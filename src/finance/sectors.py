"""
Phân ngành theo chuẩn ICB do SSI FastConnect V3 trả về (securities: icbCode, icbName) – KHÔNG gán ngành thủ công.

Mã ICB 4 chữ số của SSI được gộp thành ~20 nhóm ngành quen thuộc với nhà đầu tư Việt Nam theo tiền tố mã
(quy tắc cố định dưới đây). Mã không có ICB (đã hủy niêm yết, chưa có trong danh mục SSI) → "Khác".
"""
from __future__ import annotations

from typing import Optional

# (tiền tố mã ICB, nhóm ngành) – so khớp tiền tố DÀI NHẤT trước
ICB_SECTORS = [
    ("05", "Dầu khí & Năng lượng"), ("7573", "Dầu khí & Năng lượng"),
    ("1353", "Cao su & Nhựa"), ("1357", "Hóa chất & Phân bón"),
    ("1733", "Gỗ, Giấy & Bao bì"), ("1737", "Gỗ, Giấy & Bao bì"), ("2723", "Gỗ, Giấy & Bao bì"),
    ("1757", "Thép & VLXD"), ("2353", "Thép & VLXD"), ("1775", "Khai khoáng"),
    ("2357", "Xây dựng"),
    ("277", "Hàng không & Vận tải"), ("5751", "Hàng không & Vận tải"), ("5759", "Hàng không & Vận tải"),
    ("27", "Công nghiệp & Thiết bị"),
    ("335", "Ô tô & Phụ tùng"),
    ("3573", "Nông nghiệp & Thủy sản"), ("353", "Thực phẩm & Đồ uống"), ("357", "Thực phẩm & Đồ uống"),
    ("3785", "Thực phẩm & Đồ uống"), ("3763", "Dệt may"),
    ("37", "Bán lẻ & Tiêu dùng"), ("53", "Bán lẻ & Tiêu dùng"),
    ("45", "Y tế & Dược phẩm"),
    ("555", "Du lịch & Giải trí"), ("575", "Du lịch & Giải trí"),
    ("7535", "Tiện ích"), ("7577", "Tiện ích"), ("75", "Tiện ích"),
    ("8355", "Ngân hàng"), ("85", "Bảo hiểm"), ("86", "Bất động sản"), ("8777", "Chứng khoán"), ("87", "Dịch vụ tài chính"),
    ("95", "Công nghệ"), ("65", "Công nghệ"),
]
_SORTED = sorted(ICB_SECTORS, key=lambda kv: -len(kv[0]))


def sector_of(icb_code: Optional[str]) -> str:
    code = str(icb_code or "").strip()
    if not code or code in ("None", "nan"):
        return "Khác"
    for pre, name in _SORTED:
        if code.startswith(pre):
            return name
    return "Khác"
