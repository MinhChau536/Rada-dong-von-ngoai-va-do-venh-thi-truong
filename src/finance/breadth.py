"""
Module A – Điểm vênh, độ rộng, phân tán, phân loại phiên (bước B2.2, B2.3, B3.1–B3.3).

  (1) r_i,t   = P^c_i,t / P^ref_i,t − 1
  (2) D_t     = r_VNI,t − median_{i∈Ω_t}(r_i,t)                [điểm %]
  (3) AD_t    = (N⁺ − N⁻) / (N⁺ + N⁻ + N⁰);  IQR_t = Q75 − Q25 [điểm %]

Ω_t: cổ phiếu thường HOSE, P_ref > 0, giá trị khớp > 0 (loại mã tạm ngừng).
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from src.common.config import get
from src.finance.utils import rolling_past_quantile

SESSION_TYPES = {
    "broad_up": "Tăng lan rộng",
    "narrow_up": "Tăng thiếu lan tỏa",
    "narrow_down": "Giảm thiếu lan tỏa",
    "broad_down": "Giảm đồng thuận",
    "flat": "Đi ngang",
}


def add_validity(df: pd.DataFrame, sec_type: pd.Series | None = None) -> pd.DataFrame:
    """Gắn is_valid, is_ceiling, is_floor, ret (công thức 1)."""
    d = df.copy()
    st_ok = True if sec_type is None else d["symbol"].map(sec_type).fillna("ST").eq("ST")
    d["is_valid"] = st_ok & (d["ref"] > 0) & (d["tv"].fillna(0) > 0) & d["close"].notna()
    d["ret"] = np.where(d["ref"] > 0, d["close"] / d["ref"] - 1, np.nan)
    d["is_ceiling"] = d["is_valid"] & (d["close"] >= d["ceiling"]) & d["ceiling"].notna()
    d["is_floor"] = d["is_valid"] & (d["close"] <= d["floor"]) & d["floor"].notna()
    return d


def classify_session(r_vni_pct: float, ad: float, flat_pct: float | None = None) -> str:
    """Quy tắc mục 8.2: đi ngang nếu |r_VNI| < 0,1%; còn lại theo dấu r_VNI và AD."""
    flat = get("breadth.flat_threshold_pct", 0.1) if flat_pct is None else flat_pct
    if r_vni_pct is None or np.isnan(r_vni_pct):
        return "flat"
    if abs(r_vni_pct) < flat:
        return "flat"
    if r_vni_pct > 0:
        return "broad_up" if ad > 0 else "narrow_up"
    return "broad_down" if ad < 0 else "narrow_down"


def daily_breadth(stock: pd.DataFrame, r_vni: pd.Series) -> pd.DataFrame:
    """
    stock: cột trade_date, ret, is_valid, is_ceiling, is_floor, tv
    r_vni: Series lợi suất VN-Index (phân số) theo trade_date
    """
    v = stock[stock["is_valid"]]
    eps = 1e-12
    g = v.groupby("trade_date")
    out = pd.DataFrame({
        "n_valid": g.size(),
        "median_ret_pct": g["ret"].median() * 100,
        "mean_ret_pct": g["ret"].mean() * 100,
        "q25_pct": g["ret"].quantile(0.25) * 100,
        "q75_pct": g["ret"].quantile(0.75) * 100,
        "n_up": g["ret"].apply(lambda s: int((s > eps).sum())),
        "n_down": g["ret"].apply(lambda s: int((s < -eps).sum())),
        "n_ceiling": g["is_ceiling"].sum().astype(int),
        "n_floor": g["is_floor"].sum().astype(int),
        "tv_total": g["tv"].sum(),
    })
    out["n_unch"] = out["n_valid"] - out["n_up"] - out["n_down"]
    out["AD"] = (out["n_up"] - out["n_down"]) / out["n_valid"].replace(0, np.nan)
    out["pct_up"] = out["n_up"] / out["n_valid"].replace(0, np.nan) * 100
    out["IQR_pct"] = out["q75_pct"] - out["q25_pct"]
    out["r_vni_pct"] = r_vni.reindex(out.index) * 100
    out["D"] = out["r_vni_pct"] - out["median_ret_pct"]                          # công thức (2), điểm %
    out["session_type"] = [classify_session(r, a) for r, a in zip(out["r_vni_pct"], out["AD"])]
    w = int(get("windows.high_div_window", 250))
    q = float(get("windows.high_div_pct", 90)) / 100
    thr = rolling_past_quantile(out["D"], w, q)
    out["D_p90_thr"] = thr
    out["high_divergence"] = (out["D"] >= thr) & thr.notna()
    return out


def session_type_label(code: str) -> str:
    return SESSION_TYPES.get(code, code)


def breadth_check(self_count: pd.DataFrame, ssi_index: pd.DataFrame) -> pd.DataFrame:
    """Đối chiếu độ rộng (B2.4): chênh lệch = tự đếm − SSI Advances/Declines/NoChanges."""
    m = self_count[["n_up", "n_down", "n_unch"]].join(
        ssi_index.set_index("trade_date")[["advances", "declines", "no_changes"]], how="inner")
    m["diff_up"] = m["n_up"] - m["advances"]
    m["diff_down"] = m["n_down"] - m["declines"]
    m["diff_unch"] = m["n_unch"] - m["no_changes"]
    m["max_abs_diff"] = m[["diff_up", "diff_down", "diff_unch"]].abs().max(axis=1)
    return m


def breadth_summary(snap: pd.DataFrame) -> Dict:
    """Thống kê độ rộng cho một rổ bất kỳ trong một phiên (giao diện khối B4.5f)."""
    if snap is None or snap.empty:
        return {"available": False}
    v = snap[snap["is_valid"]] if "is_valid" in snap else snap
    r = v["ret"]
    n_ce = int(v.get("is_ceiling", pd.Series(False, index=v.index)).sum())
    n_fl = int(v.get("is_floor", pd.Series(False, index=v.index)).sum())
    up, dn = int((r > 1e-12).sum()), int((r < -1e-12).sum())
    n = int(len(v))
    return {
        "available": n > 0, "total": n, "up": up - n_ce, "ceiling": n_ce, "down": dn - n_fl, "floor": n_fl,
        "unch": n - up - dn, "advancing": up, "declining": dn,
        "AD": (up - dn) / n if n else None,
        "eq_ret_pct": float(r.mean() * 100) if n else None,
        "median_pct": float(r.median() * 100) if n else None,
        "pct_above_ma20": float(v["above_ma20"].mean() * 100) if "above_ma20" in v and n else None,
        "new_high20": int(v["new_high20"].sum()) if "new_high20" in v else 0,
        "new_low20": int(v["new_low20"].sum()) if "new_low20" in v else 0,
        "tv_bn": float(v["tv"].sum() / 1e9) if "tv" in v else None,
    }
