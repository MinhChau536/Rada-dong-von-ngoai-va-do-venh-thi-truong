"""
Module B – Dòng vốn ngoại (bước B5.1–B5.6).

  (6) NF = FB − FS ;  nf = NF / mẫu số ;  FPR = (FB + FS) / (2·mẫu số)
      mẫu số = TV (khớp lệnh) hoặc TV + TV_pt nếu trường khối ngoại gồm thỏa thuận (chốt ở B2.5)
  (7) HHI_t = Σ_i (|NF_i| / Σ_j |NF_j|)² ;  U = 1 − Remain / Room
  (8) z_i,t = (nf_i,t − mean_[t−60,t−1]) / sd_[t−60,t−1]
Chuỗi phiên: số phiên mua/bán ròng liên tiếp; đảo chiều: phiên đổi dấu sau chuỗi ≥ 3.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from src.common.config import get
from src.finance.utils import rolling_pct_rank, rolling_z, safe_div, streaks


def decide_denominator(df: pd.DataFrame) -> Dict:
    """
    B2.5 – Trường khối ngoại là khớp lệnh hay gồm thỏa thuận?
    Nếu nhiều mã có (FB+FS)/2 > TV ở phiên có thỏa thuận lớn → gồm thỏa thuận → dùng TV + TV_pt.
    """
    mode = get("foreign.denominator", "auto")
    d = df[(df["tv"] > 0)].copy()
    gross_half = (d["fb"].fillna(0) + d["fs"].fillna(0)) / 2
    exceed = (gross_half > d["tv"] * 1.001)
    big_deal = d["tv_pt"].fillna(0) > 0.2 * d["tv"]
    share_exceed_all = float(exceed.mean()) if len(d) else 0.0
    share_exceed_deal = float(exceed[big_deal].mean()) if big_deal.any() else 0.0
    includes_deal = share_exceed_deal > 0.05
    if mode == "match":
        chosen = "match"
    elif mode == "match_plus_deal":
        chosen = "match_plus_deal"
    else:
        chosen = "match_plus_deal" if includes_deal else "match"
    return {"chosen": chosen, "includes_deal": includes_deal, "share_exceed_all": share_exceed_all,
            "share_exceed_bigdeal": share_exceed_deal, "n_bigdeal": int(big_deal.sum()), "n_obs": int(len(d))}


def stock_flows(df: pd.DataFrame, denominator: str = "match") -> pd.DataFrame:
    """Chỉ báo dòng vốn theo mã × phiên. df cần: trade_date, symbol, fb, fs, tv, tv_pt, remain, room."""
    d = df.sort_values(["symbol", "trade_date"]).copy()
    denom = d["tv"] + (d["tv_pt"].fillna(0) if denominator == "match_plus_deal" else 0)
    d["net_flow"] = d["fb"] - d["fs"]
    d["nf"] = safe_div(d["net_flow"], denom)
    d["FPR"] = safe_div(d["fb"] + d["fs"], 2 * denom)
    d["U"] = 1 - safe_div(d["remain"], d["room"])
    d["U"] = d["U"].clip(0, 1)
    room_prev = d.groupby("symbol")["room"].shift(1)
    d["room_changed"] = room_prev.notna() & (d["room"] - room_prev).abs().gt(1e-6 * d["room"].abs())
    zw = int(get("windows.z_window", 60))
    rmin = int(get("foreign.streak_reversal_min", 3))
    parts = []
    for _, g in d.groupby("symbol", sort=False):
        g = g.copy()
        g["z_nf"] = rolling_z(g["nf"], zw)
        g["pct60_nf"] = rolling_pct_rank(g["nf"], zw)
        st = streaks(g["net_flow"])
        g["streak"] = st
        prev = st.shift(1).fillna(0)
        g["reversal"] = (np.sign(st) != np.sign(prev)) & (prev.abs() >= rmin) & (st != 0)
        parts.append(g)
    return pd.concat(parts).sort_values(["trade_date", "symbol"])


def market_flows(stock: pd.DataFrame) -> pd.DataFrame:
    """Chỉ báo dòng vốn toàn sàn mỗi phiên: NF tổng, HHI, tỷ trọng Top5, FPR toàn sàn, z tổng NF."""
    v = stock[stock["is_valid"]].copy()
    v["absNF"] = v["net_flow"].abs()
    g = v.groupby("trade_date")
    out = pd.DataFrame({
        "NF_total": g["net_flow"].sum(), "FB_total": g["fb"].sum(), "FS_total": g["fs"].sum(),
        "tv_total_f": g["tv"].sum(), "absNF_total": g["absNF"].sum(),
    })
    share2 = v.assign(sh=v["absNF"] / v["trade_date"].map(out["absNF_total"]).replace(0, np.nan))
    out["HHI"] = share2.groupby("trade_date")["sh"].apply(lambda s: float((s ** 2).sum()))
    top5 = v.sort_values("absNF", ascending=False).groupby("trade_date").head(5)
    out["top5_share_flow"] = top5.groupby("trade_date")["absNF"].sum() / out["absNF_total"].replace(0, np.nan)
    out["FPR_total"] = (out["FB_total"] + out["FS_total"]) / (2 * out["tv_total_f"].replace(0, np.nan))
    out["nf_total_ratio"] = out["NF_total"] / out["tv_total_f"].replace(0, np.nan)
    zw = int(get("windows.z_window", 60))
    out["z_NF_total"] = rolling_z(out["NF_total"], zw)
    # Chuỗi phiên toàn sàn & phân vị lịch sử tổng NF
    out["streak_total"] = streaks(out["NF_total"]).values
    out["NF_total_pct60"] = rolling_pct_rank(out["NF_total"], zw)
    return out.drop(columns=["tv_total_f"])


def group_flows(stock: pd.DataFrame, mapping: pd.Series, group_type: str) -> pd.DataFrame:
    d = stock[stock["is_valid"]].copy()
    d["grp"] = d["symbol"].map(mapping)
    d = d.dropna(subset=["grp"])
    g = d.groupby(["trade_date", "grp"]).agg(net_flow=("net_flow", "sum"), FB=("fb", "sum"), FS=("fs", "sum"),
                                              TV=("tv", "sum"), n=("symbol", "nunique"),
                                              ret_eq=("ret", "mean")).reset_index()
    g["nf"] = g["net_flow"] / g["TV"].replace(0, np.nan)
    g["FPR"] = (g["FB"] + g["FS"]) / (2 * g["TV"].replace(0, np.nan))
    g["group_type"] = group_type
    return g.rename(columns={"grp": "group_name"})
