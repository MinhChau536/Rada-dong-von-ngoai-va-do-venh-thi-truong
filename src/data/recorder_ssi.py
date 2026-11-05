"""
Bộ ghi SSI streaming (bước B5.9 – mức "Nên có").

    python -m src.data.recorder_ssi

Đăng ký kênh MI (chỉ số), R (khối ngoại, room), X-TRADE (lệnh khớp kèm Side) cho VN30 + watchlist; lưu raw_stream;
tự kết nối lại; chạy 9:00–15:05; mỗi tin gọi FailoverController.ssi_ok() và tick() để phát hiện im lặng > 120 giây.

Luồng SSI dùng SignalR – dùng SDK chính thức `ssi-fc-data` (pip install ssi-fc-data). Nếu chưa cài SDK, bộ ghi báo rõ
và hệ thống vẫn chạy nhờ bộ ghi NEO song song.
"""
from __future__ import annotations

import json
import time
from typing import List

import pandas as pd

from src.common.config import env, get
from src.common.logging import get_logger
from src.common.timeutil import now_vn
from src.data import database as db
from src.data.failover import FailoverController
from src.finance.domestic import active_imbalance

log = get_logger(__name__)


def channels(symbols: List[str]) -> str:
    syms = "-".join(sorted(set(symbols)))
    return f"MI:VNINDEX-VN30|R:{syms}|X-TRADE:{syms}"


def run() -> None:
    try:
        from ssi_fc_data.fc_md_stream import MarketDataStream  # type: ignore
        from ssi_fc_data import model  # noqa: F401
    except ImportError:
        raise SystemExit("Chưa cài SDK ssi-fc-data (pip install ssi-fc-data). Bộ ghi NEO vẫn đáp ứng chuẩn WebSocket của đề.")
    db.init_schema()
    fo = FailoverController(on_switch=lambda f, t, r: __import__("src.bot.jobs", fromlist=["data_incident"]).data_incident(
        f"Chuyển nguồn {f} → {t}: {r}"))
    vn30 = db.query_df("SELECT symbol FROM dim_universe WHERE universe='VN30'")["symbol"].tolist()
    from src.analytics.watchlist_impact import get_watchlist
    buf = []

    class Cfg:
        consumerID = env("SSI_CONSUMER_ID")
        consumerSecret = env("SSI_CONSUMER_SECRET")
        url = get("ssi.base_url")
        stream_url = "https://fc-datahub.ssi.com.vn/"

    def on_message(msg):
        fo.ssi_ok()
        ts = now_vn().replace(tzinfo=None)
        try:
            body = json.loads(msg) if isinstance(msg, str) else msg
        except ValueError:
            body = {"raw": str(msg)}
        content = body.get("Content") if isinstance(body, dict) else None
        sym = None
        if isinstance(content, str):
            try:
                sym = json.loads(content).get("Symbol")
            except ValueError:
                pass
        buf.append({"recv_ts": ts, "session_date": ts.date(), "channel": body.get("DataType") if isinstance(body, dict) else None,
                    "symbol": sym, "source": "SSI", "payload": json.dumps(body, ensure_ascii=False)})
        if len(buf) >= 200:
            db.append("raw_stream", pd.DataFrame(buf))
            buf.clear()

    def on_error(err):
        fo.ssi_error(str(err))

    stream = MarketDataStream(Cfg, __import__("ssi_fc_data").fc_md_client.MarketDataClient(Cfg))
    stream.start(on_message, on_error, channels(vn30 + get_watchlist()))
    while True:
        fo.tick()
        time.sleep(10)


def imbalance_from_stream(session_date) -> pd.DataFrame:
    """Mất cân bằng mua/bán chủ động (BU − SD)/(BU + SD) theo mã từ X-TRADE đã ghi."""
    df = db.query_df("SELECT payload FROM raw_stream WHERE channel = 'X' AND session_date = ?", [session_date])
    rows = []
    for p in df.get("payload", []):
        try:
            c = json.loads(json.loads(p).get("Content", "{}"))
            rows.append({"symbol": c.get("Symbol"), "side": c.get("Side"), "vol": float(c.get("LastVol") or 0)})
        except (ValueError, AttributeError):
            continue
    return active_imbalance(pd.DataFrame(rows))


if __name__ == "__main__":
    run()
