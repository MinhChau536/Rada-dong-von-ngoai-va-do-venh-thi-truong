"""
Phiên TẠM TÍNH trong giờ giao dịch – để web cập nhật theo phút (trễ ≈ 2–3 phút).

Vì sao cần: REST của SSI FastConnect V3 (securitiesSummary, indexSummary, nến 1 ngày) chỉ trả số liệu của phiên SAU KHI
đóng cửa. Trong phiên chỉ có (1) luồng WebSocket và (2) nến 1 phút. Mô-đun này dựng một "phiên hôm nay" từ trạng thái
luồng mới nhất của mọi mã HOSE rồi chạy lại CHÍNH chuỗi chỉ báo (src/analytics/pipeline.py) trên ~320 phiên gần nhất
cộng phiên hôm nay, ghi vào kho phụ data/live.duckdb. Web ghép phiên này vào sau dữ liệu lịch sử (src/app/data_access.py).

Nguồn từng trường của phiên tạm tính:
  giá mở/cao/thấp/khớp, khối lượng lũy kế, giá TB  ← luồng trade (cả sàn HOSE)
  giá trị khớp                                     ← khối lượng lũy kế × giá trung bình
  khối ngoại mua/bán (khối lượng, giá trị), room   ← luồng room (từng mã HOSE)
  tham chiếu / trần / sàn                          ← REST masterdata của chính ngày hôm nay
  chỉ số: điểm, thay đổi, số mã tăng/giảm, KL, GT   ← luồng indexsummary; mở/cao/thấp ← nến 1 phút REST
Mã chưa có tin trade từ khi bộ ghi khởi động → bổ sung bằng nến 1 phút REST (tối đa BOOT_PER_BUILD mã mỗi lượt).
Sau khi đóng cửa, bản cập nhật cuối ngày (REST) thay thế hoàn toàn phiên tạm tính.
"""
from __future__ import annotations

import os
import time
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from src.common.config import abs_path
from src.common.logging import get_logger
from src.common.timeutil import now_vn
from src.data import database as db

log = get_logger(__name__)
LIVE_DB = abs_path("data/live.duckdb")
TMP_DB = abs_path("data/live_build.duckdb")
HIST_SESSIONS = 320          # đủ cho phân vị 250 phiên, z 60 phiên, MA50
BOOT_PER_BUILD = 400         # khởi động giữa phiên: bù mọi mã thiếu bằng nến 1 phút (≈ 0,25 giây/mã)
INDEX_MAP = {"VNINDEX": "VNINDEX", "VN30": "VN30", "HNXINDEX": "HNXINDEX", "HNXUPCOMINDEX": "UPCOMINDEX",
             "UPCOMINDEX": "UPCOMINDEX"}

_MASTER: Dict = {}
_BOOT: Dict[str, Dict] = {}


def hose_symbols() -> list:
    """Mã HOSE của phiên gần nhất trong kho (cùng tập mã mà chuỗi chỉ báo dùng)."""
    df = db.query_df("SELECT symbol FROM fact_daily_stock WHERE trade_date = (SELECT MAX(trade_date) FROM fact_daily_stock) "
                     "AND (board = 'HOSE' OR board IS NULL)")
    return sorted(df["symbol"].tolist())


def _master(today: date) -> Dict[str, Dict]:
    if _MASTER.get("date") != today:
        from src.bot.intraday import _client
        rows = _client().master_data(today, today)
        _MASTER.clear()
        _MASTER.update(date=today, rows={str(r.get("symbol", "")).upper(): r for r in rows})
    return _MASTER["rows"]


def _bars(symbol: str, today: date) -> pd.DataFrame:
    from src.bot.intraday import _bars as b
    try:
        return b(symbol, today)
    except Exception as exc:  # noqa: BLE001
        log.warning("Nến 1 phút %s lỗi: %s", symbol, exc)
        return pd.DataFrame()


def _bootstrap(symbols: list, today: date) -> None:
    """Mã chưa có tin trade: lấy nến 1 phút REST của hôm nay (mỗi lượt tối đa BOOT_PER_BUILD mã)."""
    now = time.time()
    todo = [s for s in symbols if s not in _BOOT or ("close" not in _BOOT[s] and now - _BOOT[s].get("_t", 0) > 600)][:BOOT_PER_BUILD]
    for s in todo:
        df = _bars(s, today)
        if df.empty:
            _BOOT[s] = {"_t": now}      # chưa khớp lệnh nào → thử lại sau 10 phút
            continue
        v = df["volume"].fillna(0)
        _BOOT[s] = {"open": float(df["open"].iloc[0]), "high": float(df["high"].max()), "low": float(df["low"].min()),
                    "close": float(df["close"].iloc[-1]), "vol": float(v.sum()), "tv": float((df["close"] * v).sum())}


