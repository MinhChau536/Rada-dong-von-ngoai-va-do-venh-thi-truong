"""
Định dạng số kiểu Việt Nam (dấu chấm phân cách nghìn, dấu phẩy thập phân) – dùng CHUNG cho giao diện,
PDF và Telegram để ba kênh hiển thị con số giống hệt nhau (bước B12.5).
"""
from __future__ import annotations

import math
from typing import Optional


def _isnull(v) -> bool:
    try:
        return v is None or (isinstance(v, float) and math.isnan(v)) or v != v
    except Exception:
        return False


def num(v, d: int = 2, sign: bool = False, suffix: str = "", na: str = "—") -> str:
    if _isnull(v):
        return na
    s = f"{float(v):+,.{d}f}" if sign else f"{float(v):,.{d}f}"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return s + suffix


def pct(v, d: int = 2, sign: bool = True, na: str = "—") -> str:
    """v đã ở đơn vị % (ví dụ 0,44 nghĩa là 0,44%)."""
    return num(v, d, sign, "%", na)


def frac_pct(v, d: int = 1, sign: bool = False, na: str = "—") -> str:
    """v là phân số (0,71 → 71%)."""
    return na if _isnull(v) else pct(float(v) * 100, d, sign)


def bn(v_vnd, d: int = 0, sign: bool = True, na: str = "—") -> str:
    """VND → tỷ đồng."""
    return na if _isnull(v_vnd) else num(float(v_vnd) / 1e9, d, sign, " tỷ")


def price(v, na: str = "—") -> str:
    return num(v, 0, False, "", na)


def arrow(v: Optional[float]) -> str:
    if _isnull(v):
        return ""
    return "▲" if v > 1e-9 else "▼" if v < -1e-9 else "■"
