"""
Ba trạng thái hiển thị cho mọi thẻ, biểu đồ, bảng (bước B4.7, mục 6 của đề):
đang tải · không có dữ liệu (kèm lý do) · lỗi nguồn (nguồn lỗi, thời điểm dữ liệu gần nhất).
Bọc mọi lệnh gọi dữ liệu để ứng dụng không dừng khi lỗi; không hiển thị số cũ như số mới.
"""
from __future__ import annotations

import functools
import traceback
from datetime import date
from typing import Callable, Optional

import pandas as pd
import streamlit as st

from src.common.logging import get_logger

log = get_logger(__name__)


def no_data_reason(d: Optional[date] = None, symbol: Optional[str] = None) -> str:
    if d is not None:
        ts = pd.Timestamp(d)
        if ts.weekday() >= 5:
            return "Ngày nghỉ cuối tuần – không có phiên giao dịch."
    if symbol:
        return f"{symbol}: chưa có dữ liệu phiên (mã tạm ngừng, chưa niêm yết hoặc ngoài rổ dữ liệu)."
    return "Không có dữ liệu cho lựa chọn hiện tại (ngoài giờ giao dịch, ngày nghỉ hoặc chưa tải)."


def empty(msg: str) -> None:
    st.info(f"ℹ️ {msg}")


def source_error(source: str, exc: Exception, last_ok: Optional[str] = None) -> None:
    extra = f" Dữ liệu gần nhất: {last_ok}." if last_ok else ""
    st.warning(f"⚠️ Lỗi nguồn {source}: {exc}.{extra} Số liệu cũ KHÔNG được hiển thị như số mới.")


def safe_block(title: str = "khối") -> Callable:
    """Decorator: khối giao diện lỗi → cảnh báo thay vì làm dừng cả trang."""
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrap(*a, **k):
            try:
                return fn(*a, **k)
            except Exception as exc:  # noqa: BLE001
                log.error("Lỗi khối %s: %s\n%s", title, exc, traceback.format_exc())
                st.warning(f"⚠️ Không hiển thị được {title}: {exc}")
                return None
        return wrap
    return deco