def stock_rows(state: Dict, today: date) -> pd.DataFrame:
    """Dòng fact_daily_stock của phiên hôm nay từ trạng thái luồng."""
    syms = hose_symbols()
    master = _master(today)
    trades, rooms = state.get("trade", {}), state.get("room", {})
    _bootstrap([s for s in syms if s not in trades], today)
    prev = db.query_df("SELECT symbol, close, remain, room FROM fact_daily_stock WHERE trade_date = "
                       "(SELECT MAX(trade_date) FROM fact_daily_stock)").set_index("symbol")
    out = []
    for s in syms:
        m, t, r = master.get(s, {}), trades.get(s), rooms.get(s)
        row = {"trade_date": today, "symbol": s, "source": "SSI", "board": m.get("board") or "HOSE",
               "ref": m.get("refPrice"), "ceiling": m.get("ceiling"), "floor": m.get("floor"),
               "vol_pt": 0.0, "tv_pt": 0.0}
        if t:
            vol = float(t.get("total_volume") or 0)
            row.update(open=t.get("open"), high=t.get("high"), low=t.get("low"), close=t.get("price"), vol=vol,
                       tv=vol * float(t.get("avg") or t.get("price") or 0))
        elif "close" in _BOOT.get(s, {}):
            row.update({k: v for k, v in _BOOT[s].items() if not k.startswith("_")})
        else:
            row.update(open=np.nan, high=np.nan, low=np.nan, close=np.nan, vol=0.0, tv=0.0)
        if r:
            row.update(fb_vol=r.get("buy_quantity"), fs_vol=r.get("sell_quantity"), fb=r.get("buy_value"),
                       fs=r.get("sell_value"), remain=r.get("current_room"), room=r.get("total_room"))
        else:
            row.update(fb_vol=0.0, fs_vol=0.0, fb=0.0, fs=0.0,
                       remain=prev["remain"].get(s, np.nan) if s in prev.index else np.nan,
                       room=prev["room"].get(s, np.nan) if s in prev.index else np.nan)
        if row.get("ref") in (None, 0) and s in prev.index:
            row["ref"] = prev["close"].get(s)
        out.append(row)
    df = pd.DataFrame(out)
    num = ["ref", "ceiling", "floor", "open", "high", "low", "close", "vol", "tv", "vol_pt", "tv_pt",
           "fb_vol", "fs_vol", "fb", "fs", "remain", "room"]
    for c in num:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    for c in ("open", "high", "low", "close"):
        df.loc[df[c] <= 0, c] = np.nan
    df["loaded_at"] = now_vn().replace(tzinfo=None)
    df["listed_share_est"] = np.nan
    return df


def index_rows(state: Dict, today: date) -> pd.DataFrame:
    out = []
    for code, d in state.get("indexsummary", {}).items():
        std = INDEX_MAP.get(code)
        if not std:
            continue
        f = lambda k: pd.to_numeric(d.get(k), errors="coerce")  # noqa: E731
        bars = _bars(std, today)
        row = {"trade_date": today, "index_code": std, "source": "SSI", "value": f("v"), "change": f("c"),
               "ratio_change": f("cr"), "advances": f("adv"), "declines": f("dec"), "no_changes": f("nc"),
               "ceilings": f("ce"), "floors": f("fl"), "vol": f("tq"), "tv": f("tv"),
               "open": float(bars["open"].iloc[0]) if not bars.empty else np.nan,
               "high": float(bars["high"].max()) if not bars.empty else np.nan,
               "low": float(bars["low"].min()) if not bars.empty else np.nan}
        out.append(row)
    df = pd.DataFrame(out)
    if not df.empty:
        for c in ("advances", "declines", "no_changes", "ceilings", "floors"):
            df[c] = df[c].astype("Int64")
        df["loaded_at"] = now_vn().replace(tzinfo=None)
    return df


