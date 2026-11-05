"""
FTSE Flow Radar – điểm vào ứng dụng Streamlit.

    streamlit run src/app/main.py

Chế độ DEMO_DATA=true: nếu kho chưa có chỉ báo, tự sinh dữ liệu mẫu tổng hợp và chạy toàn bộ chuỗi xử lý (~1–2 phút).
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
from src.common.config import get, is_demo  # noqa: E402

st.set_page_config(page_title=f"{get('app.name')}", page_icon="📡", layout="wide", initial_sidebar_state="expanded")
st.session_state.setdefault("theme", "light")
st.session_state.setdefault("bg_fx", False)  # B4.3: tắt hiệu ứng nền động, không còn tùy chọn bật

from src.app.pages import (p1_tong_quan, p2_dan_dat, p3_khoi_ngoai, p4_su_kien, p5_watchlist,  # noqa: E402
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
    ],
}
st.session_state["_pages"] = {pg.url_path: pg for grp in PAGES.values() for pg in grp}

mode = st.session_state["theme"]
register_plotly(mode)
st.markdown(css(mode), unsafe_allow_html=True)

if not da.ready():
    if is_demo():
        with st.spinner("Lần chạy đầu: đang sinh DỮ LIỆU MẪU tổng hợp và tính toàn bộ chỉ báo (khoảng 1–2 phút)…"):
            from src.data import rebuild_all
            rebuild_all.main(robustness=True, backtest=True)
            da.clear_cache()
    else:
        st.error("Kho chỉ báo trống. Chạy `python -m src.data.backfill` rồi `python -m src.data.rebuild_all`, "
                 "hoặc đặt DEMO_DATA=true trong .env để dùng dữ liệu mẫu.")
        st.stop()

nav = st.navigation(PAGES, position="hidden")
from src.app.components import sidebar  # noqa: E402

sidebar.render(PAGES, nav)
if st.session_state.pop("sb_search_go", False) and nav.url_path != "watchlist":
    st.switch_page(st.session_state["_pages"]["watchlist"])
nav.run()
