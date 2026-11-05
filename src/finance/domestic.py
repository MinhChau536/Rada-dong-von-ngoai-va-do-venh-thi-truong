"""
Module B – Đối chiếu khối nội (bước B5.7, B5.8).

Mua ròng khối nội = − bán ròng khối ngoại (không mang thông tin độc lập) nên KHÔNG xây chỉ số
"sức mạnh dòng tiền nội". Thay vào đó dùng 4 thước đo: FPR, trạng thái hấp thụ, tỷ trọng lô lẻ,
mất cân bằng mua/bán chủ động (X-TRADE Side).

Bảng trạng thái hấp thụ (mục 8.3) – chỉ gán khi |nf| ≥ 0,05 và |r| ≥ 0,5%, còn lại 'neutral':
  Bán ròng + Tăng → absorb (Khối nội hấp thụ)     Bán ròng + Giảm → joint_sell (Đồng thuận bán)
  Mua ròng + Tăng → joint_buy (Đồng thuận mua)    Mua ròng + Giảm → domestic_take (Khối nội chốt hàng)
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from src.common.config import get

ABSORB_LABELS = {
    "absorb": "Khối nội hấp thụ",
    "joint_sell": "Đồng thuận bán",
    "joint_buy": "Đồng thuận mua",
    "domestic_take": "Khối nội chốt hàng",
    "neutral": "Trung tính",
}


def absorb_state(nf: float, r: float, nf_min: Optional[float] = None, r_min: Optional[float] = None) -> str:
    nf_min = float(get("foreign.absorb_nf_min", 0.05)) if nf_min is None else nf_min
    r_min = float(get("foreign.absorb_ret_min", 0.005)) if r_min is None else r_min
    if nf is None or r is None or np.isnan(nf) or np.isnan(r):
        return "neutral"
    if abs(nf) < nf_min or abs(r) < r_min:
        return "neutral"
    if nf < 0:
        return "absorb" if r > 0 else "joint_sell"
    return "joint_buy" if r > 0 else "domestic_take"


def absorb_states(nf: pd.Series, r: pd.Series) -> pd.Series:
    nf_min = float(get("foreign.absorb_nf_min", 0.05))
    r_min = float(get("foreign.absorb_ret_min", 0.005))
    a, b = nf.to_numpy(dtype=float), r.to_numpy(dtype=float)
    out = np.full(len(a), "neutral", dtype=object)
    sig = (np.abs(a) >= nf_min) & (np.abs(b) >= r_min) & ~np.isnan(a) & ~np.isnan(b)
    out[sig & (a < 0) & (b > 0)] = "absorb"
    out[sig & (a < 0) & (b < 0)] = "joint_sell"
    out[sig & (a > 0) & (b > 0)] = "joint_buy"
    out[sig & (a > 0) & (b < 0)] = "domestic_take"
    return pd.Series(out, index=nf.index)


def absorption_rate(states: pd.Series) -> float:
    """Tỷ lệ phiên 'khối nội hấp thụ' trong số phiên khối ngoại bán ròng có ý nghĩa."""
    s = states[states.isin(["absorb", "joint_sell"])]
    return float((s == "absorb").mean()) if len(s) else float("nan")


def active_imbalance(trades: pd.DataFrame) -> pd.DataFrame:
    """(BU − SD)/(BU + SD) theo mã từ kênh X-TRADE (cột symbol, side, vol)."""
    if trades is None or trades.empty:
        return pd.DataFrame(columns=["symbol", "BU", "SD", "imbalance"])
    t = trades.copy()
    t["side"] = t["side"].astype(str).str.upper()
    p = t.pivot_table(index="symbol", columns="side", values="vol", aggfunc="sum", fill_value=0)
    bu = p.get("BU", pd.Series(0, index=p.index))
    sd = p.get("SD", pd.Series(0, index=p.index))
    out = pd.DataFrame({"BU": bu, "SD": sd})
    out["imbalance"] = (out["BU"] - out["SD"]) / (out["BU"] + out["SD"]).replace(0, np.nan)
    return out.reset_index()


def oddlot_share(oddlot_value: pd.Series, total_value: pd.Series) -> pd.Series:
    return oddlot_value / total_value.replace(0, np.nan)