def build(state: Dict) -> Optional[Dict]:
    """Dựng kho phụ data/live.duckdb cho phiên hôm nay. Trả thông tin tóm tắt hoặc None nếu chưa đủ dữ liệu."""
    from src.analytics import pipeline
    t0 = time.time()
    today = now_vn().date()
    main_last = db.query_df("SELECT MAX(trade_date) d FROM fact_daily_stock")["d"].iat[0]
    if main_last is not None and pd.Timestamp(main_last).date() >= today:
        return None                                          # kho chính đã có phiên hôm nay (cập nhật cuối ngày)
    idx = index_rows(state, today)
    if idx.empty or "VNINDEX" not in set(idx["index_code"]):
        log.info("Chưa có indexsummary VNINDEX trong luồng – chưa dựng phiên tạm tính")
        return None
    srows = stock_rows(state, today)
    n_traded = int(srows["close"].notna().sum())
    if n_traded < 50:
        return None
    hist_dates = db.query_df("SELECT DISTINCT trade_date FROM fact_daily_stock ORDER BY trade_date DESC LIMIT ?",
                             [HIST_SESSIONS])["trade_date"]
    start = pd.Timestamp(hist_dates.min())
    hist = db.query_df("SELECT * FROM fact_daily_stock WHERE trade_date >= ?", [start])
    ihist = db.query_df("SELECT * FROM fact_daily_index WHERE trade_date >= ?", [start - pd.Timedelta(days=10)])
    sec = db.query_df("SELECT * FROM dim_securities")
    uni = db.query_df("SELECT * FROM dim_universe")
    for p in (TMP_DB, TMP_DB.with_suffix(".duckdb.wal")):
        if p.exists():
            p.unlink()
    db.init_schema(TMP_DB)
    stock = pd.concat([hist, srows[[c for c in hist.columns if c in srows.columns]]], ignore_index=True)
    index = pd.concat([ihist, idx[[c for c in ihist.columns if c in idx.columns]]], ignore_index=True)
    with db.connect(path=TMP_DB) as con:
        for name, df in (("fact_daily_stock", stock), ("fact_daily_index", index), ("dim_securities", sec),
                         ("dim_universe", uni)):
            con.execute(f"DELETE FROM {name}")
            con.register("_df", df)
            cols = ", ".join(df.columns)
            con.execute(f"INSERT INTO {name} ({cols}) SELECT {cols} FROM _df")
            con.unregister("_df")
    pipeline.compute(path=TMP_DB, write=True)
    last_trade = max((str(t.get("trading_time", "")) for t in state.get("trade", {}).values()), default="")
    info = {"session_date": pd.Timestamp(today), "built_at": now_vn().replace(tzinfo=None), "n_symbols": len(srows),
            "n_traded": n_traded, "n_room": len(state.get("room", {})), "last_tick": last_trade[:19],
            "seconds": round(time.time() - t0, 1)}
    db.replace_table("live_meta", pd.DataFrame([info]), TMP_DB)
    _swap()
    log.info("Phiên tạm tính %s: %d/%d mã có giao dịch, room %d mã, tick cuối %s (%.1f giây)", today, n_traded,
             len(srows), info["n_room"], info["last_tick"], info["seconds"])
    return info


def _jsonnum(o):
    if o is pd.NA or o is None:
        return None
    if isinstance(o, np.integer):
        return int(o)
    return float(o)


WS_SOURCE = "SSI-WS"     # nguồn tạm tính trong raw_*: ưu tiên THẤP hơn "SSI" (REST) – bản chính thức tự thay thế


