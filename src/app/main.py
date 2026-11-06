"""
FTSE Flow Radar – điểm vào ứng dụng Streamlit.

    streamlit run src/app/main.py

Ứng dụng chỉ đọc dữ liệu thật tải từ SSI FastConnect Data / NEO API. Khi kho chỉ báo còn trống, chỉ mở trang
"Kết nối dữ liệu" (chẩn đoán API, IP cần đăng ký, nút tải dữ liệu) và trang "Phương pháp & giới hạn".
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from src.app import data_access as da  # noqa: E402
from src.app.theme import css, register_plotly  # noqa: E402
from src.common.config import get  # noqa: E402

st.set_page_config(page_title=f"{get('app.name')}", page_icon="📡", layout="wide", initial_sidebar_state="expanded")
st.session_state.setdefault("theme", "light")
st.session_state.setdefault("bg_fx", False)  # B4.3: tắt hiệu ứng nền động, không còn tùy chọn bật

from src.app.views import (p0_ket_noi, p1_tong_quan, p2_dan_dat, p3_khoi_ngoai, p4_su_kien, p5_watchlist,  # noqa: E402
                           p6_bao_cao, p7_chat_luong, p8_phuong_phap)

PAGES = {
    "Thị trường": [
        st.Page(p1_tong_quan.render, title="Tổng quan thị trường", icon=":material/dashboard:", url_path="tong-quan", default=True),
        st.Page(p2_dan_dat.render, title="Dẫn dắt & độ vênh", icon=":material/stacked_bar_chart:", url_path="dan-dat"),
    ],
    "Dòng vốn": [
        st.Page(p3_khoi_ngoai.render, title="Ra-đa khối ngoại", icon=":material/radar:", url_path="khoi-ngoai"),
        st.Page(p4_su_kien.render, title="Sự kiện FTSE", icon=":material/event:", url_path="su-kien-ftse"),
    ],
    "Cá nhân": [
        st.Page(p5_watchlist.render, title="Watchlist Impact", icon=":material/visibility:", url_path="watchlist"),
        st.Page(p6_bao_cao.render, title="Báo cáo & Telegram", icon=":material/description:", url_path="bao-cao"),
    ],
    "Hệ thống": [
        st.Page(p7_chat_luong.render, title="Chất lượng dữ liệu", icon=":material/fact_check:", url_path="chat-luong"),
        st.Page(p8_phuong_phap.render, title="Phương pháp & giới hạn", icon=":material/menu_book:", url_path="phuong-phap"),
        st.Page(p0_ket_noi.render, title="Kết nối dữ liệu", icon=":material/cable:", url_path="ket-noi"),
    ],
}
if not da.ready():                     # kho trống → chỉ mở trang kết nối & phương pháp, KHÔNG sinh dữ liệu giả
    PAGES = {"Hệ thống": [
        st.Page(p0_ket_noi.render, title="Kết nối dữ liệu", icon=":material/cable:", url_path="ket-noi", default=True),
        st.Page(p8_phuong_phap.render, title="Phương pháp & giới hạn", icon=":material/menu_book:", url_path="phuong-phap"),
    ]}
st.session_state["_pages"] = {pg.url_path: pg for grp in PAGES.values() for pg in grp}

mode = st.session_state["theme"]
register_plotly(mode)
st.markdown(css(mode), unsafe_allow_html=True)

nav = st.navigation(PAGES, position="hidden")
from src.app.components import sidebar  # noqa: E402

sidebar.render(PAGES, nav)
if st.session_state.pop("sb_search_go", False) and nav.url_path != "watchlist" and "watchlist" in st.session_state["_pages"]:
    st.switch_page(st.session_state["_pages"]["watchlist"])
nav.run()
