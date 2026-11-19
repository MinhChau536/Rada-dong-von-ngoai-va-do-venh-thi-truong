"""Trang "Kiểm chứng & dữ liệu": gộp Backtest, Chất lượng dữ liệu và Kết nối dữ liệu thành 3 tab (giảm số trang)."""
from __future__ import annotations

import streamlit as st

from src.app.components import status_bar
from src.app.components.ui import header
from src.app.views import p0_ket_noi, p7_chat_luong, p10_backtest


def render() -> None:
    header("Kiểm chứng & dữ liệu", "Backtest trên dữ liệu lịch sử · chất lượng và đối chiếu dữ liệu · kết nối SSI FastConnect V3")
    status_bar.render()
    t1, t2, t3 = st.tabs(["🧪 Backtest", "✅ Chất lượng dữ liệu", "🔌 Kết nối dữ liệu"])
    with t1:
        p10_backtest.render(embedded=True)
    with t2:
        p7_chat_luong.render(embedded=True)
    with t3:
        p0_ket_noi.render(embedded=True)
