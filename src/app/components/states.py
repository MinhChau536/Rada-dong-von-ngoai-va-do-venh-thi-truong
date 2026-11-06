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


# Nội dung từng trang theo thuyết minh mục 11.3 – hiển thị khi kho chỉ báo còn trống (không vẽ số liệu giả)
PAGE_FEATURES = {
    "tong-quan": ["4 thẻ VN-Index, VN30, HNX, UPCoM kèm sparkline 40 phiên", "Chất lượng xu hướng: trung vị lợi suất, "
                  "độ vênh D, CR5, khối ngoại ròng, loại phiên", "Dải danh mục theo dõi kèm trạng thái hấp thụ",
                  "Biểu đồ nến có mốc FTSE + đồng hồ sức khỏe thị trường", "Mã dẫn dắt VN-Index, đóng góp theo họ & ngành",
                  "Độ rộng thị trường (trần/tăng/đứng/giảm/sàn)", "Bản đồ nhiệt & ngành", "Dòng vốn khối ngoại hôm nay",
                  "Cổ phiếu nổi bật", "So sánh hiệu suất"],
    "dan-dat": ["Thác nước đóng góp điểm theo mã và ngành", "Chuỗi độ vênh D với dải phân vị 10–90",
                "VN-Index loại trừ một họ cổ phiếu (ví dụ Vingroup)", "Phân phối CR5", "Lịch sử loại phiên"],
    "khoi-ngoai": ["Bảng xếp hạng NF, nf, z-score, chuỗi phiên, room đã dùng", "HHI tập trung dòng vốn theo thời gian",
                   "Dòng vốn theo nhóm FTSE / VN30 / đối chứng / ngành", "Trạng thái hấp thụ của khối nội", "Tỷ trọng lô lẻ"],
    "su-kien-ftse": ["CAAR và CAFF quanh E1, E2, E3 cho nhóm FTSE và nhóm đối chứng", "Bảng kiểm định t, BMP, dấu, bootstrap",
                     "Đồ thị hệ số chênh lệch kép (DiD)"],
    "watchlist": ["Thêm/xóa mã theo dõi", "Hồ sơ phản ứng từng mã: ER, beta Dimson, đóng góp chỉ số, phân vị nf",
                  "So sánh hiệu suất chuẩn hóa", "Phản ứng theo loại phiên", "Tin liên quan (nguồn bổ trợ)"],
    "bao-cao": ["Xuất PDF Market Snapshot và Closing Report", "Lịch sử báo cáo", "Cấu hình và nhật ký cảnh báo Telegram"],
    "chat-luong": ["Trạng thái SSI và NEO, lịch sử chuyển nguồn", "Độ đầy đủ theo phiên, sai số tái lập ε",
                   "Đối chiếu độ rộng và đối chiếu SSI–NEO", "Thống kê luồng NEO WebSocket, nhật ký lỗi"],
}


def page_waiting(title: str, url_path: str) -> None:
    """Trang chưa có dữ liệu: nói rõ lý do, liệt kê nội dung sẽ hiển thị, dẫn tới trang Kết nối dữ liệu."""
    from src.app.components.ui import esc, header, md, pal
    p = pal()
    header(title, "Chưa có dữ liệu thật trong kho – trang sẽ tự hiển thị sau khi tải dữ liệu từ API")
    items = "".join(f"<li>{esc(x)}</li>" for x in PAGE_FEATURES.get(url_path, []))
    md(f'<div class="ffr-card"><div class="ffr-lbl">Trang này sẽ hiển thị</div>'
       f'<ul style="margin:8px 0 4px 18px;line-height:1.8;font-size:14px">{items}</ul>'
       f'<div style="font-size:13px;color:{p["muted"]};margin-top:8px">Ứng dụng không dùng dữ liệu giả lập. '
       f'Kho chỉ báo đang trống vì chưa tải được dữ liệu từ SSI (hoặc chưa có phiên nào ghi từ luồng NEO).</div></div>')
    pg = st.session_state.get("_pages", {}).get("ket-noi")
    if pg is not None:
        st.page_link(pg, label="→ Mở trang Kết nối dữ liệu để kiểm tra và tải dữ liệu", icon=":material/cable:")
