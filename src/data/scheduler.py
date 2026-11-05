"""
Lịch tự động (bước B9.2b) – vòng lặp đơn giản, giờ Việt Nam, thứ 2–6:

  11:35  bản tin giữa phiên + Market Snapshot
  15:05  cập nhật cuối phiên (backfill phiên hôm nay nếu có khóa SSI) → tính lại chỉ báo
  15:10  kiểm tra chất lượng
  15:15  xuất Closing Report (chỉ khi qua kiểm tra) + gửi Telegram; ghi reports_log
  mỗi 5 phút trong phiên: đánh giá cảnh báo (cooldown 30 phút, tối đa 5/ngày)

    python -m src.data.scheduler            # chạy liên tục
    python -m src.data.scheduler --once closing   # chạy một tác vụ ngay
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime
from typing import Callable, Dict

from src.common.config import get, is_demo
from src.common.logging import get_logger
from src.common.timeutil import in_session, now_vn

log = get_logger(__name__)


def task_close_update() -> Dict:
    from src.data import build_facts
    from src.analytics import pipeline
    if not is_demo():
        from src.data import backfill
        from src.ssi_api.ssi_client import SSIClient
        c = SSIClient()
        today = now_vn().date()
        backfill.stocks(c, today, today)
        backfill.indexes(c, today, today)
    build_facts.build_all()
    pipeline.compute()
    return {"ok": True}


def task_quality() -> Dict:
    from src.data import quality
    return quality.run()


def task_closing() -> Dict:
    from src.bot import jobs
    return jobs.closing_brief()


def task_midday() -> Dict:
    from src.bot import jobs
    return jobs.midday_brief()


def task_alerts() -> Dict:
    from src.bot import jobs
    return {"sent": jobs.run_alerts()}


TASKS: Dict[str, Callable[[], Dict]] = {"midday": task_midday, "close_update": task_close_update,
                                        "quality": task_quality, "closing": task_closing, "alerts": task_alerts}


def schedule() -> Dict[str, str]:
    s = get("schedule")
    return {s["midday_brief"]: "midday", s["close_update"]: "close_update", s["quality_check"]: "quality",
            s["closing_report"]: "closing"}


def run_forever() -> None:
    done = set()
    last_alert = 0.0
    log.info("Bộ lập lịch chạy: %s", schedule())
    while True:
        now = now_vn()
        key_day = now.strftime("%Y-%m-%d")
        if now.weekday() < 5:
            hm = now.strftime("%H:%M")
            for t, name in schedule().items():
                if hm >= t and (key_day, name) not in done:
                    try:
                        log.info("Chạy tác vụ %s: %s", name, TASKS[name]())
                    except Exception as exc:  # noqa: BLE001
                        log.error("Tác vụ %s lỗi: %s", name, exc)
                    done.add((key_day, name))
            if in_session(now) and time.time() - last_alert > 300:
                try:
                    task_alerts()
                except Exception as exc:  # noqa: BLE001
                    log.error("Cảnh báo lỗi: %s", exc)
                last_alert = time.time()
        time.sleep(20)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", choices=list(TASKS))
    a = ap.parse_args()
    if a.once:
        print(TASKS[a.once]())
    else:
        run_forever()
