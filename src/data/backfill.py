"""
Tải lịch sử từ SSI (bước B1.8–B1.11).

    python -m src.data.backfill                # từ history.start_date đến hôm qua, tiếp tục từ điểm dừng
    python -m src.data.backfill --from 2025-04-01 --to 2025-04-30

- DailyStockPrice market=HOSE từng ngày (lặp pageIndex), lưu raw_daily_stock (JSON gốc, source='SSI').
- Lưu điểm dừng (ngày cuối đã tải) vào bảng checkpoints để chạy tiếp khi gián đoạn; ngày nghỉ API trả rỗng → bỏ qua.
- DailyIndex cho VNINDEX, VN30, HNXINDEX, UPCOMINDEX; SecuritiesDetails (ListedShare, as_of); IndexComponents VN30;
  nến 1 phút 20 phiên gần nhất cho VN30 + watchlist (gộp 5 phút ở tầng chỉ báo).
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd

from src.common.config import get
from src.common.logging import get_logger
from src.common.timeutil import parse_ssi_date, today_vn
from src.data import database as db
from src.ssi_api.ssi_client import SSIClient

log = get_logger(__name__)
SRC = "SSI"
JOB = "backfill_daily_stock"


def _now():
    return datetime.now().replace(microsecond=0)


def stocks(c: SSIClient, start: date, end: date) -> int:
    ck = db.get_checkpoint(JOB)
    if ck:
        start = max(start, pd.Timestamp(ck).date() + timedelta(days=1))
    n = 0
    for d in pd.bdate_range(start, end):
        rows = c.daily_stock_price(d.date(), "HOSE")
        if rows:
            df = pd.DataFrame({"trade_date": d.date(), "symbol": [r.get("Symbol") for r in rows], "source": SRC,
                               "payload": [json.dumps(r, ensure_ascii=False) for r in rows], "loaded_at": _now()})
            db.upsert("raw_daily_stock", df.dropna(subset=["symbol"]))
            n += len(df)
            log.info("DailyStockPrice %s: %d mã", d.date(), len(df))
        else:
            log.info("DailyStockPrice %s: rỗng (ngày nghỉ)", d.date())
        db.set_checkpoint(JOB, d.strftime("%Y-%m-%d"))
    return n


def indexes(c: SSIClient, start: date, end: date) -> int:
    n = 0
    for code in get("history.index_codes", ["VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"]):
        s = start
        while s <= end:                                  # chia khúc 30 ngày cho mỗi lần gọi
            e = min(end, s + timedelta(days=30))
            rows = c.daily_index(code, s, e)
            if rows:
                df = pd.DataFrame({"trade_date": [parse_ssi_date(r.get("TradingDate")).date() for r in rows],
                                   "index_code": code, "source": SRC,
                                   "payload": [json.dumps(r, ensure_ascii=False) for r in rows], "loaded_at": _now()})
                db.upsert("raw_daily_index", df.dropna(subset=["trade_date"]))
                n += len(df)
            s = e + timedelta(days=1)
    return n


def securities(c: SSIClient) -> int:
    rows = c.securities_details("HOSE")
    as_of = today_vn()
    df = pd.DataFrame({"symbol": [r.get("Symbol") for r in rows], "as_of": as_of, "source": SRC,
                       "payload": [json.dumps(r, ensure_ascii=False) for r in rows], "loaded_at": _now()})
    db.upsert("raw_securities", df.dropna(subset=["symbol"]))
    comp = c.index_components("VN30")
    db.upsert("raw_index_components", pd.DataFrame({"index_code": "VN30", "symbol": comp, "as_of": as_of,
                                                    "source": SRC, "loaded_at": _now()}))
    return len(df)


def intraday(c: SSIClient, symbols, sessions: int = 20) -> int:
    end = today_vn() - timedelta(days=1)
    start = end - timedelta(days=int(sessions * 1.5) + 4)
    n = 0
    for s in symbols:
        rows = c.intraday_ohlc(s, start, end)
        recs = []
        for r in rows:
            ts = pd.to_datetime(f"{r.get('TradingDate')} {r.get('Time')}", format="%d/%m/%Y %H:%M:%S", errors="coerce")
            if pd.isna(ts):
                continue
            recs.append({"ts": ts.floor("5min"), "r": r})
        if not recs:
            continue
        # gộp 1 phút → 5 phút
        g = pd.DataFrame([{"ts": x["ts"], **{k: float(x["r"].get(k) or 0) for k in ("Open", "High", "Low", "Close", "Volume")}}
                          for x in recs]).groupby("ts").agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"),
                                                            Close=("Close", "last"), Volume=("Volume", "sum")).reset_index()
        payload = [json.dumps({"Symbol": s, "TradingDate": t.strftime("%d/%m/%Y"), "Time": t.strftime("%H:%M:%S"),
                               "Open": o, "High": h, "Low": lo, "Close": cl, "Volume": v})
                   for t, o, h, lo, cl, v in g[["ts", "Open", "High", "Low", "Close", "Volume"]].itertuples(index=False)]
        db.upsert("raw_intraday", pd.DataFrame({"ts": g["ts"], "symbol": s, "source": SRC, "payload": payload, "loaded_at": _now()}))
        n += len(g)
    return n


def main(start: Optional[date] = None, end: Optional[date] = None) -> dict:
    db.init_schema()
    c = SSIClient()
    if not c.is_available:
        raise SystemExit("Thiếu SSI_CONSUMER_ID / SSI_CONSUMER_SECRET trong .env (lấy tại iBoard > Dịch vụ API).")
    start = start or pd.Timestamp(get("history.start_date")).date()
    end = end or (today_vn() - timedelta(days=1))
    out = {"securities": securities(c), "stocks": stocks(c, start, end), "indexes": indexes(c, start, end)}
    vn30 = db.query_df("SELECT symbol FROM raw_index_components WHERE index_code='VN30'")["symbol"].tolist()
    out["intraday"] = intraday(c, sorted(set(vn30 + ["VN30"] + list(get("watchlist_default", [])))),
                               int(get("windows.intraday_sessions", 20)))
    db.set_source_status("SSI", "ok", f"backfill {start}→{end}")
    log.info("Backfill xong: %s", out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    a = ap.parse_args()
    print(main(pd.Timestamp(a.start).date() if a.start else None, pd.Timestamp(a.end).date() if a.end else None))
