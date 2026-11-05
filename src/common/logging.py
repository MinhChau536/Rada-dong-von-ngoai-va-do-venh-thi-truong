"""
Nhật ký hệ thống dùng chung (bước B1.12).

Định dạng: 'thời gian VN | mức | module | thông điệp', ghi ra logs/app.log xoay vòng 5 MB.
Bộ lọc SecretFilter che mọi token, mật khẩu, ConsumerSecret trước khi ghi (mask_secrets).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

from src.common.config import abs_path, get

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
_SECRET_ENV = ("SSI_CONSUMER_ID", "SSI_CONSUMER_SECRET", "NEO_USERNAME", "NEO_PASSWORD",
               "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_IDS")
_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-_\.=]+"),
    re.compile(r'(?i)("?(?:access_?token|accessToken|token|consumerSecret|consumer_secret|password|secret|jwt)"?\s*[:=]\s*"?)([^",\s}]+)'),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b"),            # dạng token bot Telegram
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWT
]


def mask_secrets(text: str) -> str:
    """Che bí mật trong chuỗi: giá trị biến môi trường nhạy cảm + mẫu token/JWT/mật khẩu."""
    if not text:
        return text
    s = str(text)
    for name in _SECRET_ENV:
        val = os.getenv(name)
        if val and len(val) >= 4 and not val.startswith("your_"):
            s = s.replace(val, "***")
    s = _PATTERNS[0].sub(r"\1***", s)
    s = _PATTERNS[1].sub(r"\1***", s)
    s = _PATTERNS[2].sub("***", s)
    s = _PATTERNS[3].sub("***", s)
    return s


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = mask_secrets(record.getMessage())
            record.args = ()
        except Exception:  # pragma: no cover
            pass
        return True


class VNFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):  # noqa: N802
        return datetime.fromtimestamp(record.created, VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


_configured = False


def setup_logging(level: str | None = None) -> None:
    global _configured
    if _configured:
        return
    lvl = getattr(logging, (level or os.getenv("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    fmt = VNFormatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    root = logging.getLogger("ffr")
    root.setLevel(lvl)
    root.propagate = False
    log_file = abs_path(get("paths.log_file", "logs/app.log"))
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.addFilter(SecretFilter())
        root.addHandler(fh)
    except OSError:  # pragma: no cover - ổ chỉ đọc
        pass
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:  # cửa sổ lệnh Windows mặc định cp1252 → tránh lỗi in tiếng Việt
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover
            pass
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.addFilter(SecretFilter())
    root.addHandler(sh)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    short = name.replace("src.", "")
    return logging.getLogger(f"ffr.{short}")
