"""
Tải dữ liệu THẬT từ SSI FastConnect V3 (bước B1.8–B1.11).

    python -m src.data.backfill                # từ history.start_date đến phiên gần nhất đã đóng cửa, chạy tiếp từ điểm dừng
    python -m src.data.backfill --from 2025-04-01 --to 2025-04-30

- securitiesByBoard HOSE → raw_securities (listedShare, stockType); securitiesByBoard index=VN30 → raw_index_components.
- masterdata (tham chiếu/trần/sàn) theo ngày + securitiesSummary từng cổ phiếu HOSE cho cả khoảng ngày
  → raw_daily_stock (JSON gốc đã ghép refPrice/ceiling/floor, source='SSI').
- indexSummary từng phiên (số mã tăng/giảm, khối ngoại toàn sàn) + ohlc 1d → raw_daily_index cho VNINDEX, VN30,
  HNXINDEX, UPCOMINDEX.
- ohlc 5m của ~20 phiên gần nhất cho VN30 + watchlist + chỉ số VN30 → raw_intraday.
Gọi API song song (mặc định 6 luồng) nhưng luôn giãn cách theo giới hạn 20 yêu cầu/giây của máy chủ.
"""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as dtime, timedelta
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from src.common.config import get
from src.common.logging import get_logger
from src.common.timeutil import now_vn, parse_ssi_date, today_vn
from src.data import database as db
from src.ssi_api.ssi_client import SSIClient, enrich_index, enrich_stock

log = get_logger(__name__)
SRC = "SSI"
JOB = "backfill_daily_stock"
JOB_INDEX = "backfill_daily_index"
WORKERS = 6


def _now():
    return datetime.now().replace(microsecond=0)


def _d(s) -> Optional[date]:
    ts = parse_ssi_date(s)
    return None if pd.isna(ts) else ts.date()


def _pmap(fn: Callable, items: Iterable, workers: int = WORKERS) -> List[Tuple]:
    """Chạy fn(item) song song; trả [(item, kết quả | Exception)] theo đúng thứ tự đầu vào."""
    items = list(items)

    def safe(x):
        try:
            return fn(x)
        except Exception as exc:  # noqa: BLE001 – ghi nhận từng mục, không dừng cả đợt
            return exc
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(zip(items, ex.map(safe, items)))


def last_closed_session() -> date:
    """Phiên gần nhất đã đóng cửa: hôm nay nếu đã qua 15:05 (ngày làm việc), nếu không thì ngày làm việc trước."""
    now = now_vn()
    d = now.date() if now.time() >= dtime(15, 5) else now.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


# ── danh mục ──────────────────────────────────────────────────────────────────
def securities(c: SSIClient) -> int:
    rows = c.securities("HOSE")
    as_of = today_vn()
    df = pd.DataFrame({"symbol": [r.get("symbol") for r in rows], "as_of": as_of, "source": SRC,
                       "payload": [json.dumps(r, ensure_ascii=False) for r in rows], "loaded_at": _now()})
    db.upsert("raw_securities", df.dropna(subset=["symbol"]))
    comp = [s for s in c.index_components("VN30") if STOCK_CODE.match(s) and s != "VN30"]
    if len(comp) >= 20:                     # V3 hiện chỉ trả chính mã chỉ số → không ghi rác vào raw_index_components
        db.upsert("raw_index_components", pd.DataFrame({"index_code": "VN30", "symbol": comp, "as_of": as_of,
                                                        "source": SRC, "loaded_at": _now()}))
    log.info("Danh mục HOSE: %d mã; VN30: %d mã", len(df), len(comp))
    return len(df)


def stock_symbols() -> List[str]:
    """Cổ phiếu thường HOSE theo danh mục mới nhất (stockType = Stock)."""
    raw = db.query_df("SELECT symbol, payload FROM raw_securities WHERE source = 'SSI' "
                      "AND as_of = (SELECT MAX(as_of) FROM raw_securities WHERE source = 'SSI')")
    out = []
    for sym, p in zip(raw["symbol"], raw["payload"]):
        d = json.loads(p)
        if str(d.get("stockType") or d.get("SecType") or "").strip().lower() in ("stock", "st", "s"):
            out.append(str(sym).upper().strip())
    return sorted(set(out))


# ── giá & khối ngoại từng mã ─────────────────────────────────────────────────
STOCK_CODE = re.compile(r"^[A-Z0-9]{3}$")      # cổ phiếu HOSE: đúng 3 ký tự (loại chứng quyền, ETF, quỹ đóng)
MASTER_KEYS = ("refPrice", "ceiling", "floor", "board")


