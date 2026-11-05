"""
Bộ ghi NEO WebSocket chạy song song MỖI PHIÊN, kể cả khi SSI bình thường (bước B1.4b).

    python -m src.data.recorder_neo

(1) Kết nối ws://neoapi.vpbanks.com.vn/stock-stream/broker, gửi {action:'auth', data: JWT}.
(2) Đăng ký marketInfo (VNINDEX, VN30), marketSession (HOSE), stockInfo (VN30 + watchlist).
(3) Lưu từng tin vào raw_stream_neo kèm recv_ts (giờ VN) và JSON gốc (ghi theo lô 2 giây).
(4) Tự kết nối lại với thời gian chờ tăng dần 2–4–8–16 giây, tối đa 60 giây; làm mới JWT khi hết hạn.
(5) Chạy 8:55–15:05. Thống kê tin/phiên và thời gian mất kết nối ở trang 7 (đọc raw_stream_neo).
"""
from __future__ import annotations

import json
import time
from typing import List

import pandas as pd

from src.common.config import get
from src.common.logging import get_logger
from src.common.timeutil import in_recorder_window, now_vn
from src.data import database as db
from src.neo_api.neo_client import NEOClient, default_subscriptions

log = get_logger(__name__)


def _flush(buf: List[dict]) -> None:
    if buf:
        db.append("raw_stream_neo", pd.DataFrame(buf))
        buf.clear()


def run(max_seconds: float | None = None) -> None:
    db.init_schema()
    c = NEOClient()
    if not c.is_available:
        raise SystemExit("Thiếu NEO_USERNAME/NEO_PASSWORD trong .env")
    vn30 = db.query_df("SELECT symbol FROM dim_universe WHERE universe='VN30'")["symbol"].tolist()
    from src.analytics.watchlist_impact import get_watchlist
    subs = default_subscriptions(get_watchlist(), vn30)
    backoff = list(get("neo.reconnect_backoff_sec", [2, 4, 8, 16]))
    cap = float(get("neo.reconnect_max_sec", 60))
    t_start = time.time()
    attempt = 0
    buf: List[dict] = []
    while max_seconds is None or time.time() - t_start < max_seconds:
        if not in_recorder_window() and max_seconds is None:
            log.info("Ngoài khung 8:55–15:05 – bộ ghi NEO chờ")
            time.sleep(60)
            continue
        try:
            last_flush = time.time()
            for msg in c.ws_messages(subs):
                attempt = 0
                ts = now_vn().replace(tzinfo=None)
                ch = msg.get("channel") or msg.get("type") or msg.get("event")
                data = msg.get("data")
                sym = msg.get("symbol") or (data.get("symbol") if isinstance(data, dict) else None)
                buf.append({"recv_ts": ts, "session_date": ts.date(), "channel": ch, "symbol": sym, "source": "NEO",
                            "payload": json.dumps(msg, ensure_ascii=False)})
                if time.time() - last_flush > 2:
                    _flush(buf)
                    last_flush = time.time()
                    db.set_source_status("NEO", "ok", "đang ghi")
                if not in_recorder_window() and max_seconds is None:
                    break
                if max_seconds is not None and time.time() - t_start > max_seconds:
                    break
        except Exception as exc:  # noqa: BLE001 – mất kết nối → nối lại
            _flush(buf)
            wait = min(cap, backoff[min(attempt, len(backoff) - 1)] * (2 ** max(0, attempt - len(backoff) + 1)))
            attempt += 1
            db.set_source_status("NEO", "degraded", f"mất kết nối: {exc}"[:200], ok=False)
            log.warning("NEO WebSocket lỗi: %s – nối lại sau %ss", exc, wait)
            if "401" in str(exc) or "auth" in str(exc).lower():
                c.auth(force=True)
            time.sleep(wait)
    _flush(buf)


if __name__ == "__main__":
    run()
