"""
Bot Telegram (bước B10.1–B10.2) – python-telegram-bot.

    python -m src.bot.bot

Lệnh: /market /leaders /foreign /watch [mã] /report /status /help. Chỉ phản hồi chat_id trong TELEGRAM_CHAT_IDS.
Mọi tin kết thúc bằng câu miễn trừ "Thông tin phân tích, không phải khuyến nghị giao dịch". Không có lệnh đặt lệnh.
"""
from __future__ import annotations

import sys
from pathlib import Path

from src.bot import messages as M
from src.bot.telegram_api import chat_ids, token, with_disclaimer
from src.common.logging import get_logger

log = get_logger(__name__)


def main() -> None:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes

    if not token():
        print("Thiếu TELEGRAM_BOT_TOKEN trong .env (tạo bot qua @BotFather).")
        sys.exit(1)
    allowed = set(chat_ids())

    def guard(fn):
        async def wrap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            cid = str(update.effective_chat.id)
            if allowed and cid not in allowed:
                log.warning("Từ chối chat_id không đăng ký")
                return
            try:
                await fn(update, ctx)
            except Exception as exc:  # noqa: BLE001
                log.error("Lỗi lệnh bot: %s", exc)
                await update.message.reply_text(with_disclaimer(f"Không xử lý được yêu cầu: {exc}"))
        return wrap

    async def reply(update, text):
        await update.message.reply_text(with_disclaimer(text))

    @guard
    async def start(update, ctx):
        await reply(update, "Xin chào! " + M.HELP)

    @guard
    async def help_(update, ctx):
        await reply(update, M.HELP)

    @guard
    async def market(update, ctx):
        await reply(update, M.market())

    @guard
    async def leaders(update, ctx):
        await reply(update, M.leaders())

    @guard
    async def foreign(update, ctx):
        await reply(update, M.foreign())

    @guard
    async def watch(update, ctx):
        await reply(update, M.watch(ctx.args[0] if ctx.args else None))

    @guard
    async def status(update, ctx):
        await reply(update, M.status())

    @guard
    async def report(update, ctx):
        p = M.latest_report()
        if not p or not Path(p).exists():
            await reply(update, "Chưa có báo cáo PDF – xuất ở trang 'Báo cáo & Telegram'.")
            return
        with open(p, "rb") as f:
            await update.message.reply_document(f, caption=with_disclaimer(Path(p).name))

    app = Application.builder().token(token()).build()
    for name, fn in (("start", start), ("help", help_), ("market", market), ("leaders", leaders), ("foreign", foreign),
                     ("watch", watch), ("status", status), ("report", report)):
        app.add_handler(CommandHandler(name, fn))
    log.info("Bot Telegram đang chạy (%d chat_id được phép)", len(allowed))
    app.run_polling()


if __name__ == "__main__":
    main()