def master(c: SSIClient, start: date, end: date, board: Optional[str] = None) -> Dict[Tuple[date, str], Dict]:
    """Giá tham chiếu/trần/sàn + SÀN NIÊM YẾT theo (ngày, mã), chia khúc 10 ngày để mỗi lần gọi ít trang.
    Giữ mọi sàn (board=None) để biết mã nào ở HOSE vào từng ngày – mã chuyển từ UPCOM/HNX sang HOSE và mã đã
    hủy niêm yết đều có trong masterdata của ngày đó (khắc phục sai lệch sống sót)."""
    chunks, s = [], start
    while s <= end:
        e = min(end, s + timedelta(days=9))
        chunks.append((s, e))
        s = e + timedelta(days=1)
    out: Dict[Tuple[date, str], Dict] = {}
    for (s, e), rows in _pmap(lambda se: c.master_data(*se), chunks):
        if isinstance(rows, Exception):
            log.warning("masterdata %s→%s lỗi: %s", s, e, rows)
            continue
        for r in rows:
            sym = str(r.get("symbol", "")).upper().strip()
            if not STOCK_CODE.match(sym):
                continue
            if board and str(r.get("board", "")).upper() != board:
                continue
            d = _d(r.get("tradingDate"))
            if d:
                out[(d, sym)] = {k: r.get(k) for k in MASTER_KEYS}
    log.info("masterdata %s→%s: %d bản ghi (%s)", start, end, len(out), board or "mọi sàn")
    return out


def hose_symbols(ref: Dict[Tuple[date, str], Dict], exchange: str = "HOSE") -> List[str]:
    """Mã từng niêm yết trên HOSE ít nhất một phiên trong khoảng (theo masterdata của ngày)."""
    return sorted({sym for (_, sym), m in ref.items() if str(m.get("board") or "").upper() == exchange})


def _year_chunks(start: date, end: date) -> List[Tuple[date, date]]:
    out, s = [], start
    while s <= end:
        e = min(end, date(s.year, 12, 31))
        out.append((s, e))
        s = e + timedelta(days=1)
    return out


def stocks(c: SSIClient, start: date, end: date, symbols: Optional[List[str]] = None,
           use_checkpoint: bool = True) -> int:
    """securitiesSummary từng mã, theo khúc 1 năm (giữ bộ nhớ nhỏ khi tải 10 năm); điểm dừng sau mỗi khúc đủ mã.
    use_checkpoint=False: tải lại đúng khoảng [start, end] (ghi đè), không đọc/ghi điểm dừng – dùng để vá phiên lỗi."""
    ck = db.get_checkpoint(JOB) if use_checkpoint else None
    if ck:
        start = max(start, pd.Timestamp(ck).date() + timedelta(days=1))
    if start > end:
        log.info("securitiesSummary: đã có dữ liệu đến %s", ck)
        return 0
    current = stock_symbols()
    n = 0
    for cs, ce in _year_chunks(start, end):
        ref = master(c, cs, ce)
        syms = symbols or sorted(set(hose_symbols(ref)) | (set(current) if ce >= today_vn() - timedelta(days=60) else set()))
        if not syms:
            raise RuntimeError("Không xác định được danh sách mã HOSE – kiểm tra masterdata / securitiesByBoard")
        n_chunk, failed = 0, []
        batch = 40
        for i in range(0, len(syms), batch):
            part = syms[i:i + batch]
            frames = []
            for sym, rows in _pmap(lambda s_: c.securities_summary(s_, cs, ce), part):
                if isinstance(rows, Exception):
                    failed.append(sym)
                    log.warning("securitiesSummary %s lỗi: %s", sym, rows)
                    continue
                recs = []
                for r in rows:
                    d = _d(r.get("tradingDate"))
                    if d is None or not (cs <= d <= ce):
                        continue
                    recs.append({"trade_date": d, "symbol": sym, "source": SRC, "loaded_at": _now(),
                                 "payload": json.dumps(enrich_stock(r, ref.get((d, sym))), ensure_ascii=False)})
                if recs:
                    frames.append(pd.DataFrame(recs))
            if frames:
                df = pd.concat(frames, ignore_index=True)
                db.upsert("raw_daily_stock", df)
                n_chunk += len(df)
        n += n_chunk
        log.info("securitiesSummary %s→%s: %d mã HOSE, %d dòng%s", cs, ce, len(syms), n_chunk,
                 f", {len(failed)} mã lỗi" if failed else "")
        if failed:
            log.warning("%d mã lỗi (tải lại ở lần chạy sau, không ghi điểm dừng): %s", len(failed), ", ".join(failed[:20]))
            return n
        if use_checkpoint:
            db.set_checkpoint(JOB, ce.strftime("%Y-%m-%d"))
    return n


# ── chỉ số ────────────────────────────────────────────────────────────────────
def indexes(c: SSIClient, start: date, end: date, use_checkpoint: bool = True) -> int:
    ck = db.get_checkpoint(JOB_INDEX) if use_checkpoint else None
    if ck:
        start = max(start, pd.Timestamp(ck).date() + timedelta(days=1))
    if start > end:
        return 0
    n, ok = 0, True
    for code in get("history.index_codes", ["VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"]):
        bars = {}
        for b in c.ohlc(code, "1d", start, end):                     # nến ngày → biết luôn các phiên giao dịch
            d = _d(b.get("tradingDate"))
            if d:
                bars[d] = b
        days = sorted(bars) or [d.date() for d in pd.bdate_range(start, end)]
        recs = []
        for d, rows in _pmap(lambda x: c.index_summary(code, x), days):
            if isinstance(rows, Exception):
                ok = False
                log.warning("indexSummary %s %s lỗi: %s", code, d, rows)
                continue
            for r in rows:
                rd = _d(r.get("tradingDate")) or d
                if rd != d:                                         # máy chủ trả phiên gần nhất khi ngày nghỉ
                    continue
                recs.append({"trade_date": d, "index_code": code, "source": SRC, "loaded_at": _now(),
                             "payload": json.dumps(enrich_index({**r, "index": code}, bars.get(d)), ensure_ascii=False)})
        if recs:
            db.upsert("raw_daily_index", pd.DataFrame(recs))
            n += len(recs)
        log.info("indexSummary %s %s→%s: %d phiên", code, start, end, len(recs))
    if ok and use_checkpoint:
        db.set_checkpoint(JOB_INDEX, end.strftime("%Y-%m-%d"))
    return n


