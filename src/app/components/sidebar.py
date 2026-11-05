"""
Thanh bên (bước B4.2, Hình 2a): logo, ô tra cứu mã, 8 trang chia 4 nhóm, trạng thái SSI/NEO, khuyến cáo học thuật.
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
from src.common.config import get, is_demo


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
        c1, c2 = st.columns(2)
        with c1:
            dark = st.toggle("Tối", value=st.session_state.get("theme") == "dark", key="theme_toggle")
            st.session_state["theme"] = "dark" if dark else "light"
        with c2:
            if st.button("↻ Làm mới", width="stretch", help="Xóa bộ nhớ đệm và đọc lại kho chỉ báo"):
                da.clear_cache()
                st.rerun()
        srcs = source_state()
        d = da.daily() if da.ready() else pd.DataFrame()
        n_sess = len(d)
        last = d["trade_date"].max().strftime("%d/%m/%Y") if n_sess else "—"
        lines = [f'<span class="ffr-dot" style="background:{srcs["SSI"][0]}"></span>SSI FastConnect · nguồn chính',
                 f'<span class="ffr-dot" style="background:{srcs["NEO"][0]}"></span>NEO API · ghi song song',
                 f'<span class="ffr-dot" style="background:#14B8A6"></span>Phiên mới nhất {last}',
                 f'<span class="ffr-dot" style="background:#7F8EA3"></span>Kho DuckDB · {n_sess} phiên']
        if is_demo():
            lines.insert(0, '<span class="ffr-dot" style="background:#F59E0B"></span><b>CHẾ ĐỘ DỮ LIỆU MẪU</b>')
        md('<div class="ffr-srcbox">' + "<br>".join(lines) + "</div>")
        md(f'<div class="ffr-disc"><b style="color:#FBBF24">Khuyến cáo học thuật</b><br>{get("app.disclaimer")} '
           'Hệ thống chỉ đọc dữ liệu, không đặt lệnh.</div>')
