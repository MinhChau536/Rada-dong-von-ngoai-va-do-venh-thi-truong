"""
Cập nhật dữ liệu liên tục từ SSI FastConnect V3 (REST) – dùng cho bộ lập lịch và chạy tay.

Mỗi lần chạy:
  1. Tải BÙ mọi phiên còn thiếu: từ điểm dừng (checkpoints) đến phiên đã đóng cửa gần nhất – máy tắt nhiều ngày
     vẫn tự lấp đủ; mã lỗi được tải lại ở lần sau (backfill không ghi điểm dừng khi còn mã lỗi).
     Vá phiên gần đây (10 phiên) mà SSI để trống khối ngoại cho mọi mã: tải lại mỗi lần chạy cho đến khi SSI bổ sung.
  2. Nếu có phiên mới (hoặc kho chỉ báo đang chậm hơn raw): dựng lại toàn bộ fact → chỉ báo → kiểm tra chất lượng →
     kiểm định (H1–H4, sự kiện, DiD, độ vững) → backtest cảnh báo → triển vọng thống kê dùng trong báo cáo.
  3. Ghi trạng thái vào logs/last_update.json và source_status.

Khóa tệp data/.update.lock ngăn hai tiến trình cùng ghi DuckDB (khóa quá 3 giờ coi là treo và được gỡ).

    python -m src.data.updater              # tải bù + dựng lại nếu có phiên mới
    python -m src.data.updater --force      # luôn dựng lại
    python -m src.data.updater --status     # xem dữ liệu đang tới phiên nào
"""
from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from datetime import date
from typing import Dict, Iterator, List, Optional

import pandas as pd

from src.common.config import abs_path, get, ssi_configured
from src.common.logging import get_logger
from src.common.timeutil import now_vn
from src.data import database as db

log = get_logger(__name__)

LOCK = abs_path("data/.update.lock")
STATUS = abs_path("logs/last_update.json")
STALE_LOCK_SEC = 3 * 3600


class Busy(RuntimeError):
    """Một lần cập nhật khác đang chạy."""


@contextmanager
def update_lock() -> Iterator[None]:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime > STALE_LOCK_SEC:
        log.warning("Gỡ khóa cập nhật treo (%s)", LOCK.read_text(encoding="utf-8", errors="ignore").strip())
        LOCK.unlink(missing_ok=True)
    try:
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise Busy(f"Đang có tiến trình cập nhật khác ({LOCK.read_text(encoding='utf-8', errors='ignore').strip()})") from exc
    try:
        os.write(fd, f"pid={os.getpid()} start={now_vn():%Y-%m-%d %H:%M:%S}".encode())
        os.close(fd)
        yield
    finally:
        LOCK.unlink(missing_ok=True)


def _max_date(sql: str) -> Optional[date]:
    try:
        df = db.query_df(sql)
    except Exception:  # noqa: BLE001 – bảng chưa tồn tại
        return None
    v = None if df.empty else df.iloc[0, 0]
    return None if v is None or pd.isna(v) else pd.Timestamp(v).date()


def coverage() -> Dict[str, Optional[str]]:
    """Dữ liệu đang tới phiên nào ở từng tầng + phiên đã đóng cửa gần nhất theo lịch."""
    from src.data.backfill import last_closed_session
    f = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"raw_stock": f(_max_date("SELECT MAX(trade_date) FROM raw_daily_stock WHERE source = 'SSI'")),   # chỉ bản REST
            "raw_index": f(_max_date("SELECT MAX(trade_date) FROM raw_daily_index WHERE source = 'SSI'")),     # chính thức
            "indicators": f(_max_date("SELECT MAX(trade_date) FROM indicator_daily")),
            "stats_computed": f(_max_date("SELECT MAX(computed_at) FROM pipeline_meta")),
            "expected_last_session": last_closed_session().isoformat()}


def is_behind() -> bool:
    """Kho chỉ báo chưa có phiên đã đóng cửa gần nhất (bỏ qua ngày lễ: so với raw đã tải)."""
    c = coverage()
    # chỉ báo đã có phiên mới nhưng dựng từ bản tạm tính WebSocket (SSI-WS) → vẫn coi là thiếu để tải bản REST chính thức
    return (c["indicators"] is None or c["raw_stock"] is None or c["indicators"] < c["expected_last_session"]
            or c["raw_stock"] < c["expected_last_session"])


def foreign_gaps(lookback: int = 10) -> List[date]:
    """Phiên trong `lookback` phiên gần nhất mà raw không có khối ngoại cho mã nào (SSI chưa công bố / lỗi nguồn)."""
    df = db.query_df(
        "WITH s AS (SELECT DISTINCT trade_date FROM raw_daily_stock ORDER BY trade_date DESC LIMIT ?) "
        "SELECT r.trade_date, COUNT(*) AS n, "
        "SUM(CASE WHEN json_extract_string(r.payload, '$.totalForeignBuyValue') IS NOT NULL THEN 1 ELSE 0 END) AS k "
        "FROM raw_daily_stock r JOIN s USING (trade_date) GROUP BY 1", [lookback])
    if df.empty:
        return []
    return sorted(pd.Timestamp(d).date() for d in df.loc[(df["n"] >= 50) & (df["k"] == 0), "trade_date"])


