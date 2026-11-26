"""
Bộ ghi luồng WebSocket SSI FastConnect V3 (bước B1.4b, B5.9) – luồng thời gian thực DUY NHẤT của hệ thống.

    python -m src.data.recorder_ssi                 # chạy trong cửa sổ 8:55–15:05 các ngày làm việc rồi tự dừng
    python -m src.data.recorder_ssi --seconds 60    # ghi thử 60 giây (bất kể giờ) – dùng để kiểm tra kết nối

Kết nối wss://stream.ssi.com.vn/ws/v3 qua SDK chính thức `ssi-sdk` (xác thực bằng API Key/Secret, không OTP), đăng ký:
  • indexsummary.<VNINDEX|VN30|HNXINDEX|UPCOMINDEX>  – điểm, số mã tăng/giảm, GT khớp, khối ngoại toàn sàn
  • trade.index.<VNINDEX|VN30>                       – tick của chính chỉ số
  • room.<mã>  / trade.<mã>  cho VN30 + watchlist     – room & khối ngoại lũy kế; lệnh khớp kèm chiều chủ động
  • trade/quote cả sàn HOSE + room mọi mã HOSE        – chỉ giữ TRẠNG THÁI MỚI NHẤT trong bộ nhớ (không lưu từng tin),
                                                       cứ stream.live_build_sec giây dựng phiên tạm tính (src/data/live.py)
Tin của chỉ số, VN30 và watchlist lưu nguyên văn (JSON) vào raw_stream (source='SSI'); ghi theo lô. SDK tự kết nối lại (backoff có trần) và
làm mới token trước khi hết hạn. Luồng im lặng > stream.silence_sec giây trong phiên → source_status 'degraded'
+ thông báo sự cố qua Telegram; có tin trở lại → 'ok'.
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import sys
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
        self.keep: Optional[set] = None          # mã lưu nguyên văn vào raw_stream (None = lưu mọi tin)
        self.state: Dict[str, Dict[str, Dict]] = {"trade": {}, "room": {}, "indexsummary": {}}

    def snapshot(self) -> Dict[str, Dict[str, Dict]]:
        with self.lock:
            return {k: dict(v) for k, v in self.state.items()}

    def on_data(self, msg: Any) -> None:
        row = to_row(msg)
        if row is None:
            return
        ch, sym = row["channel"], row["symbol"]
        if ch in self.state and sym:
            try:
                body = json.loads(row["payload"])
                body = body.get("data") if ch == "indexsummary" and isinstance(body.get("data"), dict) else body
                with self.lock:
                    self.state[ch][sym] = body
            except Exception:  # noqa: BLE001
                pass
        store = self.keep is None or ch in ("indexsummary", "trade.index", "market", "market.flag") or sym in self.keep
        if ch == "quote" and self.keep is not None:
            store = False
        with self.lock:
            self.n += 1
            self.last_msg = time.monotonic()
            if store:
                self.buf.append(row)
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
        log.info("Ngoài cửa sổ ghi %s–%s – không ghi luồng.", get("session.recorder_start"), get("session.recorder_end"))
        if symbols is None and now_vn().weekday() < 5 and now_vn().strftime("%H:%M") >= get("session.recorder_end", "15:05"):
            post_close_update()                       # máy bật sau giờ đóng cửa: vẫn tự lấy số liệu cuối ngày
        return {"messages": 0, "skipped": True}
    if seconds is None and not _claim_lock():
        log.info("Đã có bộ ghi luồng khác đang chạy hôm nay – thoát.")
        return {"messages": 0, "skipped": True, "reason": "running"}
    _keep_awake(True)                                  # máy không tự ngủ khi đang ghi luồng (Windows)
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
            live_on = bool(get("stream.live_build", True)) and symbols is None
            hose: List[str] = []
            if live_on:
                from ssi_sdk.enums import Board  # type: ignore
                from src.data import live
                hose = live.hose_symbols()
                rec.keep = set(syms)
                s.subscribe_board([Board.HOSE])                  # trade + quote cả sàn (chỉ giữ trạng thái mới nhất)
                for i in range(0, len(hose), 100):
                    s.subscribe_symbol_room(hose[i:i + 100])     # khối ngoại & room từng mã HOSE
            elif syms:
                s.subscribe_symbol_room(syms)
                s.subscribe_symbol_trade(syms)
            db.set_source_status("SSI", "ok", f"WebSocket V3 đã kết nối · {len(hose) or len(syms)} mã")
            log.info("Đang ghi luồng SSI V3: %d chỉ số, %d mã lưu nguyên văn, %d mã HOSE theo dõi trạng thái",
                     len(INDEXES), len(syms), len(hose))
            last_flush = time.monotonic()
            every = float(get("stream.live_build_sec", 120))
            last_build = time.monotonic() - every + 20          # lượt dựng đầu tiên sau ~20 giây nhận luồng
            builder: Optional[threading.Thread] = None

            def _build(force: bool = False) -> None:
                try:
                    from src.data import live
                    if force or in_session():
                        if live.build(rec.snapshot()):
                            _publish_live()
                except Exception as exc:  # noqa: BLE001 – lượt sau thử lại
                    log.warning("Dựng phiên tạm tính lỗi: %s", exc)

            try:
                while True:
                    time.sleep(2)
                    if time.monotonic() - last_flush > 10:
                        rec.flush()
                        last_flush = time.monotonic()
                    if live_on and time.monotonic() - last_build >= every and not (builder and builder.is_alive()):
                        builder = threading.Thread(target=_build, daemon=True)
                        builder.start()
                        last_build = time.monotonic()
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
                if live_on and t_end is None:            # lượt dựng cuối với giá chốt sau ATC
                    if builder and builder.is_alive():
                        builder.join(timeout=120)
                    _build(force=True)
                    if now_vn().strftime("%H:%M") >= get("session.close", "15:00"):
                        close_from_stream(rec.snapshot())  # chốt phiên vào kho chính → đủ kết quả trước 15:15
                try:
                    s.disconnect()
                except Exception:  # noqa: BLE001
                    pass
    by = db.query_df("SELECT channel, COUNT(*) n FROM raw_stream WHERE session_date = ? GROUP BY 1",
                     [now_vn().date()])
    out = {"messages": rec.n, "by_channel": dict(zip(by.get("channel", []), by.get("n", [])))}
    log.info("Kết thúc ghi luồng: %s", out)
    _keep_awake(False)
    if seconds is None and symbols is None:
        post_close_update()
    return out


def _keep_awake(on: bool) -> None:
    """Windows: SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) – chặn chế độ ngủ do không thao tác trong lúc
    tiến trình còn chạy (không chặn khi người dùng chủ động gập máy/ngủ). Máy ngủ giữa phiên làm luồng dừng và mất dữ liệu."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000001 if on else 0))
    except Exception:  # noqa: BLE001
        pass