def promote(state: Dict) -> Optional[Dict]:
    """Sau ATC (≈ 15:05): ghi phiên hôm nay từ trạng thái luồng WebSocket vào raw_daily_stock / raw_daily_index của KHO
    CHÍNH (source = 'SSI-WS', payload cùng tên trường với securitiesSummary / indexSummary của SSI REST) để chuỗi xử lý
    tính đủ mọi kết quả trước 15:15 mà không phải chờ SSI công bố số liệu cuối ngày qua REST.
    Khi SSI REST có số liệu chính thức (source = 'SSI'), build_facts giữ bản 'SSI' (ưu tiên cao hơn) → số tạm tính bị thay."""
    import json
    from src.ssi_api.ssi_client import enrich_stock
    today = now_vn().date()
    # Chỉ chốt khi luồng còn sống tới sau ATC: lệnh khớp cuối cùng phải sau 14:44 (máy ngủ / mất mạng giữa phiên → giá cũ,
    # KHÔNG ghi vào kho chính; chờ bản REST chính thức)
    last = max((str(t.get("trading_time", "")) for t in state.get("trade", {}).values()), default="")
    if last[:10].replace("/", "-") != today.isoformat() or last[11:16] < "14:44":
        log.warning("Luồng WebSocket ngừng từ %s (máy ngủ hoặc mất kết nối) – không chốt phiên từ luồng, chờ SSI REST",
                    last[11:19] or "đầu phiên")
        return None
    idx = index_rows(state, today)
    srows = stock_rows(state, today)
    if idx.empty or "VNINDEX" not in set(idx["index_code"]) or int(srows["close"].notna().sum()) < 50:
        log.info("Không đủ dữ liệu luồng để chốt phiên %s (nghỉ lễ hoặc bộ ghi chạy quá muộn)", today)
        return None
    master = _master(today)
    ts = now_vn().replace(tzinfo=None)
    day_s = today.strftime("%Y/%m/%d")
    recs = []
    for r in srows[srows["close"].notna()].itertuples():
        m = master.get(r.symbol) or {"refPrice": r.ref, "ceiling": r.ceiling, "floor": r.floor, "board": r.board}
        ref = float(m.get("refPrice") or r.ref or np.nan)
        payload = {"tradingDate": day_s, "symbol": r.symbol, "open": r.open, "high": r.high, "low": r.low, "close": r.close,
                   "priceChange": r.close - ref if ref == ref else None,
                   "priceChangePercentage": (r.close / ref - 1) * 100 if ref and ref == ref else None,
                   "totalMatch": r.vol, "totalMatchValue": r.tv, "totalDeal": 0, "totalDealValue": 0,
                   "totalForeignBuy": r.fb_vol, "totalForeignSell": r.fs_vol, "totalForeignBuyValue": r.fb,
                   "totalForeignSellValue": r.fs, "remainForeignRoom": r.remain, "totalForeignRoom": r.room,
                   "_provisional": "websocket"}
        payload = {k: (None if isinstance(v, float) and v != v else v) for k, v in payload.items()}
        recs.append({"trade_date": today, "symbol": r.symbol, "source": WS_SOURCE, "loaded_at": ts,
                     "payload": json.dumps(enrich_stock(payload, m), ensure_ascii=False, default=_jsonnum)})
    irecs = []
    for r in idx.itertuples():
        payload = {"tradingDate": day_s, "indexId": r.index_code, "indexValue": r.value, "indexChange": r.change,
                   "indexChangePercentage": r.ratio_change, "totalAdvanceStock": r.advances, "totalDeclineStock": r.declines,
                   "totalNoChangeStock": r.no_changes, "totalCeilingStock": r.ceilings, "totalFloorStock": r.floors,
                   "totalMatch": r.vol, "totalMatchValue": r.tv, "open": r.open, "high": r.high, "low": r.low,
                   "_provisional": "websocket"}
        payload = {k: (None if v is pd.NA or (isinstance(v, float) and v != v) else v) for k, v in payload.items()}
        irecs.append({"trade_date": today, "index_code": r.index_code, "source": WS_SOURCE, "loaded_at": ts,
                      "payload": json.dumps(payload, ensure_ascii=False, default=_jsonnum)})
    db.upsert("raw_daily_stock", pd.DataFrame(recs))
    db.upsert("raw_daily_index", pd.DataFrame(irecs))
    log.info("Chốt phiên %s từ luồng WebSocket: %d mã, %d chỉ số (nguồn %s – chờ SSI REST thay bằng số chính thức)",
             today, len(recs), len(irecs), WS_SOURCE)
    return {"stocks": len(recs), "indexes": len(irecs)}


def _swap() -> None:
    """Thay data/live.duckdb bằng bản vừa dựng (thử lại nếu web đang đọc tệp)."""
    for i in range(20):
        try:
            os.replace(TMP_DB, LIVE_DB)
            return
        except PermissionError:
            time.sleep(0.25 * (i + 1))
    log.warning("Không thay được data/live.duckdb (tệp đang bị khóa) – giữ bản cũ")


def meta(path: Path = LIVE_DB) -> Optional[Dict]:
    """Thông tin phiên tạm tính nếu còn hiệu lực (cùng ngày hôm nay và mới hơn kho chính)."""
    if not path.exists():
        return None
    try:
        m = db.query_df("SELECT * FROM live_meta", path=path)
    except Exception:  # noqa: BLE001
        return None
    if m.empty:
        return None
    r = m.iloc[0].to_dict()
    if pd.Timestamp(r["session_date"]).date() != now_vn().date():
        return None
    main_last = db.query_df("SELECT MAX(trade_date) d FROM indicator_daily")["d"].iat[0]
    if main_last is not None and pd.Timestamp(main_last) >= pd.Timestamp(r["session_date"]):
        return None
    return r
