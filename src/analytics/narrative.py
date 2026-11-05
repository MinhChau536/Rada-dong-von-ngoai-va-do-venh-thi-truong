"""
Khuôn câu nhận định (bước B8.3) – KHÔNG dùng mô hình ngôn ngữ; mọi con số điền từ bảng chỉ báo
đã làm tròn bằng src.common.fmt nên truy vết được về chỉ báo gốc.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from src.common import fmt
from src.common.config import get
from src.finance.breadth import session_type_label
from src.finance.domestic import ABSORB_LABELS


def disclaimer(short: bool = True) -> str:
    return get("app.bot_disclaimer") if short else get("app.disclaimer")


def market_summary(day: pd.Series, leaders: Optional[pd.DataFrame] = None, with_disclaimer: bool = True) -> str:
    """Nhận định thị trường một phiên (khối B4.5e, PDF, /market)."""
    if day is None or len(day) == 0:
        return "Chưa có dữ liệu phiên."
    parts = []
    dI, r = day.get("dI"), day.get("r_vni_pct")
    n = int(day.get("n_valid") or 0)
    pct_down = (day.get("n_down") or 0) / n * 100 if n else None
    pct_up = day.get("pct_up")
    st = session_type_label(day.get("session_type", "flat"))
    lead = f"VN-Index {fmt.num(dI, 2, True)} điểm ({fmt.pct(r)})"
    if dI is not None and dI >= 0:
        parts.append(f"{lead} nhưng {fmt.num(pct_down, 0)}% số mã HOSE giảm." if pct_down and pct_down > 50
                     else f"{lead}, {fmt.num(pct_up, 0)}% số mã HOSE tăng.")
    else:
        parts.append(f"{lead} nhưng {fmt.num(pct_up, 0)}% số mã HOSE tăng." if pct_up and pct_up > 50
                     else f"{lead}, {fmt.num(pct_down, 0)}% số mã HOSE giảm.")
    parts.append(f"Loại phiên: {st.lower()}; trung vị lợi suất {fmt.pct(day.get('median_ret_pct'))}.")
    if leaders is not None and not leaders.empty and day.get("CR5") is not None:
        side = "pos" if (dI or 0) >= 0 else "neg"
        top = leaders[leaders["side"] == side].sort_values("rank").head(2)
        names = " và ".join(f"{x.symbol} ({fmt.num(x.C, 1, True)})" for x in top.itertuples())
        if names:
            parts.append(f"Năm mã tạo ra {fmt.frac_pct(day.get('CR5'), 0)} tổng đóng góp tuyệt đối, dẫn đầu là {names}.")
    ex = day.get("index_ex_vingroup_ret_pct")
    if ex is not None and not pd.isna(ex) and day.get("C_vingroup") is not None:
        parts.append(f"Nếu loại nhóm Vingroup, chỉ số {fmt.pct(ex)} (nhóm đóng góp {fmt.num(day.get('C_vingroup'), 1, True)} điểm).")
    p = day.get("D_pct250")
    if p is not None and not pd.isna(p):
        parts.append(f"Độ vênh D = {fmt.num(day.get('D'), 2, True)} đ.%, cao hơn {fmt.num(p, 0)}% số phiên trong một năm.")
    txt = " ".join(parts)
    return f"{txt} {disclaimer()}" if with_disclaimer else txt


def foreign_summary(day: pd.Series, top_buy: Optional[pd.DataFrame] = None, top_sell: Optional[pd.DataFrame] = None) -> str:
    nf = day.get("NF_total")
    verb = "mua ròng" if (nf or 0) >= 0 else "bán ròng"
    s = f"Khối ngoại {verb} {fmt.bn(abs(nf or 0), 0, False)} trên HOSE (z 60 phiên = {fmt.num(day.get('z_NF_total'), 2, True)}, HHI = {fmt.num(day.get('HHI'), 3)})."
    st = int(day.get("streak_total") or 0)
    if abs(st) >= 2:
        s += f" Chuỗi {abs(st)} phiên {'mua' if st > 0 else 'bán'} ròng liên tiếp."
    if top_sell is not None and not top_sell.empty and (nf or 0) < 0:
        s += " Tập trung bán: " + ", ".join(f"{x.symbol} ({fmt.bn(x.net_flow, 0)})" for x in top_sell.head(3).itertuples()) + "."
    if top_buy is not None and not top_buy.empty and (nf or 0) >= 0:
        s += " Tập trung mua: " + ", ".join(f"{x.symbol} ({fmt.bn(x.net_flow, 0)})" for x in top_buy.head(3).itertuples()) + "."
    return s


def stock_line(p: Dict) -> str:
    """Một câu nhận định cho mỗi mã watchlist (B7.6)."""
    if not p or p.get("ret") is None:
        return f"{p.get('symbol', '?')}: chưa có dữ liệu phiên."
    sym = p["symbol"]
    s = f"{sym} {fmt.pct(p['ret'] * 100)} so với trung vị thị trường {fmt.num(p['ER_M'] * 100, 2, True)} đ.%"
    if p.get("C") is not None:
        s += f", đóng góp {fmt.num(p['C'], 2, True)} điểm VN-Index"
        if p.get("leader_rank") and p["leader_rank"] <= 5:
            s += f" (hạng {p['leader_rank']} dẫn dắt)"
    s += "."
    if p.get("net_flow") is not None:
        s += f" Khối ngoại {'mua' if p['net_flow'] >= 0 else 'bán'} ròng {fmt.bn(abs(p['net_flow']), 1, False)}"
        if p.get("pct60_nf") is not None and not pd.isna(p["pct60_nf"]):
            s += f", cao hơn {fmt.num(p['pct60_nf'], 0)}% số phiên 60 ngày của mã"
        s += f"; trạng thái: {ABSORB_LABELS.get(p.get('absorb_state', 'neutral'), 'Trung tính').lower()}."
    if p.get("beta_dimson") is not None and not pd.isna(p["beta_dimson"]):
        s += f" β Dimson = {fmt.num(p['beta_dimson'], 2)}."
    return s
