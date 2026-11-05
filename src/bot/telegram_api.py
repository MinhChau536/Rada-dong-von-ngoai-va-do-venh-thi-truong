"""
Gửi tin Telegram qua Bot HTTP API (dùng cho bản tin theo lịch và cảnh báo – bước B10.3).
Token & chat_id đọc từ .env; KHÔNG ghi ra log (mask_secrets). Chỉ gửi tới TELEGRAM_CHAT_IDS đã đăng ký.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import requests

from src.common.config import env, get
from src.common.logging import get_logger

log = get_logger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"


def token() -> Optional[str]:
    t = env("TELEGRAM_BOT_TOKEN")
    return t if t and not t.startswith("123456:") else None


def chat_ids() -> List[str]:
    raw = env("TELEGRAM_CHAT_IDS", "") or ""
    return [c.strip() for c in raw.split(",") if c.strip() and not c.strip().startswith("111111")]


def configured() -> bool:
    return bool(token() and chat_ids())


def with_disclaimer(text: str) -> str:
    d = get("app.bot_disclaimer")
    return text if d in text else f"{text}\n\n— {d}"


def send_message(text: str, ids: Optional[List[str]] = None) -> bool:
    if not configured():
        log.info("Telegram chưa cấu hình – bỏ qua gửi tin")
        return False
    ok = True
    for cid in ids or chat_ids():
        try:
            r = requests.post(API.format(token=token(), method="sendMessage"),
                              data={"chat_id": cid, "text": with_disclaimer(text)[:4000]}, timeout=15)
            ok &= r.ok
            if not r.ok:
                log.warning("Telegram sendMessage lỗi %s: %s", r.status_code, r.text[:200])
        except requests.RequestException as exc:
            log.warning("Telegram lỗi mạng: %s", exc)
            ok = False
    return ok


def send_document(path: Path, caption: str = "", ids: Optional[List[str]] = None) -> bool:
    if not configured():
        return False
    ok = True
    for cid in ids or chat_ids():
        try:
            with open(path, "rb") as f:
                r = requests.post(API.format(token=token(), method="sendDocument"),
                                  data={"chat_id": cid, "caption": with_disclaimer(caption)[:1000]},
                                  files={"document": (Path(path).name, f, "application/pdf")}, timeout=60)
            ok &= r.ok
        except (requests.RequestException, OSError) as exc:
            log.warning("Telegram sendDocument lỗi: %s", exc)
            ok = False
    return ok