def _claim_lock() -> bool:
    """Ghi data/.recorder.lock = 'ngày pid=…' (bộ ghi chạy từ Task Scheduler, app hoặc bot đều dùng chung một khóa)."""
    import os
    from src.data import autoupdate
    lock = autoupdate.REC_LOCK
    today = now_vn().strftime("%Y-%m-%d")
    try:
        if lock.exists():
            txt = lock.read_text(encoding="utf-8")
            pid = int(txt.split("pid=")[-1]) if "pid=" in txt else 0
            # pid trong khóa có thể là tiến trình CHA (python.exe của venv trên Windows là trình khởi chạy, tiến trình
            # Python thật là con của nó) → coi là chính mình
            if txt.startswith(today) and pid not in (os.getpid(), os.getppid()) and autoupdate._pid_alive(pid):
                return False
        lock.write_text(f"{today} pid={os.getpid()}", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("Không ghi được khóa bộ ghi: %s", exc)
    return True


def close_from_stream(state: Dict) -> Optional[Dict]:
    """15:05: ghi phiên chốt từ luồng WebSocket vào kho chính (nguồn SSI-WS) rồi tính lại toàn bộ chỉ báo + kiểm định
    (bỏ bảng độ vững để kịp 15:15). Bản REST chính thức của SSI thay thế sau đó (post_close_update)."""
    from src.data import live, rebuild_all, updater
    t0 = time.time()
    try:
        res = live.promote(state)
        if not res:
            return None
        with updater.update_lock():
            out = rebuild_all.main(robustness=False)
        log.info("Đã tính xong phiên %s từ số liệu chốt WebSocket trong %.0f giây (hash %s)", now_vn().date(),
                 time.time() - t0, out.get("hash"))
        return res
    except updater.Busy:
        log.warning("Đang có tiến trình cập nhật khác – bỏ qua chốt phiên từ luồng")
    except Exception as exc:  # noqa: BLE001
        log.warning("Chốt phiên từ luồng lỗi: %s", exc)
    return None


def _publish_live() -> None:
    """Đẩy số liệu tạm tính của hôm nay lên GitHub (mỗi ≥ 2 phút) – lỗi không làm dừng bộ ghi."""
    try:
        from tools.publish_data import publish_live
        r = publish_live()
        if r.get("state") not in ("wait", "disabled"):
            log.info("Đẩy số liệu trong phiên: %s", r)
    except Exception as exc:  # noqa: BLE001
        log.warning("Không đẩy được số liệu trong phiên: %s", exc)


def _publish() -> None:
    """Đẩy phần dữ liệu mới lên GitHub (tools/publish_data.py) – lỗi không làm dừng bộ ghi."""
    try:
        from tools.publish_data import auto_publish
        log.info("Đẩy dữ liệu lên GitHub: %s", auto_publish())
    except Exception as exc:  # noqa: BLE001
        log.warning("Không đẩy được dữ liệu lên GitHub: %s", exc)


def post_close_update(poll_sec: int = 90, until: str = "18:30") -> str:
    """Sau đóng cửa: hỏi SSI REST mỗi `poll_sec` giây, có số liệu chính thức của hôm nay thì tải và dựng lại ngay.

    Số liệu cuối ngày (securitiesSummary, indexSummary) SSI công bố sau giờ đóng cửa một khoảng không cố định; trong lúc
    chờ, web vẫn hiển thị phiên tạm tính với giá chốt sau ATC. Bản chính thức thay thế ngay khi dựng xong.
    """
    from src.data import updater
    from src.bot.intraday import _client
    today = now_vn().date()
    while now_vn().strftime("%H:%M") < until:
        try:
            if not updater.is_behind():
                _publish()
                return "up_to_date"
            c = _client()
            ready = bool(c.index_summary("VNINDEX", today)) and bool(c.securities_summary("FPT", today, today))
            if ready:
                log.info("SSI đã công bố số liệu cuối ngày %s – tải và dựng lại ngay", today)
                try:                                  # chạy ngay trong tiến trình này (không qua autoupdate: hàm đó
                    r = updater.update()              # thấy chính bộ ghi đang chạy nên sẽ bỏ qua)
                    log.info("Cập nhật cuối ngày xong: %s, dữ liệu tới %s", r.get("status"), r["after"]["indicators"])
                    _publish()                        # bản công khai trên mạng có phiên mới ngay
                    # SSI có thể điều chỉnh số cuối ngày sau đó → 18:05 tải lại phiên một lần (updater.refresh_recent)
                    while now_vn().strftime("%H:%M") < "18:05":
                        time.sleep(60)
                    r = updater.update()
                    log.info("Tải lại sau 18:00: %s", r.get("status"))
                    _publish()
                    return str(r.get("status"))
                except updater.Busy:                  # tiến trình khác đang cập nhật → chờ lượt sau
                    time.sleep(poll_sec)
                    continue
            log.info("SSI chưa có số liệu cuối ngày %s – thử lại sau %d giây", today, poll_sec)
        except Exception as exc:  # noqa: BLE001
            log.warning("Kiểm tra số liệu cuối ngày lỗi: %s", exc)
        time.sleep(poll_sec)
    return "timeout"


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
