"""
Bot Telegram (bước B10.1–B10.2) – python-telegram-bot, giao diện nút bấm + thanh Menu.

    python -m src.bot.bot

• Thanh Menu (nút "Menu" cạnh ô chat) liệt kê lệnh; menu chính dạng nút bấm; mỗi tin có nút điều hướng.
• Gõ thẳng mã (vd. FPT) → thẻ phân tích + nút Biểu đồ / Theo dõi.
• Lệnh: /menu /market /leaders /foreign /outlook /stock <mã> /chart <mã> /watch /add <mã> /remove <mã>
  /portfolio [thận trọng|cân bằng|tăng trưởng] /report /status /help.
• Chỉ phản hồi chat_id trong TELEGRAM_CHAT_IDS. Mọi tin kết thúc bằng câu miễn trừ. Không có chức năng đặt lệnh.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Dict, Optional

from src.bot import messages as M
from src.bot.telegram_api import chat_ids, token
from src.common.config import get
from src.common.logging import get_logger

log = get_logger(__name__)

COMMANDS = [("menu", "🏠 Menu chính"), ("market", "📊 Tổng quan thị trường"), ("leaders", "🏁 Mã dẫn dắt VN-Index"),
            ("foreign", "🌏 Dòng vốn khối ngoại"), ("outlook", "🔮 Triển vọng 5 & 20 phiên"),
            ("stock", "📈 Phân tích một mã: /stock FPT"), ("chart", "🖼 Biểu đồ: /chart FPT"),
            ("watch", "👁 Danh mục theo dõi"), ("add", "➕ Thêm mã: /add FPT"), ("remove", "➖ Bỏ mã: /remove FPT"),
            ("portfolio", "💼 Tối ưu danh mục theo khẩu vị"), ("report", "📄 PDF báo cáo gần nhất"),
            ("status", "🛰 Tình trạng dữ liệu"), ("help", "❓ Hướng dẫn")]
PROFILE_ALIASES = {"than": "Thận trọng", "thận": "Thận trọng", "can": "Cân bằng", "cân": "Cân bằng",
                   "tang": "Tăng trưởng", "tăng": "Tăng trưởng"}

_CTX: Dict = {"t": 0.0, "d": None, "ctx": None}


def ctx_cached() -> Optional[Dict]:
    """context.build() tốn vài giây – giữ 5 phút hoặc tới khi có phiên mới."""
    from src.reports import context
    d = context.latest_date()
    if _CTX["ctx"] is None or _CTX["d"] != d or time.time() - _CTX["t"] > 300:
        _CTX.update(ctx=context.build(d), d=d, t=time.time())
    return _CTX["ctx"]


def _disc(text: str) -> str:
    return f"{text}\n\n<i>— {get('app.bot_disclaimer')}</i>"


def main() -> None:
    from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonCommands, Update)
    from telegram.constants import ParseMode
    from telegram.error import BadRequest
    from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters)

    if not token():
        print("Thiếu TELEGRAM_BOT_TOKEN trong .env (tạo bot qua @BotFather).")
        sys.exit(1)
    allowed = set(chat_ids())

    def kb(rows) -> Optional[InlineKeyboardMarkup]:
        return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=c[:64]) for t, c in r] for r in rows if r]) if rows else None

    async def send(update: Update, text: str, rows=None, edit: bool = False):
        markup = kb(rows)
        body = _disc(text)[:4090]
        q = update.callback_query
        if edit and q is not None:
            try:
                await q.edit_message_text(body, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True)
                return
            except BadRequest as exc:              # tin là ảnh/tài liệu hoặc nội dung không đổi → gửi tin mới
                if "not modified" in str(exc).lower():
                    return
        await update.effective_chat.send_message(body, parse_mode=ParseMode.HTML, reply_markup=markup,
                                                 disable_web_page_preview=True)

    def guard(fn):
        async def wrap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            cid = str(update.effective_chat.id)
            if allowed and cid not in allowed:
                log.warning("Từ chối chat_id không đăng ký")
                return
            if update.callback_query is not None:
                await update.callback_query.answer()
            try:
                await fn(update, ctx)
            except Exception as exc:  # noqa: BLE001
                log.error("Lỗi lệnh bot: %s", exc)
                busy = "lock" in str(exc).lower() or "being used" in str(exc).lower()
                msg = ("⏳ Dữ liệu đang được cập nhật – thử lại sau ít phút." if busy
                       else f"⚠️ Không xử lý được yêu cầu: {type(exc).__name__}")
                await update.effective_chat.send_message(msg, reply_markup=kb(M.BACK))
        return wrap

    # ── trang nội dung (dùng chung cho lệnh và nút) ───────────────────────────
    async def page(update: Update, name: str, arg: str = "", edit: bool = False):
        if name == "menu":
            await send(update, M.menu_text(), M.MENU, edit)
        elif name == "help":
            await send(update, M.HELP, M.MENU, edit)
        elif name in ("market", "leaders", "foreign", "outlook"):
            text, rows = getattr(M, name)(ctx_cached(), with_buttons=True)
            await send(update, text, rows, edit)
        elif name == "watch":
            text, rows = M.watch(None, ctx_cached(), with_buttons=True)
            await send(update, text, rows, edit)
        elif name == "stock":
            text, rows = M.stock_card(arg, ctx_cached())
            await send(update, text, rows, edit)
        elif name == "pf":
            text, rows = M.portfolio(arg or "Cân bằng")
            await send(update, text, rows, edit)
        elif name == "status":
            await send(update, M.status(), M.BACK, edit)
        elif name == "chart":
            from src.bot import charts
            sym = (arg or "VNINDEX").upper()
            img = charts.index_chart(sym) if sym in ("VNINDEX", "VN30") else charts.stock_chart(sym)
            back = [[("📈 Thẻ phân tích", f"stock:{sym}"), ("🏠 Menu", "menu")]] if sym not in ("VNINDEX", "VN30") \
                else [[("📊 Thị trường", "market"), ("🏠 Menu", "menu")]]
            await update.effective_chat.send_photo(img, caption=f"🖼 {sym} – giá, MA20/MA50, khối lượng, khối ngoại ròng",
                                                   reply_markup=kb(back))
        elif name == "report":
            p = M.latest_report()
            if not p or not Path(p).exists():
                await send(update, "📄 Chưa có báo cáo PDF – xuất ở trang 'Báo cáo &amp; Telegram'.", M.BACK, edit)
                return
            with open(p, "rb") as f:
                await update.effective_chat.send_document(f, caption=f"📄 {Path(p).name}", reply_markup=kb(M.BACK))
        elif name in ("add", "rm"):
            from src.analytics import watchlist_impact as wi
            sym = arg.upper()
            if name == "add":
                wl = wi.get_watchlist()
                if len(wl) >= int(get("watchlist_max", 15)):
                    await send(update, f"⚠️ Danh mục đã đủ {len(wl)} mã – bỏ bớt trước khi thêm.", M.BACK)
                    return
                wi.add(sym, "thêm qua Telegram")
            else:
                wi.remove(sym)
            _CTX["ctx"] = None                         # danh mục đổi → tính lại hồ sơ watchlist
            text, rows = M.stock_card(sym, ctx_cached())
            note = f"✅ Đã {'thêm' if name == 'add' else 'bỏ'} <b>{sym}</b> {'vào' if name == 'add' else 'khỏi'} danh mục.\n\n"
            await send(update, note + text, rows, edit)

    # ── lệnh ──────────────────────────────────────────────────────────────────
    def cmd(name: str, need_arg: bool = False):
        @guard
        async def h(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            arg = " ".join(ctx.args) if ctx.args else ""
            if need_arg and not arg:
                await send(update, f"Cú pháp: /{name} &lt;mã&gt;, ví dụ <code>/{name} FPT</code>", M.BACK)
                return
            if name == "portfolio":
                key = arg.lower().split()[0][:4] if arg else ""
                await page(update, "pf", next((v for k, v in PROFILE_ALIASES.items() if key.startswith(k)), "Cân bằng"))
            elif name == "remove":
                await page(update, "rm", arg.split()[0])
            elif name in ("stock", "chart", "add"):
                await page(update, name, arg.split()[0] if arg else "")
            elif name == "start":
                await send(update, "👋 Xin chào! Đây là <b>FTSE Flow Radar</b> – radar dòng vốn ngoại và độ vênh thị trường "
                                   "giai đoạn nâng hạng FTSE.\n\n" + M.menu_text(), M.MENU)
            else:
                await page(update, name)
        return h

    @guard
    async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        data = update.callback_query.data or "menu"
        name, _, arg = data.partition(":")
        await page(update, name, arg, edit=name not in ("chart", "report"))

    @guard
    async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        t = (update.message.text or "").strip().upper()
        if re.fullmatch(r"[A-Z0-9]{3,4}", t):
            await page(update, "stock", t)
        else:
            await send(update, "Gõ một mã cổ phiếu (vd. <code>FPT</code>) hoặc chọn mục bên dưới.", M.MENU)

    async def post_init(app: Application) -> None:
        await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])
        await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        log.info("Đã đăng ký %d lệnh vào thanh Menu", len(COMMANDS))

    app = Application.builder().token(token()).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd("start")))
    for name, _ in COMMANDS:
        app.add_handler(CommandHandler(name, cmd(name, need_arg=name in ("stock", "add", "remove"))))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("Bot Telegram đang chạy (%d chat_id được phép)", len(allowed))
    print("🤖 FTSE Flow Radar bot đang chạy – Ctrl+C để dừng")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