def repair_recent_gaps(lookback: int | None = None) -> Dict:
    """Tải lại (không dùng điểm dừng) các phiên gần đây SSI để trống khối ngoại – SSI có thể bổ sung sau."""
    from src.data import backfill
    from src.ssi_api.ssi_client import SSIClient
    lookback = int(get("update.repair_lookback", 10) if lookback is None else lookback)
    gaps = foreign_gaps(lookback)
    if not gaps:
        return {"gaps": []}
    c = SSIClient()
    for d in gaps:
        backfill.stocks(c, d, d, use_checkpoint=False)
    still = foreign_gaps(lookback)
    fixed = [d for d in gaps if d not in still]
    log.info("Vá khối ngoại: %d phiên thiếu %s → đã có %s, vẫn thiếu %s", len(gaps), gaps, fixed, still)
    return {"gaps": [str(d) for d in gaps], "fixed": [str(d) for d in fixed], "still_missing": [str(d) for d in still]}


def _write_status(rec: Dict) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(rec, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


REFRESH_AFTER = "18:00"   # SSI có thể điều chỉnh số cuối ngày trong vài giờ sau đóng cửa (vd. VN30 20/11: −1,61 → −1,67)


def refresh_recent() -> bool:
    """Tải lại phiên REST gần nhất nếu bản đang lưu được tải TRƯỚC 18:00 của chính ngày đó (có thể là số sơ bộ).
    Mỗi phiên chỉ tải lại tới khi có một bản tải sau 18:00. Trả True nếu đã tải lại."""
    from src.data import backfill
    from src.ssi_api.ssi_client import SSIClient
    try:
        df = db.query_df("SELECT trade_date, MAX(loaded_at) AS t FROM raw_daily_index WHERE source = 'SSI' "
                         "GROUP BY 1 ORDER BY 1 DESC LIMIT 1")
    except Exception:  # noqa: BLE001
        return False
    if df.empty:
        return False
    d, t = pd.Timestamp(df["trade_date"].iat[0]).date(), pd.Timestamp(df["t"].iat[0])
    cutoff = pd.Timestamp(f"{d} {REFRESH_AFTER}")
    if t >= cutoff or now_vn().replace(tzinfo=None) < cutoff:
        return False
    log.info("Tải lại phiên %s (bản lưu lúc %s có thể là số sơ bộ của SSI)", d, f"{t:%H:%M}")
    c = SSIClient()
    backfill.stocks(c, d, d, use_checkpoint=False)
    backfill.indexes(c, d, d, use_checkpoint=False)
    return True


def update(force: bool = False, robustness: bool = True) -> Dict:
    """Tải bù từ SSI rồi dựng lại khi có dữ liệu mới. Ném Busy nếu đang có lần cập nhật khác."""
    if not ssi_configured():
        raise RuntimeError("Thiếu SSI_API_KEY / SSI_API_SECRET trong .env")
    t0 = time.time()
    rec: Dict = {"started": now_vn().strftime("%Y-%m-%d %H:%M:%S")}
    with update_lock():
        from src.data import backfill, rebuild_all
        db.init_schema()
        before = coverage()
        rec["before"] = before
        try:
            rec["fetched"] = backfill.main()        # điểm dừng → chỉ tải phần còn thiếu
        except Exception as exc:
            rec.update(status="error", error=str(exc)[:500], seconds=round(time.time() - t0, 1))
            _write_status(rec)
            try:
                from src.bot.jobs import data_incident
                data_incident(f"SSI lỗi khi cập nhật dữ liệu: {exc}"[:300])
            except Exception:  # noqa: BLE001 – Telegram không bắt buộc
                pass
            raise
        rec["repaired"] = repair_recent_gaps()
        rec["refreshed"] = refresh_recent()
        # Phiên đã có bản REST chính thức → xóa bản tạm tính chốt từ luồng WebSocket (SSI-WS) của phiên đó
        for t in ("raw_daily_stock", "raw_daily_index"):
            db.execute(f"DELETE FROM {t} WHERE source = 'SSI-WS' AND trade_date IN "
                       f"(SELECT DISTINCT trade_date FROM {t} WHERE source = 'SSI')")
        mid = coverage()
        new_raw = (mid["raw_stock"] != before["raw_stock"] or mid["raw_index"] != before["raw_index"]
                   or bool(rec["repaired"].get("fixed")) or bool(rec["refreshed"]))
        stale = mid["indicators"] is None or (mid["raw_stock"] or "") > (mid["indicators"] or "")
        if force or new_raw or stale:
            res = rebuild_all.main(robustness=robustness)
            rec["rebuild"] = {k: v for k, v in res.items() if k in ("hash", "seconds", "quality")}
            rec["status"] = "updated"
        else:
            rec["status"] = "up_to_date"
            log.info("Không có phiên mới (raw tới %s) – bỏ qua dựng lại", mid["raw_stock"])
        rec["after"] = coverage()
        rec["seconds"] = round(time.time() - t0, 1)
        _write_status(rec)
        log.info("Cập nhật %s: dữ liệu tới %s (%.0f giây)", rec["status"], rec["after"]["indicators"], rec["seconds"])
        return rec


def last_status() -> Dict:
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Luôn dựng lại chỉ báo và kiểm định")
    ap.add_argument("--no-robustness", action="store_true")
    ap.add_argument("--status", action="store_true", help="Chỉ in dữ liệu đang tới phiên nào")
    a = ap.parse_args()
    if a.status:
        print(json.dumps({"coverage": coverage(), "behind": is_behind(), "last_update": last_status()},
                         ensure_ascii=False, indent=2, default=str))
    else:
        print(json.dumps(update(a.force, not a.no_robustness), ensure_ascii=False, indent=2, default=str))
