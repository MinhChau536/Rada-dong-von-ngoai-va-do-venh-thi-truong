"""
Bộ ghi luồng WebSocket SSI FastConnect V3 (bước B1.4b, B5.9) – luồng thời gian thực DUY NHẤT của hệ thống.

    python -m src.data.recorder_ssi                 # chạy trong cửa sổ 8:55–15:05 các ngày làm việc rồi tự dừng
    python -m src.data.recorder_ssi --seconds 60    # ghi thử 60 giây (bất kể giờ) – dùng để kiểm tra kết nối

Kết nối wss://stream.ssi.com.vn/ws/v3 qua SDK chính thức `ssi-sdk` (xác thực bằng API Key/Secret, không OTP), đăng ký:
  • indexsummary.<VNINDEX|VN30|HNXINDEX|UPCOMINDEX>  – điểm, số mã tăng/giảm, GT khớp, khối ngoại toàn sàn
  • trade.index.<VNINDEX|VN30>                       – tick của chính chỉ số
  • room.<mã>  / trade.<mã>  cho VN30 + watchlist     – room & khối ngoại lũy kế; lệnh khớp kèm chiều chủ động
Mỗi tin lưu nguyên văn (JSON) vào raw_stream (source='SSI'); ghi theo lô. SDK tự kết nối lại (backoff có trần) và
làm mới token trước khi hết hạn. Luồng im lặng > stream.silence_sec giây trong phiên → source_status 'degraded'
+ thông báo sự cố qua Telegram; có tin trở lại → 'ok'.
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import threading
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from src.common.config import env, get, ssi_base_url, ssi_stream_url
from src.common.logging import get_logger
from src.common.timeutil import in_recorder_window, in_session, now_vn
from src.data import database as db
from src.finance.domestic import active_imbalance

log = get_logger(__name__)
INDEXES = ["VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"]

_CHANNEL = {"IndexSummaryMessage": "indexsummary", "IndexTickMessage": "trade.index", "TradeMessage": "trade",
            "ForeignRoomMessage": "room", "QuoteMessage": "quote", "IntervalMessage": "candle",
            "MarketFlagMessage": "market.flag", "MarketStatusMessage": "market", "MarketDataMessage": "market"}


def _jsonable(v: Any) -> Any:
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def to_row(msg: Any, ts=None) -> Optional[Dict]:
    """Tin từ SDK (dataclass hoặc dict) → một dòng raw_stream."""
    ts = ts or now_vn().replace(tzinfo=None)
    if dataclasses.is_dataclass(msg) and not isinstance(msg, type):
        name = type(msg).__name__
        body = _jsonable(dataclasses.asdict(msg))
    elif isinstance(msg, dict):
        if msg.get("method") or msg.get("channel") == "HEARTBEAT":       # xác nhận subscribe / heartbeat
            return None
        name = "dict"
        body = _jsonable(msg)
    else:
        return None
    channel = _CHANNEL.get(name) or str(body.get("type") or body.get("topic") or name)
    inner = body.get("data") if isinstance(body.get("data"), dict) else {}
    sym = body.get("symbol") or body.get("index") or inner.get("symbol") or inner.get("index")
    return {"recv_ts": ts, "session_date": ts.date(), "channel": channel, "symbol": (str(sym).upper() if sym else None),
            "source": "SSI", "payload": json.dumps(body, ensure_ascii=False, default=str)}


def symbols_to_watch() -> List[str]:
    vn30 = db.query_df("SELECT symbol FROM dim_universe WHERE universe='VN30'")
    if vn30.empty:
        vn30 = db.query_df("SELECT DISTINCT symbol FROM raw_index_components WHERE index_code='VN30'")
    from src.analytics.watchlist_impact import get_watchlist
    return sorted(set(vn30["symbol"].tolist() + list(get_watchlist())))


class Recorder:
    def __init__(self, flush_rows: Optional[int] = None):
        self.buf: List[Dict] = []
        self.lock = threading.Lock()
        self.flush_rows = int(flush_rows or get("stream.flush_rows", 200))
        self.silence = float(get("stream.silence_sec", 120))
        self.last_msg = time.monotonic()
        self.n = 0
        self.degraded = False

    def on_data(self, msg: Any) -> None:
        row = to_row(msg)
        if row is None:
            return
        with self.lock:
            self.buf.append(row)
            self.n += 1
            self.last_msg = time.monotonic()
            full = len(self.buf) >= self.flush_rows
        if full:
            self.flush()

    def flush(self) -> int:
        with self.lock:
            rows, self.buf = self.buf, []
        if rows:
            try:
                db.append("raw_stream", pd.DataFrame(rows))
            except Exception as exc:  # noqa: BLE001 – không mất tin: trả lại bộ đệm
                log.warning("Ghi raw_stream lỗi (%s) – giữ lại %d tin", exc, len(rows))
                with self.lock:
                    self.buf = rows + self.buf
                return 0
        return len(rows)

    def check_silence(self) -> None:
        quiet = time.monotonic() - self.last_msg
        if in_session() and quiet > self.silence and not self.degraded:
            self.degraded = True
            msg = f"Luồng WebSocket SSI im lặng {int(quiet)} giây trong phiên"
            log.warning(msg)
            db.set_source_status("SSI", "degraded", msg, ok=False)
            db.append("source_events", pd.DataFrame([{"ts": now_vn().replace(tzinfo=None), "from_source": "SSI",
                                                      "to_source": "SSI", "reason": msg}]))
            try:
                from src.bot.jobs import data_incident
                data_incident(msg)
            except Exception as exc:  # noqa: BLE001
                log.warning("Không gửi được thông báo sự cố: %s", exc)
        elif self.degraded and quiet < self.silence:
            self.degraded = False
            db.set_source_status("SSI", "ok", "Luồng WebSocket SSI hoạt động trở lại")


def _sdk():
    try:
        from ssi_sdk import Auth, Config, Stream  # type: ignore
    except ImportError:
        raise SystemExit("Chưa cài SDK chính thức của SSI: pip install ssi-sdk")
    return Auth, Config, Stream


def run(seconds: Optional[float] = None, symbols: Optional[List[str]] = None) -> Dict:
    """Ghi luồng đến hết cửa sổ ghi (hoặc `seconds` giây). Trả thống kê {messages, by_channel}."""
    Auth, Config, Stream = _sdk()
    if not (env("SSI_API_KEY") and env("SSI_API_SECRET")):
        raise SystemExit("Thiếu SSI_API_KEY / SSI_API_SECRET trong .env")
    db.init_schema()
    if seconds is None and not in_recorder_window():
        log.info("Ngoài cửa sổ ghi %s–%s – không chạy.", get("session.recorder_start"), get("session.recorder_end"))
        return {"messages": 0, "skipped": True}
    syms = symbols if symbols is not None else symbols_to_watch()
    rec = Recorder()
    cfg = Config(api_key=env("SSI_API_KEY"), api_secret=env("SSI_API_SECRET"), api_url=ssi_base_url(),
                 streaming_url=ssi_stream_url(), log_level=env("LOG_LEVEL", "INFO") or "INFO")
    t_end = time.monotonic() + seconds if seconds else None
    with Auth(cfg) as auth:
        auth.authenticate()                                   # dữ liệu thị trường: không cần OTP
        with Stream(auth) as stream:
            s = stream.streaming
            s.on_data = rec.on_data
            s.connect()
            s.subscribe_index_summary(INDEXES)
            s.subscribe_index_trade(["VNINDEX", "VN30"])
            if syms:
                s.subscribe_symbol_room(syms)
                s.subscribe_symbol_trade(syms)
            db.set_source_status("SSI", "ok", f"WebSocket V3 đã kết nối · {len(syms)} mã")
            log.info("Đang ghi luồng SSI V3: %d chỉ số, %d mã", len(INDEXES), len(syms))
            last_flush = time.monotonic()
            try:
                while True:
                    time.sleep(2)
                    if time.monotonic() - last_flush > 10:
                        rec.flush()
                        last_flush = time.monotonic()
                    rec.check_silence()
                    if t_end is not None:
                        if time.monotonic() >= t_end:
                            break
                    elif not in_recorder_window():
                        break
            except KeyboardInterrupt:
                log.info("Dừng theo yêu cầu")
            finally:
                rec.flush()
                try:
                    s.disconnect()
                except Exception:  # noqa: BLE001
                    pass
    by = db.query_df("SELECT channel, COUNT(*) n FROM raw_stream WHERE session_date = ? GROUP BY 1",
                     [now_vn().date()])
    out = {"messages": rec.n, "by_channel": dict(zip(by.get("channel", []), by.get("n", [])))}
    log.info("Kết thúc ghi luồng: %s", out)
    return out


def imbalance_from_stream(session_date) -> pd.DataFrame:
    """Mất cân bằng mua/bán chủ động (BU − SD)/(BU + SD) theo mã từ kênh trade đã ghi (side B → BU, S → SD)."""
    df = db.query_df("SELECT payload FROM raw_stream WHERE channel = 'trade' AND session_date = ?", [session_date])
    rows = []
    for p in df.get("payload", []):
        try:
            c = json.loads(p)
            side = {"B": "BU", "S": "SD"}.get(str(c.get("side", "")).upper(), str(c.get("side", "")).upper())
            rows.append({"symbol": c.get("symbol"), "side": side, "vol": float(c.get("quantity") or 0)})
        except (ValueError, AttributeError, TypeError):
            continue
    return active_imbalance(pd.DataFrame(rows))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, help="Ghi thử trong N giây (bỏ qua cửa sổ giờ)")
    a = ap.parse_args()
    print(run(seconds=a.seconds))
