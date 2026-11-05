"""
Module C – Nghiên cứu sự kiện FTSE (bước B6.1–B6.5).

B6.1 Nhóm đối chứng: mỗi mã FTSE ghép 1 mã HOSE ngoài rổ gần nhất theo (phân vị vốn hóa, phân vị thanh
     khoản bình quân 120 phiên trước E1) – láng giềng gần nhất, khoảng cách Euclid, KHÔNG hoàn lại.
     Phương án 2: ghép chỉ theo thanh khoản.
B6.2 Mô hình thị trường r_i = α + β r_m trên cửa sổ ước lượng [−130; −11]; mã có w ≥ 3% dùng
     VN-Index loại trừ chính mã: r_m,−i = (ΔI − C_i) / (I_{t−1}(1 − w_i)).
B6.3 (9)  AR = r − (α̂ + β̂ r_m);  CAR(τ1,τ2) = Σ AR;  CAAR = mean CAR. Độ vững: mô hình điều chỉnh thị trường.
B6.4 Kiểm định t cắt ngang; BMP (Boehmer–Musumeci–Poulsen 1991) có hiệu chỉnh sai số dự báo; dấu tổng quát
     (Cowan 1992); bootstrap 2000 lần; FTSE vs đối chứng: Welch t, Mann–Whitney.
B6.5 (10) AFF = nf − mean(nf_est);  AVol = ln TV − mean(ln TV_est); cộng dồn như CAR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from src.common.config import CONFIG_DIR, events, ftse_universe, get
from src.common.logging import get_logger

log = get_logger(__name__)


# ── B6.1 ghép nhóm đối chứng ──────────────────────────────────────────────────
def match_control(s: pd.DataFrame, write: bool = True) -> Optional[pd.DataFrame]:
    fu = ftse_universe()
    ev = events()
    if fu.empty or ev.empty:
        return None
    e1 = ev.loc[ev["event_id"] == "E1", "event_date"].iloc[0]
    lookback = int(get("events.control_lookback", 120))
    dates = np.sort(s["trade_date"].unique())
    pre = dates[dates < np.datetime64(e1)][-lookback:]
    if len(pre) < 20:
        pre = dates[:lookback]
    w = s[s["trade_date"].isin(pre) & s["is_valid"]].copy()
    w["cap"] = w["listed_share"] * w["close"]
    feat = w.groupby("symbol").agg(cap=("cap", "mean"), liq=("tv", "mean"), n=("tv", "size"))
    feat = feat[feat["n"] >= 0.6 * len(pre)].dropna()
    feat["cap_pct"] = feat["cap"].rank(pct=True)
    feat["liq_pct"] = feat["liq"].rank(pct=True)
    treated = [x for x in fu["symbol"] if x in feat.index]
    pool = feat.drop(index=[x for x in fu["symbol"] if x in feat.index])
    order = feat.loc[treated].sort_values("cap", ascending=False).index.tolist()

    def greedy(cols: List[str]) -> Dict[str, Tuple[str, float]]:
        avail = pool.copy()
        res = {}
        for t in order:
            if avail.empty:
                break
            dist = np.sqrt(((avail[cols] - feat.loc[t, cols]) ** 2).sum(axis=1))
            best = dist.idxmin()
            res[t] = (best, float(dist.loc[best]))
            avail = avail.drop(index=best)
        return res

    m1 = greedy(["cap_pct", "liq_pct"])
    m2 = greedy(["liq_pct"])
    rows = []
    for t in order:
        c1, d1 = m1.get(t, (None, np.nan))
        c2, d2 = m2.get(t, (None, np.nan))
        rows.append({"ftse_symbol": t, "control_symbol": c1, "distance": round(d1, 4),
                     "control_symbol_liq": c2, "distance_liq": round(d2, 4),
                     "cap_pct_ftse": round(feat.loc[t, "cap_pct"], 4),
                     "cap_pct_control": round(feat.loc[c1, "cap_pct"], 4) if c1 else None,
                     "liq_pct_ftse": round(feat.loc[t, "liq_pct"], 4),
                     "liq_pct_control": round(feat.loc[c1, "liq_pct"], 4) if c1 else None})
    out = pd.DataFrame(rows)
    if write:
        out.to_csv(CONFIG_DIR / "control_group.csv", index=False, encoding="utf-8")
    return out


def control_balance(ctrl: pd.DataFrame) -> pd.DataFrame:
    """Bảng so sánh đặc điểm hai nhóm (trung vị phân vị vốn hóa, thanh khoản) + Mann–Whitney."""
    rows = []
    for var in ("cap_pct", "liq_pct"):
        a, b = ctrl[f"{var}_ftse"].astype(float), ctrl[f"{var}_control"].astype(float)
        p = stats.mannwhitneyu(a, b).pvalue if len(a) > 2 else np.nan
        rows.append({"variable": var, "median_ftse": a.median(), "median_control": b.median(), "mw_p": p})
    return pd.DataFrame(rows)


# ── tiện ích lịch ─────────────────────────────────────────────────────────────
def event_position(dates: np.ndarray, event_date) -> int:
    idx = np.searchsorted(dates, np.datetime64(pd.Timestamp(event_date)))
    return int(idx)


def _panel(stock: pd.DataFrame, col: str) -> pd.DataFrame:
    return stock.pivot(index="trade_date", columns="symbol", values=col).astype(float)


class EventStudy:
    def __init__(self, stock: pd.DataFrame, day: pd.DataFrame, est_window=None, model: str = "market",
                 exclude_ceiling_floor: bool = False):
        self.dates = np.sort(pd.to_datetime(stock["trade_date"].unique()))
        st = stock.copy()
        if exclude_ceiling_floor:
            st.loc[st["is_ceiling"] | st["is_floor"], "ret"] = np.nan
        st.loc[~st["is_valid"], "ret"] = np.nan
        self.R = _panel(st, "ret").reindex(self.dates)
        self.NF = _panel(st, "nf").reindex(self.dates)
        tv = st.assign(ltv=np.log(st["tv"].where(st["tv"] > 0)))
        self.LTV = _panel(tv, "ltv").reindex(self.dates)
        self.W = _panel(st, "w").reindex(self.dates)
        self.C = _panel(st, "C").reindex(self.dates)
        d = day.set_index(pd.to_datetime(day["trade_date"])).reindex(self.dates)
        self.rm = (d["vni"] / d["prev_value"] - 1)
        self.dI, self.prev = d["dI"], d["prev_value"]
        self.est = est_window or get("events.estimation_window", [-130, -11])
        self.win = get("events.event_window", [-10, 20])
        self.model = model
        self.big_w = float(get("events.large_weight_threshold", 0.03))
        self.min_obs = int(get("events.min_est_obs", 100))

    def market_for(self, sym: str) -> pd.Series:
        w = self.W.get(sym)
        if w is not None and float(w.mean(skipna=True) or 0) >= self.big_w:
            c = self.C[sym].fillna(0)
            return (self.dI - c) / (self.prev * (1 - w.fillna(0)))
        return self.rm

    def run_symbol(self, sym: str, pos: int) -> Optional[Dict]:
        if sym not in self.R.columns:
            return None
        n = len(self.dates)
        e0, e1 = pos + self.est[0], pos + self.est[1]
        w0, w1 = pos + self.win[0], min(pos + self.win[1], n - 1)
        if w0 < 0 or pos >= n:
            return None
        e0c = max(0, e0)
        r = self.R[sym]
        m = self.market_for(sym)
        er, em = r.iloc[e0c:e1 + 1], m.iloc[e0c:e1 + 1]
        ok = er.notna() & em.notna()
        min_obs = min(self.min_obs, max(30, (e1 - e0c + 1) - 10))
        if ok.sum() < min_obs:
            return None
        x, y = em[ok].to_numpy(), er[ok].to_numpy()
        if self.model == "market_adj":
            a, b = 0.0, 1.0
        else:
            b, a = np.polyfit(x, y, 1)
        resid = y - (a + b * x)
        T = len(y)
        sigma = float(np.sqrt((resid ** 2).sum() / max(T - 2, 1)))
        xm, sxx = x.mean(), ((x - x.mean()) ** 2).sum()
        taus = np.arange(w0 - pos, w1 - pos + 1)
        rw, mw = r.iloc[w0:w1 + 1].to_numpy(), m.iloc[w0:w1 + 1].to_numpy()
        ar = rw - (a + b * mw)
        corr = np.sqrt(1 + 1 / T + ((mw - xm) ** 2) / sxx) if sxx > 0 else np.ones_like(mw)
        sar = ar / (sigma * corr)
        p_pos = float((resid > 0).mean())
        nf, lt = self.NF[sym], self.LTV[sym]
        nf_e, lt_e = nf.iloc[e0c:e1 + 1], lt.iloc[e0c:e1 + 1]
        aff = nf.iloc[w0:w1 + 1].to_numpy() - nf_e.mean()
        avol = lt.iloc[w0:w1 + 1].to_numpy() - lt_e.mean()
        saff = aff / (nf_e.std() if nf_e.std() > 0 else np.nan)
        return {"symbol": sym, "alpha": a, "beta": b, "sigma": sigma, "n_est": T, "p_pos": p_pos,
                "taus": taus, "ar": ar, "sar": sar, "aff": aff, "saff": saff, "avol": avol,
                "market": "VNI_ex" if m is not self.rm else "VNI"}

    def run_group(self, symbols: List[str], event_date) -> List[Dict]:
        pos = event_position(self.dates, event_date)
        out = []
        for sym in symbols:
            res = self.run_symbol(sym, pos)
            if res is not None:
                out.append(res)
        return out


def _window_sum(res: Dict, key: str, w: Tuple[int, int]) -> float:
    m = (res["taus"] >= w[0]) & (res["taus"] <= w[1])
    v = res[key][m]
    if len(v) == 0 or np.all(np.isnan(v)):
        return np.nan
    return float(np.nansum(v))


def bootstrap_ci(x: np.ndarray, reps: int, seed: int = 7, alpha: float = 0.05) -> Tuple[float, float]:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 3:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(reps, len(x)), replace=True).mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def car_tests(cars: np.ndarray, scars: np.ndarray, p_pos: np.ndarray, reps: int) -> List[Dict]:
    """t cắt ngang, BMP, dấu tổng quát, bootstrap."""
    out = []
    c = cars[~np.isnan(cars)]
    n = len(c)
    if n >= 3:
        t, p = stats.ttest_1samp(c, 0.0)
        lo, hi = bootstrap_ci(c, reps)
        out.append({"test": "t cắt ngang", "statistic": t, "p_value": p, "n": n, "estimate": c.mean(),
                    "ci_lo": lo, "ci_hi": hi})
        sc = scars[~np.isnan(scars)]
        if len(sc) >= 3 and sc.std(ddof=1) > 0:
            tb = sc.mean() * np.sqrt(len(sc)) / sc.std(ddof=1)
            out.append({"test": "BMP", "statistic": tb, "p_value": 2 * stats.t.sf(abs(tb), len(sc) - 1),
                        "n": len(sc), "estimate": c.mean(), "ci_lo": lo, "ci_hi": hi})
        pp = np.nanmean(p_pos) if len(p_pos) else 0.5
        wpos = int((c > 0).sum())
        if 0 < pp < 1:
            z = (wpos - n * pp) / np.sqrt(n * pp * (1 - pp))
            out.append({"test": "Dấu tổng quát", "statistic": z, "p_value": 2 * stats.norm.sf(abs(z)), "n": n,
                        "estimate": wpos / n, "ci_lo": np.nan, "ci_hi": np.nan})
    return out


def run_all(stock: pd.DataFrame, day: pd.DataFrame, variant: str = "base", est_window=None, model: str = "market",
            control_col: str = "control_symbol", exclude_family: Optional[str] = None,
            exclude_ceiling_floor: bool = False) -> Dict[str, pd.DataFrame]:
    """Chạy E1–E3 cho FTSE và đối chứng; trả về event_params, event_results, event_aar, stats rows."""
    ev = events()
    fu = ftse_universe()
    from src.common.config import control_group
    cg = control_group()
    ftse = fu["symbol"].tolist()
    ctrl = cg[control_col].dropna().tolist() if not cg.empty and control_col in cg else []
    if exclude_family:
        fam = stock.drop_duplicates("symbol").set_index("symbol")["family"]
        ftse = [x for x in ftse if fam.get(x) != exclude_family]
        ctrl = [x for x in ctrl if fam.get(x) != exclude_family]
    es = EventStudy(stock, day, est_window, model, exclude_ceiling_floor)
    reps = int(get("events.bootstrap_reps", 2000))
    windows = [tuple(w) for w in get("events.car_windows", [[-1, 1], [-5, 5], [-10, 10], [0, 20]])]
    params, results, aar, srows = [], [], [], []
    for e in ev.itertuples():
        grp_res = {"FTSE": es.run_group(ftse, e.event_date), "CONTROL": es.run_group(ctrl, e.event_date)}
        cars_by = {}
        for gname, lst in grp_res.items():
            for r in lst:
                params.append({"event_id": e.event_id, "group": gname, "symbol": r["symbol"], "alpha": r["alpha"],
                               "beta": r["beta"], "sigma": r["sigma"], "n_est": r["n_est"], "market": r["market"],
                               "variant": variant})
            for w in windows:
                L = w[1] - w[0] + 1
                for r in lst:
                    results.append({"event_id": e.event_id, "group": gname, "symbol": r["symbol"],
                                    "window": f"[{w[0]};{w[1]}]", "CAR": _window_sum(r, "ar", w),
                                    "SCAR": _window_sum(r, "sar", w) / np.sqrt(L),
                                    "CAFF": _window_sum(r, "aff", w),
                                    "SCAFF": _window_sum(r, "saff", w) / np.sqrt(L),
                                    "CAVol": _window_sum(r, "avol", w), "variant": variant})
            if lst:
                taus = lst[0]["taus"]
                AR = np.vstack([np.pad(r["ar"], (0, len(taus) - len(r["ar"])), constant_values=np.nan) for r in lst])
                AF = np.vstack([np.pad(r["aff"], (0, len(taus) - len(r["aff"])), constant_values=np.nan) for r in lst])
                AV = np.vstack([np.pad(r["avol"], (0, len(taus) - len(r["avol"])), constant_values=np.nan) for r in lst])
                car_path = np.nancumsum(AR, axis=1)
                caff_path = np.nancumsum(AF, axis=1)
                for k, tau in enumerate(taus):
                    n_ok = int(np.sum(~np.isnan(AR[:, k])))
                    if n_ok == 0:
                        continue
                    se = np.nanstd(car_path[:, k], ddof=1) / np.sqrt(n_ok) if n_ok > 1 else np.nan
                    sef = np.nanstd(caff_path[:, k], ddof=1) / np.sqrt(n_ok) if n_ok > 1 else np.nan
                    aar.append({"event_id": e.event_id, "group": gname, "tau": int(tau),
                                "AAR": np.nanmean(AR[:, k]), "CAAR": np.nanmean(car_path[:, k]),
                                "CAAR_lo": np.nanmean(car_path[:, k]) - 1.96 * se,
                                "CAAR_hi": np.nanmean(car_path[:, k]) + 1.96 * se,
                                "AAFF": np.nanmean(AF[:, k]), "CAFF": np.nanmean(caff_path[:, k]),
                                "CAFF_lo": np.nanmean(caff_path[:, k]) - 1.96 * sef,
                                "CAFF_hi": np.nanmean(caff_path[:, k]) + 1.96 * sef,
                                "AAVol": np.nanmean(AV[:, k]), "n": n_ok, "variant": variant})
        res_df = pd.DataFrame([x for x in results if x["event_id"] == e.event_id and x["variant"] == variant])
        for w in windows:
            wl = f"[{w[0]};{w[1]}]"
            for gname, lst in grp_res.items():
                sub = res_df[(res_df["group"] == gname) & (res_df["window"] == wl)] if not res_df.empty else pd.DataFrame()
                if sub.empty:
                    continue
                pp = np.array([r["p_pos"] for r in lst])
                for t in car_tests(sub["CAR"].to_numpy(), sub["SCAR"].to_numpy(), pp, reps):
                    srows.append({"hypothesis": "H3a", "metric": "CAR", "event_id": e.event_id, "group": gname,
                                  "window": wl, "model": model, "variant": variant, **t})
                for metric, std_col, hyp in (("CAFF", "SCAFF", "H3b"), ("CAVol", None, "H3b")):
                    x = sub[metric].to_numpy()
                    sx = sub[std_col].to_numpy() if std_col else x
                    for t in car_tests(x, sx, np.full(len(x), 0.5), reps):
                        if metric == "CAVol" and t["test"] == "BMP":
                            continue
                        srows.append({"hypothesis": hyp, "metric": metric, "event_id": e.event_id, "group": gname,
                                      "window": wl, "model": model, "variant": variant, **t})
            # FTSE vs đối chứng
            a = res_df[(res_df["group"] == "FTSE") & (res_df["window"] == wl)] if not res_df.empty else pd.DataFrame()
            b = res_df[(res_df["group"] == "CONTROL") & (res_df["window"] == wl)] if not res_df.empty else pd.DataFrame()
            if len(a) >= 3 and len(b) >= 3:
                for metric, hyp in (("CAR", "H3a"), ("CAFF", "H3b"), ("CAVol", "H3b")):
                    xa, xb = a[metric].dropna(), b[metric].dropna()
                    if len(xa) < 3 or len(xb) < 3:
                        continue
                    tw = stats.ttest_ind(xa, xb, equal_var=False)
                    mw = stats.mannwhitneyu(xa, xb, alternative="two-sided")
                    for name, st_, p_ in (("Welch t (FTSE − đối chứng)", tw.statistic, tw.pvalue),
                                          ("Mann–Whitney (FTSE vs đối chứng)", mw.statistic, mw.pvalue)):
                        srows.append({"hypothesis": hyp, "metric": metric, "event_id": e.event_id, "group": "FTSE−CONTROL",
                                      "window": wl, "model": model, "variant": variant, "test": name,
                                      "statistic": st_, "p_value": p_, "n": len(xa) + len(xb),
                                      "estimate": xa.mean() - xb.mean(), "ci_lo": np.nan, "ci_hi": np.nan})
    return {"event_params": pd.DataFrame(params), "event_results": pd.DataFrame(results),
            "event_aar": pd.DataFrame(aar), "stats": pd.DataFrame(srows)}
