"""
Lịch tự động (bước B9.2b) – vòng lặp giờ Việt Nam, thứ 2–6:

  khởi động  nếu kho chậm hơn phiên đã đóng gần nhất → TẢI BÙ + dựng lại ngay (máy tắt nhiều ngày vẫn đủ dữ liệu)
  08:55      bật bộ ghi luồng WebSocket SSI FastConnect V3 (tự dừng 15:05) – chỉ khi còn trong phiên
  11:35      bản tin giữa phiên + Market Snapshot – chỉ đến 13:00
  15:05      cập nhật: tải bù mọi phiên thiếu từ SSI (REST) → fact → chỉ báo → kiểm định → triển vọng thống kê
             (lỗi API → thử lại mỗi 30 phút đến 20:00)
             (kiểm tra chất lượng chạy ngay trong bước này)
  15:15      xuất Closing Report (chỉ khi qua kiểm tra VÀ đã có dữ liệu phiên hôm nay; chưa có → thử lại mỗi 30 phút
             đến 21:00) + gửi Telegram; ghi reports_log
  mỗi 5 phút trong phiên: đánh giá cảnh báo (cooldown 30 phút, tối đa 5/ngày)
  22:00      lượt cập nhật dự phòng (bắt phiên SSI công bố muộn, mã lỗi lúc 15:05)

Ngày lễ rơi vào thứ 2–6: SSI không có phiên → không xuất báo cáo cũ, chỉ ghi "không có phiên".

    python -m src.data.scheduler                    # chạy liên tục
    python -m src.data.scheduler --once update      # chạy một tác vụ ngay
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List

from src.common.config import get, ssi_configured
from src.common.logging import get_logger
from src.common.timeutil import in_session, now_vn

log = get_logger(__name__)


def _has_session_today() -> bool:
    from src.reports.context import latest_date
    d = latest_date()
    return d is not None and d.date() == now_vn().date()


def task_update() -> Dict:
    """Tải bù từ SSI + dựng lại toàn bộ chỉ báo/kiểm định khi có phiên mới (src.data.updater)."""
    from src.data import updater
    return updater.update()


def task_recorder() -> Dict:
    """8:55 – ghi luồng WebSocket SSI V3 đến 15:05 (luồng nền để không chặn các tác vụ khác)."""
    import threading
    from src.data import recorder_ssi
    t = threading.Thread(target=recorder_ssi.run, name="ssi-recorder", daemon=True)
    t.start()
    return {"started": True}


def task_quality() -> Dict:
    from src.data import quality
    return quality.run()


class NotReady(RuntimeError):
    """Chưa đủ điều kiện chạy (chưa có dữ liệu phiên hôm nay) – thử lại sau."""


def task_closing() -> Dict:
    if not _has_session_today():
        raise NotReady("chưa có dữ liệu phiên hôm nay (chờ cập nhật, hoặc hôm nay nghỉ lễ) – không gửi báo cáo cũ")
    from src.bot import jobs
    return jobs.closing_brief()


def task_midday() -> Dict:
    from src.bot import jobs
    return jobs.midday_brief()


def task_alerts() -> Dict:
    from src.bot import jobs
    return {"sent": jobs.run_alerts()}


TASKS: Dict[str, Callable[[], Dict]] = {"recorder": task_recorder, "midday": task_midday, "update": task_update,
                                        "close_update": task_update, "quality": task_quality,
                                        "closing": task_closing, "alerts": task_alerts}


@dataclass
class Job:
    name: str
    start: str           # HH:MM – sớm nhất được chạy
    until: str           # HH:MM – quá giờ này không chạy nữa (khởi động muộn không chạy tác vụ đã lỡ)
    retry_min: int = 0   # > 0: lỗi thì thử lại sau N phút (đến `until`)


def jobs() -> List[Job]:
    s = get("schedule")
    return [Job("recorder", get("session.recorder_start", "08:55"), get("session.recorder_end", "15:05")),
            Job("midday", s["midday_brief"], s.get("midday_until", "13:00")),
            Job("update", s["close_update"], s.get("update_until", "20:00"), int(s.get("update_retry_min", 30))),
            # kiểm tra chất lượng đã nằm trong update (rebuild_all) – không chạy riêng để khỏi tranh khóa DuckDB
            Job("closing", s["closing_report"], s.get("closing_until", "21:00"), int(s.get("update_retry_min", 30))),
            Job("update_late", s.get("late_update", "22:00"), "23:59", int(s.get("update_retry_min", 30)))]


def run_job(job: Job) -> bool:
    fn = TASKS["update" if job.name == "update_late" else job.name]
    try:
        log.info("Chạy tác vụ %s: %s", job.name, fn())
        return True
    except Exception as exc:  # noqa: BLE001
        from src.data.updater import Busy
        if isinstance(exc, (Busy, NotReady)):
            log.info("Tác vụ %s: %s – thử lại sau", job.name, exc)
        else:
            log.error("Tác vụ %s lỗi: %s", job.name, exc)
        return False


def catch_up_on_start() -> None:
    """Khởi động: nếu kho chậm hơn phiên đã đóng gần nhất → tải bù ngay (kể cả cuối tuần)."""
    from src.data import updater
    if not ssi_configured():
        log.warning("Thiếu khóa SSI – bỏ qua tải bù khi khởi động")
        return
    try:
        if updater.is_behind():
            log.info("Kho đang chậm (%s) – tải bù ngay", updater.coverage())
            updater.update()
        else:
            log.info("Kho đã cập nhật tới %s", updater.coverage()["indicators"])
    except Exception as exc:  # noqa: BLE001
        log.error("Tải bù khi khởi động lỗi: %s", exc)


def run_forever(tick: int = 20) -> None:
    done: set = set()
    next_try: Dict[tuple, float] = {}
    last_alert = 0.0
    log.info("Bộ lập lịch chạy: %s", [(j.name, j.start, j.until) for j in jobs()])
    catch_up_on_start()
    while True:
        now: datetime = now_vn()
        day = now.strftime("%Y-%m-%d")
        if now.weekday() < 5:
            hm = now.strftime("%H:%M")
            for job in jobs():
                key = (day, job.name)
                if key in done or not (job.start <= hm <= job.until) or time.time() < next_try.get(key, 0):
                    continue
                ok = run_job(job)
                if ok or not job.retry_min:
                    done.add(key)
                else:
                    next_try[key] = time.time() + job.retry_min * 60
            if in_session(now) and time.time() - last_alert > 300:
                try:
                    task_alerts()
                except Exception as exc:  # noqa: BLE001
                    log.error("Cảnh báo lỗi: %s", exc)
                last_alert = time.time()
        done = {k for k in done if k[0] == day}            # không giữ khóa ngày cũ
        time.sleep(tick)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", choices=list(TASKS))
    a = ap.parse_args()
    if a.once:
        print(TASKS[a.once]())
    else:
        run_forever()
