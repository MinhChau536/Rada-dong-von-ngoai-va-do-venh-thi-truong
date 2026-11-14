"""
Thanh bên (bước B4.2, Hình 2a): logo, ô tra cứu mã, 8 trang chia 4 nhóm, trạng thái nguồn SSI, khuyến cáo học thuật.
Dùng st.navigation(position="hidden") + st.page_link để tự vẽ nhóm và mục đang chọn theo hệ màu theme.py
(thay streamlit_option_menu giữa kỳ vì st.navigation hỗ trợ URL riêng từng trang và st.switch_page).
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd
import streamlit as st

from src.app import data_access as da
from src.app.components.status_bar import source_state
from src.app.components.ui import esc, md
from src.common.config import get


def render(groups: Dict[str, List], current) -> None:
    with st.sidebar:
        md(f'<div class="ffr-brand"><div class="ffr-logo">F</div><div><b>{get("app.name")}</b>'
           f'<small>{get("app.subtitle")}</small></div></div>')
        syms = da.symbols() if da.ready() else []
        pick = st.selectbox("Tra cứu mã", ["—"] + syms, key="sb_search", label_visibility="collapsed",
                            format_func=lambda s: "🔎 Tra cứu mã, ví dụ FPT…" if s == "—" else s)
        if pick and pick != "—" and pick != st.session_state.get("selected_symbol"):
            st.session_state["selected_symbol"] = pick
            st.session_state["sb_search_go"] = True
        for gname, pages in groups.items():
            md(f'<div class="ffr-grp">{gname}</div>')
            for pg in pages:
                if pg.url_path == current.url_path:
                    md(f'<div class="ffr-active">{esc(pg.title)}</div>')
                else:
                    st.page_link(pg, label=pg.title, icon=pg.icon)
        from src.app.components.banners import BACKGROUNDS, save_custom_image, save_prefs
        c1, c2 = st.columns([1, 1.25])
        with c1:
            dark = st.toggle("Tối", value=st.session_state.get("theme") == "dark", key="theme_toggle")
            new_theme = "dark" if dark else "light"
            if new_theme != st.session_state.get("theme"):
                st.session_state["theme"] = new_theme
                save_prefs(theme=new_theme)
        with c2:
            if st.button("↻ Làm mới", width="stretch", key="sb_refresh", help="Xóa bộ nhớ đệm và đọc lại kho chỉ báo"):
                da.clear_cache()
                st.rerun()
        cur = st.session_state.get("bg_choice", "Mặc định")
        bg = st.selectbox("🎨 Hình nền", BACKGROUNDS, index=BACKGROUNDS.index(cur) if cur in BACKGROUNDS else 0,
                          key="sb_bg", help="Đổi nền trang – lựa chọn được lưu cho lần mở sau")
        if bg != cur:
            st.session_state["bg_choice"] = bg
            save_prefs(background=bg)
        if bg == "Ảnh của tôi":
            up = st.file_uploader("Tải ảnh nền (JPG/PNG/WebP)", type=["jpg", "jpeg", "png", "webp"], key="sb_bg_up",
                                  label_visibility="collapsed")
            if up is not None and st.session_state.get("_bg_up_name") != up.name:
                save_custom_image(up.getvalue(), up.name)
                st.session_state["_bg_up_name"] = up.name
            ov = st.slider("Độ mờ lớp phủ (giữ chữ dễ đọc)", 0.3, 0.95, st.session_state.get("bg_overlay", 0.82), 0.05,
                           key="sb_bg_ov")
            if ov != st.session_state.get("bg_overlay"):
                st.session_state["bg_overlay"] = ov
                save_prefs(overlay=ov)
        srcs = source_state()
        d = da.daily() if da.ready() else pd.DataFrame()
        n_sess = len(d)
        last = d["trade_date"].max().strftime("%d/%m/%Y") if n_sess else "—"
        lines = [f'<span class="ffr-dot" style="background:{srcs["SSI"][0]}"></span>SSI FastConnect V3 · REST + WebSocket',
                 f'<span class="ffr-dot" style="background:#14B8A6"></span>Phiên mới nhất {last}',
                 f'<span class="ffr-dot" style="background:#7F8EA3"></span>Kho DuckDB · {n_sess} phiên']
        md('<div class="ffr-srcbox">' + "<br>".join(lines) + "</div>")
        md(f'<div class="ffr-disc"><b style="color:#FBBF24">Khuyến cáo học thuật</b><br>{get("app.disclaimer")} '
           'Hệ thống chỉ đọc dữ liệu, không đặt lệnh.</div>')
