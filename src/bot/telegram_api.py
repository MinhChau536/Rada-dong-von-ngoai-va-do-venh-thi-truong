"""
Gửi tin Telegram qua Bot HTTP API (dùng cho bản tin theo lịch và cảnh báo – bước B10.3).
Token & chat_id đọc từ .env; KHÔNG ghi ra log (mask_secrets). Chỉ gửi tới TELEGRAM_CHAT_IDS đã đăng ký.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

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


def keyboard_json(kb: Optional[Sequence[Sequence[Tuple[str, str]]]]) -> Optional[str]:
    """[[(nhãn, callback_data), ...], ...] → reply_markup inline_keyboard (nút chỉ phản hồi khi src.bot.bot đang chạy)."""
    if not kb:
        return None
    return json.dumps({"inline_keyboard": [[{"text": t, "callback_data": c[:64]} for t, c in row] for row in kb if row]},
                      ensure_ascii=False)


def send_message(text: str, ids: Optional[List[str]] = None, html: bool = False,
                 keyboard: Optional[Sequence[Sequence[Tuple[str, str]]]] = None) -> bool:
    """html=True: text dùng thẻ HTML của Telegram (<b>, <i>, <code>) – nội dung động phải được escape trước."""
    if not configured():
        log.info("Telegram chưa cấu hình – bỏ qua gửi tin")
        return False
    ok = True
    body = with_disclaimer(text)
    if html:
        body = body.replace(f"— {get('app.bot_disclaimer')}", f"<i>— {get('app.bot_disclaimer')}</i>")
    for cid in ids or chat_ids():
        data = {"chat_id": cid, "text": body[:4000]}
        if html:
            data["parse_mode"] = "HTML"
        mk = keyboard_json(keyboard)
        if mk:
            data["reply_markup"] = mk
        try:
            r = requests.post(API.format(token=token(), method="sendMessage"), data=data, timeout=15)
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
