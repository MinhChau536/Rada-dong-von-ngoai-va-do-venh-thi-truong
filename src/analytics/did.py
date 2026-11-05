"""
Module C – Ước lượng chênh lệch kép (bước B6.6, giả thuyết H3c).

  (11) y_i,t = μ_i + λ_t + δ·(FTSE_i × Post_t) + ε_i,t        trên cửa sổ [−60; +60] quanh E3
  y ∈ {nf, ln TV, FPR}; hiệu ứng cố định mã và phiên; sai số chuẩn cụm theo mã (linearmodels.PanelOLS).
  Kiểm tra xu hướng song song: hệ số FTSE × tuần tương đối (−8…+8, bỏ tuần −1 làm gốc).
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from src.common.config import control_group, events, ftse_universe, get
from src.common.logging import get_logger

log = get_logger(__name__)
OUTCOMES = {"nf": "nf", "ln_tv": "ln TV", "FPR": "FPR"}


def build_panel(stock: pd.DataFrame, control_col: str = "control_symbol") -> pd.DataFrame:
    ev = events().set_index("event_id")
    eid = get("events.did_event", "E3")
    edate = ev.loc[eid, "event_date"]
    w0, w1 = get("events.did_window", [-60, 60])
    ftse = set(ftse_universe()["symbol"])
    cg = control_group()
    ctrl = set(cg[control_col].dropna()) if not cg.empty and control_col in cg else set()
    dates = np.sort(pd.to_datetime(stock["trade_date"].unique()))
    pos = int(np.searchsorted(dates, np.datetime64(edate)))
    keep = dates[max(0, pos + w0): min(len(dates), pos + w1 + 1)]
    d = stock[stock["trade_date"].isin(keep) & stock["symbol"].isin(ftse | ctrl) & stock["is_valid"]].copy()
    d["FTSE"] = d["symbol"].isin(ftse).astype(int)
    rel = {dt: i - pos for i, dt in enumerate(dates)}
    d["rel"] = d["trade_date"].map(lambda x: rel[np.datetime64(x)])
    d["Post"] = (d["rel"] >= 0).astype(int)
    d["treat_post"] = d["FTSE"] * d["Post"]
    d["ln_tv"] = np.log(d["tv"].where(d["tv"] > 0))
    d["week"] = np.floor(d["rel"] / 5).astype(int)
    return d


def estimate(stock: pd.DataFrame, control_col: str = "control_symbol", variant: str = "base") -> Dict[str, pd.DataFrame]:
    from linearmodels.panel import PanelOLS

    d = build_panel(stock, control_col)
    rows: List[Dict] = []
    coefs: List[Dict] = []
    if d.empty or d["FTSE"].nunique() < 2 or d["Post"].nunique() < 2:
        return {"stats": pd.DataFrame(), "did_coefs": pd.DataFrame()}
    p = d.set_index(["symbol", "trade_date"]).sort_index()
    wk_lo, wk_hi = get("events.did_weeks", [-8, 8])
    for y, label in OUTCOMES.items():
        sub = p.dropna(subset=[y])
        try:
            mod = PanelOLS(sub[y], sub[["treat_post"]], entity_effects=True, time_effects=True)
            res = mod.fit(cov_type="clustered", cluster_entity=True)
            rows.append({"hypothesis": "H3c", "metric": label, "event_id": get("events.did_event", "E3"),
                         "group": "FTSE−CONTROL", "window": str(get("events.did_window", [-60, 60])), "model": "DiD TWFE",
                         "variant": variant, "test": "PanelOLS δ (cụm theo mã)", "statistic": float(res.tstats["treat_post"]),
                         "p_value": float(res.pvalues["treat_post"]), "n": int(res.nobs),
                         "estimate": float(res.params["treat_post"]), "ci_lo": float(res.conf_int().loc["treat_post", "lower"]),
                         "ci_hi": float(res.conf_int().loc["treat_post", "upper"]),
                         "note": f"SE={float(res.std_errors['treat_post']):.4g}; R²(within)={float(res.rsquared_within):.3f}"})
        except Exception as exc:  # pragma: no cover
            log.warning("DiD %s lỗi: %s", y, exc)
        # đồ thị hệ số theo tuần
        sub = sub.copy()
        wk = sub["week"].clip(wk_lo, wk_hi)
        names = []
        for k in range(wk_lo, wk_hi + 1):
            if k == -1:
                continue
            nm = f"w_{k}".replace("-", "m")
            sub[nm] = ((wk == k) & (sub["FTSE"] == 1)).astype(float)
            names.append((k, nm))
        cols = [nm for _, nm in names if sub[nm].sum() > 0]
        try:
            res2 = PanelOLS(sub[y], sub[cols], entity_effects=True, time_effects=True, drop_absorbed=True,
                            check_rank=False).fit(cov_type="clustered", cluster_entity=True)
            ci = res2.conf_int()
            for k, nm in names:
                if nm in res2.params.index:
                    coefs.append({"outcome": label, "week": k, "coef": float(res2.params[nm]),
                                  "ci_lo": float(ci.loc[nm, "lower"]), "ci_hi": float(ci.loc[nm, "upper"]),
                                  "p_value": float(res2.pvalues[nm]), "variant": variant})
            coefs.append({"outcome": label, "week": -1, "coef": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "p_value": np.nan,
                          "variant": variant})
        except Exception as exc:  # pragma: no cover
            log.warning("Event-study plot %s lỗi: %s", y, exc)
    c = pd.DataFrame(coefs)
    if not c.empty:
        pre = c[(c["week"] < -1) & c["p_value"].notna()]
        for out, g in pre.groupby("outcome"):
            n_sig = int((g["p_value"] < 0.05).sum())
            rows.append({"hypothesis": "H3c", "metric": out, "event_id": get("events.did_event", "E3"),
                         "group": "FTSE−CONTROL", "window": "tuần trước sự kiện", "model": "Xu hướng song song",
                         "variant": variant, "test": "Số hệ số trước sự kiện có ý nghĩa 5%", "statistic": n_sig,
                         "p_value": np.nan, "n": len(g), "estimate": float(g["coef"].mean()),
                         "ci_lo": np.nan, "ci_hi": np.nan,
                         "note": "Đạt giả định song song nếu ≈ 0 hệ số có ý nghĩa"})
    return {"stats": pd.DataFrame(rows), "did_coefs": c}
