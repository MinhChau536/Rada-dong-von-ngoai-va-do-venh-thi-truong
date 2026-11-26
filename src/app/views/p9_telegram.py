"""Trang Bot Telegram: trạng thái bot, xem trước tin nhắn (đúng nội dung + nút bấm bot sẽ gửi), gửi thử / gửi bản tin
ngay, danh sách lệnh trong thanh Menu, cấu hình và nhật ký cảnh báo gửi thật."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

from src.app import data_access as da
from src.app.components import status_bar
from src.app.components.states import empty
from src.app.components.ui import esc, header, kpi_row, kpi, md, pal, section, table_html
from src.bot import messages as M
from src.bot import runtime
from src.bot import telegram_api as tg
from src.common.config import get

ALERT_TYPES = {"index_concentrated": "1 · Chỉ số do ít mã dẫn dắt", "high_divergence": "2 · Độ vênh cao",
               "foreign_market": "3 · Dòng vốn ngoại toàn sàn bất thường", "wl_foreign": "4 · Mã watchlist có dòng vốn bất thường",
               "wl_deviation": "5 · Mã watchlist lệch mạnh khỏi thị trường", "wl_leader": "6 · Mã watchlist trong nhóm dẫn dắt",
               "wl_room": "7 · Room sắp cạn", "system_failover": "8 · Sự cố nguồn SSI (hệ thống)"}
PREVIEWS = ["Menu chính", "Thị trường", "Dẫn dắt", "Khối ngoại", "Triển vọng", "Watchlist",
            "Thẻ phân tích mã", "Chẩn đoán phiên", "Tình trạng dữ liệu", "Ký hiệu", "Hướng dẫn"]


@st.cache_resource(ttl=300, show_spinner="Đang dựng nội dung tin nhắn…")
def _ctx(date):
    from src.reports import context
    return context.build(date)


@st.cache_data(ttl=3600, show_spinner=False)
def _me():
    return runtime.get_me()


def _message(kind: str, date, symbol: str, profile: str):
    ctx = _ctx(date)
    if kind == "Menu chính":
        return M.menu_text(), M.MENU
    if kind == "Ký hiệu":
        return M.LEGEND, M.BACK
    if kind == "Hướng dẫn":
        return M.HELP, M.MENU
    if kind == "Tình trạng dữ liệu":
        return M.status(), M.BACK
    if kind == "Watchlist":
        return M.watch(None, ctx, with_buttons=True)
    if kind == "Thẻ phân tích mã":
        return M.stock_card(symbol, ctx)
    if kind == "Chẩn đoán phiên":
        return M.diagnosis(ctx)
    fn = {"Thị trường": M.market, "Dẫn dắt": M.leaders, "Khối ngoại": M.foreign, "Triển vọng": M.outlook}[kind]
    return fn(ctx, with_buttons=True)


def _phone(text: str, kb, me) -> str:
    """Khung xem trước giống ứng dụng Telegram: bong bóng tin (HTML Telegram) + hàng nút inline."""
    p = pal()
    dark = p["dark"]
    bg, bubble, btn = ("#0E1621", "#182533", "#2B5278") if dark else ("#D9E7D0", "#FFFFFF", "#4A7458")
    fg = "#E9EEF2" if dark else "#0F172A"
    body = (text + f"\n\n<i>— {esc(get('app.bot_disclaimer'))}</i>").replace("\n", "<br>")   # markdown bỏ xuống dòng trong HTML
    body = re.sub(r"<code>", '<code style="background:rgba(127,127,127,.18);color:inherit;padding:0 4px;border-radius:4px">', body)
    rows = "".join(
        '<div style="display:flex;gap:4px;margin-top:4px">' + "".join(
            f'<div style="flex:1;background:{btn};color:#fff;text-align:center;border-radius:8px;padding:7px 4px;'
            f'font-size:13px;font-weight:600">{esc(t)}</div>' for t, _ in row) + "</div>"
        for row in (kb or []) if row)
    name = esc((me or {}).get("first_name", "FTSE Flow Radar"))
    return (f'<div style="background:{bg};border-radius:16px;padding:14px;max-width:470px;border:1px solid {p["border"]}">'
            f'<div style="font-size:13px;color:{"#8BA0B3" if dark else "#3F6212"};font-weight:700;margin-bottom:6px">🤖 {name}</div>'
            f'<div style="background:{bubble};color:{fg};border-radius:12px 12px 12px 4px;padding:10px 12px;font-size:13.5px;'
            f'line-height:1.5;white-space:pre-wrap;word-break:break-word;box-shadow:0 1px 2px rgba(0,0,0,.15)">{body}</div>'
            f'{rows}</div>')


FEATURES = [
    ("", "Tra cứu bằng nút bấm", "Menu 10 nút: Thị trường, Dẫn dắt, Khối ngoại, Triển vọng, Chẩn đoán phiên, Watchlist, PDF… "
                                  "Gõ thẳng mã (vd. FPT) để nhận thẻ phân tích mã. Mọi số liệu đọc từ cùng kho chỉ báo với web và PDF."),
    ("", "Cảnh báo tự động trong phiên", "Quét 2 phút/lần (9:00–15:05) bằng nến 1 phút SSI + luồng WebSocket: VN-Index vượt ±1%/±2%, "
                                          "biến động 15 phút, vượt biên EWMA 95%, cắt MA50, khối ngoại bất thường, độ rộng lệch; mã "
                                          "watchlist vượt ngưỡng %, trần/sàn, khối lượng đột biến, phá đỉnh/đáy 20 phiên."),
    ("", "Bản tin định kỳ", "11:35 bản tin giữa phiên + PDF Market Snapshot; 15:15 Chẩn đoán phiên + Closing Report; sau phiên tín "
                             "hiệu xu hướng cuối ngày (đổi trạng thái MA50, động lượng, dòng vốn ngoại; mã watchlist cắt MA20, đỉnh/đáy mới)."),
    ("", "An toàn & chống làm phiền", "Chỉ trả lời chat_id được phép (danh sách trống = không trả lời ai); mỗi tín hiệu gửi tối đa "
                                       "1 lần/ngày; chặn bấm nút lặp; token đặt trong .env, không có trong mã nguồn."),
]


@st.cache_data(ttl=600, show_spinner=False)
def _examples(date) -> list:
    """Tin mẫu dựng từ dữ liệu SSI thật của phiên đã chọn (không cần token bot)."""
    ctx = _ctx(date)
    out = []
    for title, fn in (("Tin Thị trường", lambda: M.market(ctx, with_buttons=True)),
                      ("Chẩn đoán phiên", lambda: M.diagnosis(ctx)),
                      ("Thẻ phân tích mã VIC", lambda: M.stock_card("VIC", ctx))):
        try:
            out.append((title,) + tuple(fn()))
        except Exception as exc:  # noqa: BLE001
            out.append((title, f"Không dựng được: {esc(exc)}", M.BACK))
    return out


def _intro(me, p) -> None:
    md('<div class="ffr-insight"><b>Bot Telegram là gì?</b> Phiên bản "bỏ túi" của FTSE Flow Radar: nhà đầu tư không cần mở web '
       'vẫn nhận được chẩn đoán phiên, cảnh báo biến động và báo cáo PDF ngay trên điện thoại. Bot đọc <b>cùng kho chỉ báo</b> với '
       'web và PDF (dữ liệu SSI FastConnect V3), nên mọi con số trùng khớp giữa ba kênh. Token bot không nằm trong mã nguồn vì bảo '
       'mật – người chấm có thể xem đầy đủ nội dung bot gửi qua các <b>tin mẫu dựng từ dữ liệu thật</b> bên dưới, hoặc tự tạo bot '
       'qua @BotFather rồi điền <code>TELEGRAM_BOT_TOKEN</code>, <code>TELEGRAM_CHAT_IDS</code> vào .env và chạy '
       '<code>python -m src.bot.bot</code>.</div>')
    cols = st.columns(4, gap="small")
    for col, (ico, t, d) in zip(cols, FEATURES):
        col.markdown(f'<div class="ffr-card" style="height:100%">'
                     f'<div style="font-weight:600;font-size:15px;margin:0 0 6px">{esc(t)}</div>'
                     f'<div style="font-size:14px;line-height:1.55;color:{p["text"]}">{esc(d)}</div></div>', unsafe_allow_html=True)
    section("Luồng hoạt động", "Từ SSI tới tin nhắn trên điện thoại")
    md(table_html(["Bước", "Thành phần", "Việc làm"], [
        ["1", "SSI FastConnect V3", "REST (số liệu cuối ngày, nến 1 phút) + WebSocket (khớp lệnh, room ngoại, tổng hợp chỉ số)"],
        ["2", "Kho DuckDB + chuỗi chỉ báo", "Độ vênh, đóng góp điểm, khối ngoại, phân vị, EWMA… (src/analytics/pipeline.py)"],
        ["3", "Bộ quét cảnh báo (src/bot/monitor.py)", "So từng chỉ báo với ngưỡng theo độ nhạy Thấp/Vừa/Cao; khóa chống trùng theo ngày"],
        ["4", "Bộ soạn tin (src/bot/messages.py)", "Dựng tin HTML + bàn phím nút bấm; câu mô tả số liệu, không khuyến nghị mua/bán"],
        ["5", "Telegram Bot API", "Gửi tới chat_id được phép; nhận lệnh/nút bấm và trả lời"],
    ], left=(1, 2)))
    section("Tin mẫu dựng từ dữ liệu thật", "Đúng nội dung và nút bấm bot gửi – không cần token")
    sess = da.sessions()
    d = sess[-1] if sess else None
    if d is None:
        empty("Chưa có dữ liệu.")
        return
    ex = _examples(d)
    cols = st.columns(len(ex), gap="medium")
    for col, (title, text, kb) in zip(cols, ex):
        with col:
            st.markdown(f"**{title}** · phiên {d:%d/%m/%Y}")
            md(_phone(text, kb, me))
    al = da.table("alert_log")
    sent = al[(al["mode"] == "live") & (al["status"] == "sent")].sort_values("ts", ascending=False) if not al.empty else al
    from src.bot import monitor
    md(f'<div style="height:10px"></div>')
    c1, c2 = st.columns([1, 1.2], gap="large")
    with c1:
        st.markdown("**Ví dụ cảnh báo tự động** (đúng định dạng bot gửi khi mã watchlist thủng đáy 20 phiên)")
        sample = ("👁 <b>VNM – MÃ BẠN ĐANG THEO DÕI</b> · 09:49\n━━━━━━━━━━━━━━━━━━\n⚠️ Thủng <b>đáy 20 phiên</b> (52.000)\n\n"
                  "• Giá 51.900 (-0,19% so tham chiếu) · KL 0,51 tr")
        md(_phone(sample, [[("⏱ Trong phiên", "x"), ("📈 Thẻ phân tích", "x")], [("🏭 Ngành", "x"), ("🔔 Cài đặt cảnh báo", "x")]], me))
        st.caption("Tin thật bot đã gửi phiên 19/11/2026 lúc 09:49 (nhật ký logs/app.log).")
    with c2:
        st.markdown("**Cơ chế cảnh báo** – nội dung nút \"Cơ chế cảnh báo\" trong bot")
        txt, kb = monitor.mechanism_text("preview")
        md(_phone(txt, kb, me))


def render() -> None:
    header("Bot Telegram", "Radar trong túi: chẩn đoán phiên, cảnh báo tự động 2 phút/lần, bản tin 11:35 & 15:15, tra cứu mã bằng nút bấm",
           pills=["@" + ((_me() or {}).get("username") or "chưa cấu hình")])
    status_bar.render()
    p = pal()
    _intro(_me(), p)
    section("Trạng thái bot trên máy này", "Chỉ có khi đã cấu hình token trong .env và chạy python -m src.bot.bot")
    me, proc = _me(), runtime.bot_process()
    al = da.table("alert_log")
    live = al[al["mode"] == "live"] if not al.empty else al
    kpi_row([
        kpi("Cấu hình .env", "Đã cấu hình" if tg.configured() else "Chưa cấu hình", p["up"] if tg.configured() else p["down"],
            "TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_IDS"),
        kpi("Tài khoản bot", "@" + me["username"] if me else "—", None, me.get("first_name", "") if me else "token sai hoặc mất mạng"),
        kpi("Tiến trình bot", "Đang chạy" if proc else "Chưa chạy", p["up"] if proc else p["down"],
            f"PID {proc['pid']} · từ {proc['started'][11:16]} {proc['started'][8:10]}/{proc['started'][5:7]}" if proc
            else "python -m src.bot.bot"),
        kpi("Chat được phép", str(len(tg.chat_ids())), None, "bot bỏ qua mọi chat khác"),
        kpi("Cảnh báo đã gửi", str(int((live["status"] == "sent").sum())) if not live.empty else "0", None, "chế độ live"),
    ])
    from src.bot import monitor
    ms = monitor.status()
    ap = [monitor.prefs(c) for c in tg.chat_ids()]
    on = [c for c, x in zip(tg.chat_ids(), ap) if x["on"]]
    types = ", ".join(n for k, n in monitor.TYPES.items() if any(x["types"][k] for x in ap)) or "—"
    st.caption(f"**Cảnh báo tự động** (bot tự nhắn khi thị trường/mã theo dõi biến động): "
               f"{'bật cho ' + str(len(on)) + ' chat' if on else 'đang tắt'} · {types} · "
               f"quét gần nhất {ms['last_scan'] or '—'} · đã gửi hôm nay {ms['sent_today']} tín hiệu · "
               "đổi cài đặt bằng lệnh /alerts trong Telegram. Chỉ chạy khi bot đang chạy.")
    if not proc:
        st.info("Bot chưa chạy nên **nút bấm và lệnh trong Telegram chưa phản hồi** (tin gửi từ trang này vẫn tới). "
                "Mở một cửa sổ PowerShell mới và chạy: `python -m src.bot.bot`.")

    # ── xem trước + gửi ───────────────────────────────────────────────────────
    section("Xem trước tin nhắn", "Đúng nội dung và nút bấm bot gửi · dựng từ cùng kho chỉ báo với PDF và giao diện")
    sess = da.sessions()
    left, right = st.columns([1, 1.25], gap="large")
    with left:
        kind = st.radio("Loại tin", PREVIEWS, key="tg_kind")
        date = st.selectbox("Phiên", sess[::-1][:60], format_func=lambda d: f"Phiên {d:%d/%m/%Y}", key="tg_date")
        sym, prof = "FPT", "Cân bằng"
        if kind == "Thẻ phân tích mã":
            syms = da.symbols()
            sym = st.selectbox("Mã", syms, index=syms.index("FPT") if "FPT" in syms else 0, key="tg_sym")
        try:
            text, kb = _message(kind, date, sym, prof)
        except Exception as exc:  # noqa: BLE001
            text, kb = f"Không dựng được tin: {esc(type(exc).__name__)}: {esc(exc)}", M.BACK
        st.caption("Thẻ mã, Watchlist và Tình trạng luôn dùng dữ liệu mới nhất; các tin còn lại theo phiên đã chọn.")
        b1, b2 = st.columns(2)
        if b1.button("Gửi tin này", type="primary", width="stretch", disabled=not tg.configured()):
            ok = tg.send_message(text, html=True, keyboard=kb)
            st.toast("Đã gửi tới Telegram" if ok else "Gửi thất bại – xem logs/app.log", icon=":material/check_circle:" if ok else ":material/error:")
        if b2.button("Gửi tin thử", width="stretch", disabled=not tg.configured()):
            ok = tg.send_message("🧪 Tin thử từ <b>FTSE Flow Radar</b>.", html=True, keyboard=M.MENU)
            st.toast("Đã gửi" if ok else "Gửi thất bại – xem logs/app.log", icon=":material/check_circle:" if ok else ":material/error:")
    with right:
        md(_phone(text, kb, me))

    # ── gửi ngay ──────────────────────────────────────────────────────────────
    section("Gửi ngay", f"Lịch tự động (python -m src.data.scheduler): giữa phiên {get('schedule.midday_brief')} · "
                        f"cuối phiên {get('schedule.closing_report', '15:15')}")
    g1, g2, g3, g4 = st.columns(4)
    off = not tg.configured()
    if g1.button("Bản tin giữa phiên", width="stretch", disabled=off, help="Tin thị trường + PDF Market Snapshot"):
        from src.bot import jobs
        with st.spinner("Đang dựng và gửi…"):
            r = jobs.midday_brief()
        st.toast("Đã gửi bản tin giữa phiên" if r["sent"] else "Gửi thất bại", icon=":material/check_circle:" if r["sent"] else ":material/error:")
        da.clear_cache()
    if g2.button("Bản tin cuối phiên", width="stretch", disabled=off, help="Thị trường + khối ngoại + triển vọng + Closing Report"):
        from src.bot import jobs
        with st.spinner("Đang dựng và gửi…"):
            r = jobs.closing_brief()
        st.toast("Đã gửi bản tin cuối phiên" if r["sent"] else "Gửi thất bại", icon=":material/check_circle:" if r["sent"] else ":material/error:")
        da.clear_cache()
    if g3.button("PDF gần nhất", width="stretch", disabled=off):
        path = M.latest_report()
        ok = bool(path and Path(path).exists() and tg.send_document(Path(path), f"📄 {Path(path).name}"))
        st.toast(f"Đã gửi {Path(path).name}" if ok else "Chưa có PDF hoặc gửi thất bại", icon=":material/check_circle:" if ok else ":material/error:")
    if g4.button("Quét cảnh báo", width="stretch", disabled=off, help="Chạy quy tắc cảnh báo trên phiên mới nhất và gửi nếu có"):
        from src.bot import jobs
        n = jobs.run_alerts()
        st.toast(f"Đã gửi {n} cảnh báo" if n else "Không có cảnh báo mới (hoặc bị chặn trùng/giới hạn)", icon=":material/check_circle:")
        da.clear_cache()

    # ── lệnh ──────────────────────────────────────────────────────────────────
    from src.bot.bot import COMMANDS
    section("Lệnh trong thanh Menu", "Bấm nút Menu cạnh ô chat để chọn · hoặc gõ thẳng mã cổ phiếu (vd. FPT) để ra thẻ phân tích")
    half = (len(COMMANDS) + 1) // 2
    c1, c2 = st.columns(2)
    for col, part in ((c1, COMMANDS[:half]), (c2, COMMANDS[half:])):
        with col:
            md(table_html(["Lệnh", "Chức năng"], [[f"<code>/{c}</code>", esc(d)] for c, d in part], left=(0, 1)))

    # ── cảnh báo ──────────────────────────────────────────────────────────────
    section("Cấu hình cảnh báo", f"Cooldown {get('alerts.cooldown_min')} phút · tối đa {get('alerts.max_market_per_day')} "
                                 "cảnh báo thị trường/ngày · ngưỡng đọc từ settings.yaml")
    prefs = st.session_state.setdefault("alert_prefs", {k: True for k in ALERT_TYPES})
    cols = st.columns(2)
    for i, (k, lbl) in enumerate(ALERT_TYPES.items()):
        prefs[k] = cols[i % 2].toggle(lbl, value=prefs.get(k, True), key=f"al_{k}", disabled=k.startswith("system"))
    section("Nhật ký cảnh báo đã gửi", "Chế độ live · kết quả chạy lại trên lịch sử xem ở trang Backtest")
    if live.empty:
        empty("Chưa có cảnh báo nào được gửi thật.")
        return
    a = live.sort_values("ts", ascending=False)
    a = a[a["alert_type"].map(lambda t: prefs.get(t, True))]
    st.caption(f"{len(a)} dòng · đã gửi {int((a['status'] == 'sent').sum())} · chặn trùng "
               f"{int((a['status'] == 'suppressed_duplicate').sum())} · chặn giới hạn {int((a['status'] == 'suppressed_limit').sum())}")
    md(table_html(["Thời điểm", "Quy tắc", "Mã", "Ưu tiên", "Trạng thái", "Nội dung"],
                  [[pd.Timestamp(r.ts).strftime("%d/%m %H:%M"), str(r.rule_no), r.symbol or "—", r.priority, r.status, esc(r.message)]
                   for r in a.head(40).itertuples()], left=(0, 1, 2, 3, 4, 5)))
