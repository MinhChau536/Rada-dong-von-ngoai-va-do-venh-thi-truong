"""Trạng thái tiến trình bot cho giao diện web: bot ghi PID khi khởi động (data/.bot.pid), trang Bot Telegram đọc lại.

Không gọi getUpdates để dò bot – lệnh đó sẽ cắt kết nối long-polling của bot đang chạy.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Dict, Optional

import requests

from src.bot.telegram_api import API, token
from src.common.config import abs_path

PID_FILE = abs_path("data/.bot.pid")


def write_pid() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(json.dumps({"pid": os.getpid(), "started": datetime.now().isoformat(timespec="seconds")}),
                        encoding="utf-8")


def clear_pid() -> None:
    try:
        if PID_FILE.exists() and json.loads(PID_FILE.read_text(encoding="utf-8")).get("pid") == os.getpid():
            PID_FILE.unlink()
    except (OSError, ValueError):
        pass


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":                 # os.kill trên Windows sẽ DỪNG tiến trình → dùng WinAPI chỉ đọc
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259    # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def bot_process() -> Optional[Dict]:
    """{'pid', 'started'} nếu bot (python -m src.bot.bot) đang chạy trên máy này, ngược lại None."""
    try:
        info = json.loads(PID_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return info if pid_alive(int(info.get("pid", 0))) else None


def get_me() -> Optional[Dict]:
    """Thông tin bot (username, tên) qua getMe – không ảnh hưởng bot đang chạy."""
    if not token():
        return None
    try:
        r = requests.get(API.format(token=token(), method="getMe"), timeout=8)
        return r.json().get("result") if r.ok else None
    except requests.RequestException:
        return None