# ── nến 5 phút ────────────────────────────────────────────────────────────────
def intraday(c: SSIClient, symbols, sessions: int = 20, end: Optional[date] = None) -> int:
    end = end or last_closed_session()
    start = end - timedelta(days=int(sessions * 1.5) + 4)
    tf = get("ssi.intraday_timeframe", "5m")
    n = 0
    for s, rows in _pmap(lambda x: c.ohlc(x, tf, start, end), list(symbols)):
        if isinstance(rows, Exception):
            log.warning("ohlc %s %s lỗi: %s", tf, s, rows)
            continue
        recs = []
        for r in rows:
            ts = parse_ssi_date(r.get("tradingDate"))
            if pd.isna(ts):
                continue
            recs.append({"ts": ts, "symbol": s, "source": SRC, "payload": json.dumps(r, ensure_ascii=False),
                         "loaded_at": _now()})
        if recs:
            db.upsert("raw_intraday", pd.DataFrame(recs).drop_duplicates(["ts", "symbol"]))
            n += len(recs)
    log.info("ohlc %s: %d nến cho %d mã", tf, n, len(list(symbols)))
    return n


def intraday_symbols() -> List[str]:
    vn30 = db.query_df("SELECT DISTINCT symbol FROM dim_universe WHERE universe = 'VN30'")
    syms = vn30["symbol"].tolist() if not vn30.empty else []
    if len(syms) < 20:
        from src.common.config import stock_groups
        g = stock_groups()
        syms = g.loc[g["in_vn30"].astype(bool), "symbol"].tolist() if not g.empty else syms
    return sorted(set(syms + ["VN30"] + list(get("watchlist_default", []))))


def update_session(c: SSIClient, d: date) -> dict:
    """Cập nhật MỘT phiên (bộ lập lịch 15:05): giá + khối ngoại, chỉ số, nến 5 phút."""
    out = {"stocks": stocks(c, d, d), "indexes": indexes(c, d, d)}
    out["intraday"] = intraday(c, intraday_symbols(), int(get("windows.intraday_sessions", 20)), end=d)
    db.set_source_status("SSI", "ok", f"cập nhật phiên {d}")
    return out


def _reset_checkpoints_if_extending(start: date, full: bool) -> None:
    """Điểm dừng chỉ cho tải TIẾP về sau. Khi lùi ngày bắt đầu (history.start_date sớm hơn dữ liệu đang có) hoặc
    --full: bỏ điểm dừng để tải lại cả khoảng (upsert ghi đè, không trùng dòng)."""
    have = db.query_df("SELECT MIN(trade_date) AS d FROM raw_daily_stock WHERE source = 'SSI'")
    earliest = None if have.empty or pd.isna(have["d"].iloc[0]) else pd.Timestamp(have["d"].iloc[0]).date()
    if full or (earliest is not None and earliest > start + timedelta(days=7)):
        log.info("Tải lại từ %s (dữ liệu hiện có bắt đầu %s) – bỏ điểm dừng cũ", start, earliest)
        db.execute("DELETE FROM checkpoints WHERE job IN (?, ?)", [JOB, JOB_INDEX])


def main(start: Optional[date] = None, end: Optional[date] = None, full: bool = False) -> dict:
    db.init_schema()
    c = SSIClient()
    if not c.is_available:
        raise SystemExit("Thiếu SSI_API_KEY / SSI_API_SECRET trong .env (tạo tại SSI Developer Portal – FastConnect V3).")
    start = start or pd.Timestamp(get("history.start_date")).date()
    end = end or last_closed_session()
    _reset_checkpoints_if_extending(start, full)
    try:
        out = {"securities": securities(c), "stocks": stocks(c, start, end), "indexes": indexes(c, start, end)}
        out["intraday"] = intraday(c, intraday_symbols(), int(get("windows.intraday_sessions", 20)), end=end)
    except Exception as exc:
        db.set_source_status("SSI", "error", str(exc)[:300], ok=False)
        raise
    db.set_source_status("SSI", "ok", f"backfill {start}→{end}")
    log.info("Backfill xong: %s", out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--full", action="store_true", help="Bỏ điểm dừng, tải lại toàn bộ khoảng ngày")
    a = ap.parse_args()
    print(main(pd.Timestamp(a.start).date() if a.start else None, pd.Timestamp(a.end).date() if a.end else None,
               full=a.full))
