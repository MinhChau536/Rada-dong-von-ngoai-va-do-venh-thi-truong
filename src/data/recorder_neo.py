"""
Bộ ghi NEO WebSocket chạy song song MỖI PHIÊN, kể cả khi SSI bình thường (bước B1.4b).

    python -m src.data.recorder_neo                 # chạy liên tục, tự chờ khung 8:55–15:05 mỗi ngày giao dịch
    python -m src.data.recorder_neo --seconds 120   # ghi thử 2 phút (bất kể giờ) để kiểm tra kết nối

(1) Kết nối wss://neoapi.vpbanks.com.vn/stock-stream/broker, đồng bộ lược đồ Avro (không cần JWT).
(2) Đăng ký marketInfo (VNINDEX, VN30, HNXINDEX, UPCOMINDEX), marketSession (HOSE/HNX/UPCOM),
    stockInfo cho toàn bộ danh mục cổ phiếu HOSE đã biết (SSI SecuritiesDetails + config/stock_groups.csv + VN30
    + watchlist) – đủ để dựng ảnh chụp cuối phiên khi SSI gián đoạn.
(3) Lưu từng tin vào raw_stream_neo kèm recv_ts (giờ VN) và bản ghi đã giải mã (JSON), ghi theo lô 2 giây.
(4) Tự kết nối lại với thời gian chờ tăng dần 2–4–8–16 giây, tối đa 60 giây.
(5) Hết khung giờ: dựng ảnh chụp cuối phiên (src.data.neo_eod) → raw_daily_stock / raw_daily_index source='NEO'.
"""
from __future__ import annotations

import argparse
import json
import time
from typing import List

import pandas as pd

from src.common.config import get, stock_groups
from src.common.logging import get_logger
from src.common.timeutil import in_recorder_window, now_vn
from src.data import database as db
from src.neo_api.neo_client import NEOClient, default_subscriptions

log = get_logger(__name__)


def universe_symbols() -> List[str]:
    """Danh mục mã HOSE cần đăng ký stockInfo."""
    syms = set()
    for sql in ("SELECT DISTINCT symbol FROM dim_securities WHERE exchange IS NULL OR upper(exchange) LIKE 'HOSE%'",
                "SELECT DISTINCT symbol FROM raw_index_components",
                "SELECT DISTINCT symbol FROM watchlist"):
        try:
            syms |= set(db.query_df(sql)["symbol"].dropna().astype(str))
        except Exception:  # noqa: BLE001 – bảng chưa có dữ liệu
            pass
    sg = stock_groups()
    if not sg.empty:
        syms |= set(sg["symbol"].astype(str))
    syms |= set(get("watchlist_default", []))
    return sorted(s.upper() for s in syms if s and len(s) == 3)


def _flush(buf: List[dict]) -> None:
    if buf:
        db.append("raw_stream_neo", pd.DataFrame(buf))
        buf.clear()


def _symbol(rec: dict):
    return rec.get("symbol") or rec.get("indexCode") or rec.get("marketCode")


def run(max_seconds: float | None = None) -> dict:
    db.init_schema()
    c = NEOClient()
    subs = default_subscriptions(universe_symbols())
    backoff = list(get("neo.reconnect_backoff_sec", [2, 4, 8, 16]))
    cap = float(get("neo.reconnect_max_sec", 60))
    t_start = time.time()
    attempt, n_total, recorded_today = 0, 0, None
    buf: List[dict] = []
    log.info("Bộ ghi NEO: %d tin đăng ký, %d mã", len(subs), sum(len(s["listId"]) for s in subs if s["channel"] == "stockInfo"))
    while max_seconds is None or time.time() - t_start < max_seconds:
        if max_seconds is None and not in_recorder_window():
            today = now_vn().date()
            if recorded_today == today:            # vừa hết khung giờ → dựng ảnh chụp cuối phiên một lần
                from src.data import neo_eod
                neo_eod.snapshot_to_raw(today)
                recorded_today = None
            time.sleep(60)
            continue
        try:
            last_flush = time.time()
            for rec in c.ws_messages(subs):
                attempt = 0
                ts = now_vn().replace(tzinfo=None)
                buf.append({"recv_ts": ts, "session_date": ts.date(), "channel": rec.pop("_channel", None),
                            "symbol": _symbol(rec), "source": "NEO",
                            "payload": json.dumps(rec, ensure_ascii=False, default=str)})
                n_total += 1
                recorded_today = ts.date()
                if time.time() - last_flush > 2:
                    _flush(buf)
                    last_flush = time.time()
                    db.set_source_status("NEO", "ok", f"đang ghi luồng WebSocket ({n_total} tin)")
                if max_seconds is None and not in_recorder_window():
                    break
                if max_seconds is not None and time.time() - t_start > max_seconds:
                    break
        except Exception as exc:  # noqa: BLE001 – mất kết nối / im lặng quá lâu → nối lại
            _flush(buf)
            wait = min(cap, backoff[min(attempt, len(backoff) - 1)] * (2 ** max(0, attempt - len(backoff) + 1)))
            attempt += 1
            if in_recorder_window() or max_seconds is not None:
                db.set_source_status("NEO", "degraded", f"mất kết nối: {exc}"[:200], ok=False)
                log.warning("NEO WebSocket lỗi: %s – nối lại sau %ss", exc, wait)
            time.sleep(wait if max_seconds is None else min(wait, 2))
    _flush(buf)
    return {"messages": n_total}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, help="Ghi thử N giây rồi dừng")
    a = ap.parse_args()
    print(run(a.seconds))
