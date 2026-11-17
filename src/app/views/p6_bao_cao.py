"""Trang 6 – Báo cáo PDF (bước B9.3): nút xuất Snapshot/Closing; danh sách báo cáo đã sinh (tải về).
Bot Telegram và cảnh báo ở trang riêng (p9_telegram.py); backtest ở trang riêng (p10_backtest.py)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.app import data_access as da
from src.app.components import status_bar
from src.app.components.states import empty
from src.app.components.ui import header, section
from src.reports import closing, snapshot

KINDS = {"Tất cả": None, "Closing Report": "closing", "Market Snapshot": "snapshot"}


def render() -> None:
    header("Báo cáo PDF", "Market Snapshot trong phiên và Closing Report cuối phiên · dựng từ cùng kho chỉ báo với giao diện")
    status_bar.render()
    sess = da.sessions()
    section("Xuất báo cáo PDF", "Closing Report chỉ xuất khi kiểm tra chất lượng cuối phiên đạt")
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
            st.success(f"Đã xuất {p.name}" + ("" if reason == "ok" else f" · Lưu ý: {reason.removeprefix('đạt – ')}"))
        else:
            st.error(f"Không xuất Closing Report: {reason} (chỉ xuất khi kiểm tra chất lượng cuối phiên đạt).")
        da.clear_cache()

    rl = da.table("reports_log")
    section("Báo cáo đã sinh", "Mỗi file hiện một lần (lần xuất mới nhất) · bản ghi trong bảng reports_log")
    if rl.empty:
        empty("Chưa có báo cáo nào.")
        return
    f1, f2 = st.columns([2, 1])
    kind = f1.segmented_control("Loại", list(KINDS), default="Tất cả", key="p6_kind") or "Tất cả"
    n = f2.selectbox("Số dòng", [10, 20, 50], index=1, key="p6_n")
    rl = rl.sort_values("created_at", ascending=False)
    rl["file"] = rl["path"].map(lambda x: Path(x).name if isinstance(x, str) else None)
    rl = pd.concat([rl[rl["file"].notna()].drop_duplicates("file"), rl[rl["file"].isna()]]).sort_values("created_at", ascending=False)
    if KINDS[kind]:
        rl = rl[rl["kind"] == KINDS[kind]]
    hdr = st.columns([1.3, 1, 1, 3, 1.2])
    for c, t in zip(hdr, ["Thời điểm xuất", "Loại", "Trạng thái", "File", ""]):
        c.caption(t)
    for i, r in enumerate(rl.head(n).itertuples()):
        cols = st.columns([1.3, 1, 1, 3, 1.2])
        cols[0].write(pd.Timestamp(r.created_at).strftime("%d/%m %H:%M"))
        cols[1].write(r.kind)
        cols[2].write("✅ " + r.status if r.status == "ok" else "⛔ " + str(r.status))
        cols[3].caption(r.file or (r.note or ""))
        if isinstance(r.path, str) and Path(r.path).exists():
            cols[4].download_button("Tải về", Path(r.path).read_bytes(), file_name=r.file,
                                    mime="application/pdf", key=f"dl_{i}_{r.file}")   # id có thể trùng sau khi khôi phục snapshot
    pages = st.session_state.get("_pages", {})
    if "telegram" in pages:
        st.page_link(pages["telegram"], label="Gửi báo cáo và bản tin qua Telegram → trang Bot Telegram", icon=":material/send:")
