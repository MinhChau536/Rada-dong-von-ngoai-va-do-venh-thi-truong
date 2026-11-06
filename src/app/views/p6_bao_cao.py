"""Trang 6 – Báo cáo & Telegram (bước B9.3): nút xuất Snapshot/Closing; danh sách báo cáo đã sinh (tải về);
cấu hình loại cảnh báo bật/tắt; nhật ký tin đã gửi."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.app import data_access as da
from src.app.components import status_bar
from src.app.components.states import empty
from src.app.components.ui import header, md, section, table_html
from src.bot import telegram_api as tg
from src.common.config import get
from src.reports import closing, snapshot

ALERT_TYPES = {"index_concentrated": "1 · Chỉ số do ít mã dẫn dắt", "high_divergence": "2 · Độ vênh cao",
               "foreign_market": "3 · Dòng vốn ngoại toàn sàn bất thường", "wl_foreign": "4 · Mã watchlist có dòng vốn bất thường",
               "wl_deviation": "5 · Mã watchlist lệch mạnh khỏi thị trường", "wl_leader": "6 · Mã watchlist trong nhóm dẫn dắt",
               "wl_room": "7 · Room sắp cạn", "system_failover": "8 · Sự cố dữ liệu (hệ thống)"}


def render() -> None:
    header("Báo cáo & Telegram", "Xuất PDF từ cùng kho chỉ báo với giao diện · bản tin và cảnh báo qua bot")
    status_bar.render()
    sess = da.sessions()
    section("Xuất báo cáo PDF")
    c1, c2, c3 = st.columns([1.2, 1, 1])
    date = c1.selectbox("Phiên", sess[::-1], format_func=lambda d: f"Phiên {d:%d/%m/%Y}", key="p6_date")
    if c2.button("📄 Xuất Market Snapshot", type="primary", width="stretch"):
        with st.spinner("Đang dựng PDF…"):
            p = snapshot.build(date)
        st.success(f"Đã xuất {p.name}") if p else st.error("Không xuất được – không có dữ liệu phiên.")
        da.clear_cache()
    if c3.button("📑 Xuất Closing Report", width="stretch"):
        with st.spinner("Đang kiểm tra chất lượng và dựng PDF…"):
            p, reason = closing.build(date)
        if p:
            st.success(f"Đã xuất {p.name}")
        else:
            st.error(f"Không xuất Closing Report: {reason} (chỉ xuất khi kiểm tra chất lượng cuối phiên đạt).")
        da.clear_cache()
    rl = da.table("reports_log")
    section("Báo cáo đã sinh", "Ghi trong bảng reports_log")
    if rl.empty:
        empty("Chưa có báo cáo nào.")
    else:
        rl = rl.sort_values("created_at", ascending=False).head(15)
        for r in rl.itertuples():
            cols = st.columns([1.3, 1, 1, 3, 1.2])
            cols[0].write(pd.Timestamp(r.created_at).strftime("%d/%m %H:%M"))
            cols[1].write(r.kind)
            cols[2].write("✅ " + r.status if r.status == "ok" else "⛔ " + str(r.status))
            cols[3].caption(Path(r.path).name if isinstance(r.path, str) else (r.note or ""))
            if isinstance(r.path, str) and Path(r.path).exists():
                cols[4].download_button("Tải về", Path(r.path).read_bytes(), file_name=Path(r.path).name,
                                        mime="application/pdf", key=f"dl_{r.id}")
    section("Telegram", "Bot chỉ phản hồi chat_id đã đăng ký · mọi tin kèm câu miễn trừ")
    if tg.configured():
        st.success(f"Bot đã cấu hình · {len(tg.chat_ids())} chat_id được phép.")
        if st.button("Gửi tin thử"):
            st.write("Đã gửi" if tg.send_message("Tin thử từ FTSE Flow Radar.") else "Gửi thất bại – xem logs/app.log")
    else:
        st.info("Chưa cấu hình TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS trong .env – bot và bản tin tự động đang tắt. "
                "Chạy bot: `python -m src.bot.bot`; lịch 11:35 & 15:15: `python -m src.data.scheduler`.")
    md(table_html(["Lệnh", "Chức năng"], [["/market", "Tóm tắt: VN-Index, trung vị, D, loại phiên, nhận định"],
                                          ["/leaders", "5 mã đóng góp dương và 5 mã âm lớn nhất"],
                                          ["/foreign", "Tổng ròng, top mã, HHI, nhóm FTSE"], ["/watch [mã]", "Hồ sơ watchlist hoặc một mã"],
                                          ["/report", "Gửi PDF gần nhất"], ["/status", "Nguồn, thời điểm dữ liệu, độ đầy đủ"]],
                  left=(0, 1)))
    section("Cấu hình cảnh báo", f"Cooldown {get('alerts.cooldown_min')} phút · tối đa {get('alerts.max_market_per_day')} "
                                 "cảnh báo thị trường/ngày · ngưỡng đọc từ settings.yaml")
    prefs = st.session_state.setdefault("alert_prefs", {k: True for k in ALERT_TYPES})
    cols = st.columns(2)
    for i, (k, lbl) in enumerate(ALERT_TYPES.items()):
        prefs[k] = cols[i % 2].toggle(lbl, value=prefs.get(k, True), key=f"al_{k}", disabled=k.startswith("system"))
    section("Nhật ký cảnh báo", "live = gửi thật · backtest = chạy lại 60 phiên lịch sử (B8.4)")
    al = da.table("alert_log")
    if al.empty:
        empty("Chưa có cảnh báo.")
        return
    mode = st.radio("Chế độ", ["backtest", "live"], horizontal=True, key="p6_mode")
    a = al[al["mode"] == mode].sort_values("ts", ascending=False)
    a = a[a["alert_type"].map(lambda t: prefs.get(t, True))]
    st.caption(f"{len(a)} dòng · giữ lại {int(a['status'].isin(['sent', 'simulated']).sum())} · "
               f"chặn trùng {int((a['status'] == 'suppressed_duplicate').sum())} · chặn giới hạn {int((a['status'] == 'suppressed_limit').sum())}")
    md(table_html(["Thời điểm", "Quy tắc", "Mã", "Ưu tiên", "Trạng thái", "Nội dung"],
                  [[pd.Timestamp(r.ts).strftime("%d/%m %H:%M"), str(r.rule_no), r.symbol or "—", r.priority, r.status, r.message]
                   for r in a.head(40).itertuples()], left=(0, 1, 2, 3, 4, 5)))
