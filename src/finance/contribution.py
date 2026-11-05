"""
Module A – Phân rã đóng góp điểm VN-Index (bước B3.4–B3.7).

  (4) w_i,t = S_i·P^ref_i,t / Σ_j S_j·P^ref_j,t ;   C_i,t = I_{t−1} · w_i,t · r_i,t       [điểm]
  (5) ε_t   = (I_t − I_{t−1}) − Σ_i C_i,t ;          CR5_t = Σ_{Top5}|C| / Σ|C|

Xấp xỉ vì số cổ phiếu niêm yết khác số cổ phiếu lưu hành dùng tính chỉ số (cổ phiếu quỹ, free-float).
Nếu trung vị |ε| ≥ 0,5 điểm: ước lượng hệ số k (hồi quy ΔI trên ΣC không hệ số chặn) và dùng C·k.
Chỉ số loại trừ nhóm g: I_{t−1} + Σ_{i∉g} C_i,t.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from src.common.config import get


def contributions(stock: pd.DataFrame, index: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    stock: trade_date, symbol, ref, ret, is_valid, listed_share
    index: trade_date (index), value, prev_value
    Trả về (stock có w, C, C_raw), (bảng ngày: dI, sumC, eps, CR5…), meta {scale_k, eps_median_raw, eps_median}
    """
    d = stock.copy()
    mask = d["is_valid"] & d["listed_share"].gt(0) & d["ref"].gt(0)
    d["cap_ref"] = np.where(mask, d["listed_share"] * d["ref"], 0.0)
    tot = d.groupby("trade_date")["cap_ref"].transform("sum")
    d["w"] = np.where(tot > 0, d["cap_ref"] / tot, 0.0)
    prev = d["trade_date"].map(index["prev_value"])
    d["C_raw"] = prev * d["w"] * d["ret"].fillna(0)
    day = pd.DataFrame({"sumC_raw": d.groupby("trade_date")["C_raw"].sum()})
    day = day.join(index[["value", "prev_value"]], how="left")
    day["dI"] = day["value"] - day["prev_value"]
    day["eps_raw"] = day["dI"] - day["sumC_raw"]
    ok = day.dropna(subset=["dI", "sumC_raw"])
    eps_med_raw = float(ok["eps_raw"].abs().median()) if len(ok) else np.nan
    k = 1.0
    if len(ok) > 5 and eps_med_raw >= float(get("contribution.eps_median_target", 0.5)):
        x, y = ok["sumC_raw"].to_numpy(), ok["dI"].to_numpy()
        k = float((x @ y) / (x @ x)) if (x @ x) > 0 else 1.0
    d["C"] = d["C_raw"] * k
    day["sumC"] = day["sumC_raw"] * k
    day["eps"] = day["dI"] - day["sumC"]
    eps_med = float(day["eps"].abs().median()) if day["eps"].notna().any() else np.nan
    absC = d.assign(absC=d["C"].abs())
    tot_abs = absC.groupby("trade_date")["absC"].sum()
    top5 = absC.sort_values("absC", ascending=False).groupby("trade_date").head(int(get("contribution.top_n", 5)))
    day["CR5"] = top5.groupby("trade_date")["absC"].sum() / tot_abs.replace(0, np.nan)
    return d.drop(columns=["cap_ref"]), day, {"scale_k": k, "eps_median_raw": eps_med_raw, "eps_median": eps_med}


def leaders(stock: pd.DataFrame, day: pd.DataFrame, n: int | None = None) -> pd.DataFrame:
    """Top n đóng góp dương và âm mỗi phiên, kèm tỷ lệ % trong ΔI."""
    n = n or int(get("contribution.top_n", 5))
    v = stock[["trade_date", "symbol", "C", "ret"]].dropna(subset=["C"])
    pos = v[v["C"] > 0].sort_values("C", ascending=False).groupby("trade_date").head(n).copy()
    neg = v[v["C"] < 0].sort_values("C", ascending=True).groupby("trade_date").head(n).copy()
    pos["side"], neg["side"] = "pos", "neg"
    out = pd.concat([pos, neg], ignore_index=True)
    out["rank"] = out.groupby(["trade_date", "side"])["C"].rank(method="first", ascending=False)
    out.loc[out["side"] == "neg", "rank"] = out[out["side"] == "neg"].groupby("trade_date")["C"].rank(method="first")
    out["rank"] = out["rank"].astype(int)
    dI = out["trade_date"].map(day["dI"])
    out["share_of_dI"] = np.where(dI.abs() > 1e-9, out["C"] / dI * 100, np.nan)
    return out.sort_values(["trade_date", "side", "rank"]).reset_index(drop=True)


def group_contrib(stock: pd.DataFrame, mapping: pd.Series, group_type: str, day: pd.DataFrame) -> pd.DataFrame:
    """Tổng C theo nhóm (ngành / họ cổ phiếu) và chỉ số loại trừ nhóm."""
    d = stock.copy()
    d["grp"] = d["symbol"].map(mapping)
    d = d.dropna(subset=["grp"])
    g = d.groupby(["trade_date", "grp"]).agg(C=("C", "sum"), n=("symbol", "nunique"), w=("w", "sum")).reset_index()
    g["group_type"] = group_type
    prev = g["trade_date"].map(day["prev_value"])
    sumc = g["trade_date"].map(day["sumC"])
    g["index_ex_group"] = prev + (sumc - g["C"])
    g["index_ex_group_ret_pct"] = (sumc - g["C"]) / prev * 100
    return g.rename(columns={"grp": "group_name"})
