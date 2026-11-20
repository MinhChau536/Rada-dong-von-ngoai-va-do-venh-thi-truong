"""
Tự cập nhật phiên mới mỗi khi chạy dự án (app Streamlit, bot Telegram).

Khi khởi động – và định kỳ trong lúc app chạy – nếu kho chỉ báo chưa có phiên đã đóng cửa gần nhất
(updater.is_behind()) thì chạy `python -m src.data.updater` ở TIẾN TRÌNH NỀN: app vẫn mở ngay, số liệu mới hiện
sau khi tải xong. Khóa data/.update.lock của updater bảo đảm không bao giờ có hai lần cập nhật chồng nhau
(app + bot + bộ lập lịch cùng chạy vẫn an toàn).

    from src.data import autoupdate
    info = autoupdate.start_if_behind()     # {"state": "started" | "running" | "up_to_date" | "no_key" | "error", ...}
"""
from __future__ import annotations

import subprocess
import sys
from typing import Dict, Optional

from src.common.config import ROOT, abs_path, ssi_configured
from src.common.logging import get_logger

log = get_logger(__name__)
LOG_FILE = abs_path("logs/job_autoupdate.log")


def running() -> bool:
    """Đang có một lần cập nhật khác giữ khóa (tiến trình nền, bộ lập lịch, nút trên trang Kết nối dữ liệu)."""
    from src.data.updater import LOCK, STALE_LOCK_SEC
    import time
    return LOCK.exists() and time.time() - LOCK.stat().st_mtime <= STALE_LOCK_SEC


def start_if_behind() -> Dict:
    if not ssi_configured():
        return {"state": "no_key"}
    try:
        from src.data import updater
        if running():
            return {"state": "running"}
        if recorder_alive():                     # bộ ghi luồng đang chạy: nó tự chốt phiên lúc 15:05 và tự lấy bản REST
            return {"state": "recorder"}
        cov = updater.coverage()
        if not updater.is_behind():
            return {"state": "up_to_date", "last": cov["indicators"]}
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        fh = open(LOG_FILE, "a", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, "-m", "src.data.updater"], cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log.info("Tự cập nhật: kho tới %s, phiên đã đóng cửa gần nhất %s – tải bù ở tiến trình nền (pid %s)",
                 cov["indicators"], cov["expected_last_session"], proc.pid)
        return {"state": "started", "proc": proc, "from": cov["indicators"], "to": cov["expected_last_session"]}
    except Exception as exc:  # noqa: BLE001 – không để việc tự cập nhật làm hỏng app/bot
        log.warning("Tự cập nhật không khởi động được: %s", exc)
        return {"state": "error", "error": str(exc)}


def finished(info: Optional[Dict]) -> Optional[int]:
    """Mã thoát của tiến trình nền đã khởi động (None nếu chưa xong hoặc không có tiến trình)."""
    p = (info or {}).get("proc")
    return None if p is None else p.poll()


# ── Bộ ghi luồng WebSocket SSI V3: tự bật khi app/bot đang chạy trong giờ giao dịch ──────────────────────────────
REC_LOCK = abs_path("data/.recorder.lock")
REC_LOG = abs_path("logs/job_recorder.log")


def _in_session(now=None) -> bool:
    from datetime import datetime
    from src.common.config import get
    from src.common.timeutil import now_vn
    now = now or now_vn()
    if now.weekday() >= 5:
        return False
    t = now.strftime("%H:%M")
    return get("session.recorder_start", "08:55") <= t < get("session.recorder_end", "15:05")


def _pid_alive(pid: int) -> bool:
    """Tiến trình còn sống không (không gửi tín hiệu nào tới tiến trình)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259            # STILL_ACTIVE
    import os
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def recorder_alive() -> bool:
    """Có bộ ghi luồng (Task Scheduler / app / bot) đang chạy trong ngày hôm nay."""
    from src.common.timeutil import now_vn
    try:
        if not REC_LOCK.exists():
            return False
        txt = REC_LOCK.read_text(encoding="utf-8")
        pid = int(txt.split("pid=")[-1]) if "pid=" in txt else 0
        return txt.startswith(now_vn().strftime("%Y-%m-%d")) and _pid_alive(pid)
    except Exception:  # noqa: BLE001
        return False


def start_recorder_if_session() -> Dict:
    """Bật `python -m src.data.recorder_ssi` (ghi tới hết phiên) nếu đang trong giờ và hôm nay chưa có bộ ghi nào chạy."""
    from src.common.timeutil import now_vn
    if not ssi_configured():
        return {"state": "no_key"}
    if not _in_session():
        return {"state": "off_hours"}
    today = now_vn().strftime("%Y-%m-%d")
    try:
        if REC_LOCK.exists():
            txt = REC_LOCK.read_text(encoding="utf-8")
            pid = int(txt.split("pid=")[-1]) if "pid=" in txt else 0
            if txt.startswith(today) and _pid_alive(pid):
                return {"state": "running", "pid": pid}
            if txt.startswith(today):
                log.warning("Bộ ghi luồng (pid %s) đã dừng giữa phiên – bật lại", pid)
        REC_LOG.parent.mkdir(parents=True, exist_ok=True)
        fh = open(REC_LOG, "a", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, "-m", "src.data.recorder_ssi"], cwd=str(ROOT), stdout=fh,
                                stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        REC_LOCK.write_text(f"{today} pid={proc.pid}", encoding="utf-8")
        log.info("Tự bật bộ ghi luồng WebSocket SSI V3 (pid %s) tới hết phiên", proc.pid)
        return {"state": "started", "pid": proc.pid}
    except Exception as exc:  # noqa: BLE001
        log.warning("Không bật được bộ ghi luồng: %s", exc)
        return {"state": "error", "error": str(exc)}
