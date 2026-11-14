"""
Kiểm định giả thuyết H1a, H1b, H2a, H2b, H2c và hiệu chỉnh Holm (bước B6.7–B6.12).

Ưu tiên kiểm định phi tham số / vững với phân phối (lợi suất đuôi dày, bị chặn biên độ).
Kết quả là MÔ TẢ – không diễn giải nhân quả (mục 9.2).
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportions_ztest
from statsmodels.tsa.stattools import adfuller

from src.common.config import control_group, ftse_universe, get

NARROW = {"narrow_up", "narrow_down"}


def _row(h, test, statistic, p, n, estimate=np.nan, lo=np.nan, hi=np.nan, group="Toàn sàn", metric="", window="",
         note="", event_id="", model="", variant="base") -> Dict:
    return {"hypothesis": h, "metric": metric, "event_id": event_id, "group": group, "window": window, "model": model,
            "variant": variant, "test": test, "statistic": statistic, "p_value": p, "n": n, "estimate": estimate,
            "ci_lo": lo, "ci_hi": hi, "note": note}


def block_permutation_diff(x: np.ndarray, split: int, block: int, reps: int, seed: int = 11) -> float:
    """Kiểm định hoán vị theo khối (tôn trọng tự tương quan): hiệu trung bình sau − trước."""
    x = np.asarray(x, dtype=float)
    obs = x[split:].mean() - x[:split].mean()
    blocks = [x[i:i + block] for i in range(0, len(x), block)]
    rng = np.random.default_rng(seed)
    cnt = 0
    for _ in range(reps):
        perm = np.concatenate([blocks[i] for i in rng.permutation(len(blocks))])
        d = perm[split:].mean() - perm[:split].mean()
        cnt += abs(d) >= abs(obs) - 1e-15
    return (cnt + 1) / (reps + 1)


def h1a(day: pd.DataFrame, pre_sessions: int | None = None) -> List[Dict]:
    """So sánh trước/sau mốc hiệu lực. Nhóm 'trước' giới hạn `events.h1a_pre_sessions` phiên liền trước mốc (mặc định
    250 ≈ 1 năm) để không trộn nhiều chu kỳ thị trường 2016–2025 vào phép so sánh; 0 = dùng toàn bộ lịch sử."""
    split_date = pd.Timestamp(get("events.regime_split_date", "2026-09-21"))
    pre_n = int(get("events.h1a_pre_sessions", 250) if pre_sessions is None else pre_sessions)
    d = day.sort_values("trade_date")
    if pre_n > 0:
        td = pd.to_datetime(d["trade_date"])
        pre_idx = d.index[td < split_date][-pre_n:]
        d = d.loc[pre_idx.union(d.index[td >= split_date])].sort_values("trade_date")
    narrow = d["session_type"].isin(NARROW).astype(int).to_numpy()
    post = (pd.to_datetime(d["trade_date"]) >= split_date).to_numpy()
    n1, n0 = int(post.sum()), int((~post).sum())
    out = []
    if n1 < 5 or n0 < 5:
        return [_row("H1a", "Kiểm định hai tỷ lệ", np.nan, np.nan, n0 + n1, note="Chưa đủ phiên sau mốc")]
    k1, k0 = narrow[post].sum(), narrow[~post].sum()
    z, p = proportions_ztest([k1, k0], [n1, n0])
    diff = k1 / n1 - k0 / n0
    se = np.sqrt(k1 / n1 * (1 - k1 / n1) / n1 + k0 / n0 * (1 - k0 / n0) / n0)
    out.append(_row("H1a", "Kiểm định hai tỷ lệ (sau − trước)", z, p, n0 + n1, diff, diff - 1.96 * se, diff + 1.96 * se,
                    metric="Tỷ lệ phiên thiếu lan tỏa", note=f"Trước {k0}/{n0} = {k0 / n0:.1%}; sau {k1}/{n1} = {k1 / n1:.1%}"))
    Dv = d["D"].to_numpy()
    mw = stats.mannwhitneyu(Dv[post], Dv[~post], alternative="two-sided")
    out.append(_row("H1a", "Mann–Whitney phân phối D", mw.statistic, mw.pvalue, n0 + n1,
                    float(np.median(Dv[post]) - np.median(Dv[~post])), metric="D (điểm %)",
                    note="Hiệu trung vị D sau − trước"))
    split = int((~post).sum())
    p_perm = block_permutation_diff(narrow, split, int(get("events.permutation_block", 5)),
                                    int(get("events.permutation_reps", 5000)))
    out.append(_row("H1a", "Hoán vị khối 5 phiên", diff, p_perm, n0 + n1, diff, metric="Tỷ lệ phiên thiếu lan tỏa",
                    note="Mô tả, không quy nhân quả"))
    return out


def h1b(day: pd.DataFrame) -> List[Dict]:
    thr = float(get("events.h1b_dI_min", 10))
    x = day.loc[day["dI"].abs() >= thr, "CR5"].dropna().to_numpy()
    if len(x) < 5:
        return [_row("H1b", "Wilcoxon một phía", np.nan, np.nan, len(x), note="Quá ít phiên biến động mạnh")]
    w = stats.wilcoxon(x - 0.5, alternative="greater")
    rng = np.random.default_rng(3)
    meds = np.median(rng.choice(x, size=(int(get("events.bootstrap_reps", 2000)), len(x))), axis=1)
    return [_row("H1b", "Wilcoxon một phía (CR5 > 0,5)", w.statistic, w.pvalue, len(x), float(np.median(x)),
                 float(np.quantile(meds, .025)), float(np.quantile(meds, .975)), metric="Trung vị CR5",
                 window=f"|ΔI| ≥ {thr:g} điểm")]


def _spearman_by_day(df: pd.DataFrame, a: str, b: str, min_n: int = 10) -> pd.Series:
    out = {}
    for dt, g in df.groupby("trade_date"):
        g = g[[a, b]].dropna()
        if len(g) >= min_n and g[a].nunique() > 1 and g[b].nunique() > 1:
            out[dt] = stats.spearmanr(g[a], g[b]).statistic
    return pd.Series(out).sort_index()


def nw_mean_test(rho: pd.Series, lags: int) -> Dict:
    y = rho.dropna().to_numpy()
    if len(y) < 10:
        return {"mean": np.nan, "t": np.nan, "p": np.nan, "n": len(y), "se": np.nan}
    res = sm.OLS(y, np.ones(len(y))).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return {"mean": float(res.params[0]), "t": float(res.tvalues[0]), "p": float(res.pvalues[0]), "n": len(y),
            "se": float(res.bse[0])}


def _subsets(stock: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    ftse = set(ftse_universe()["symbol"])
    cg = control_group()
    ctrl = set(cg["control_symbol"].dropna()) if not cg.empty else set()
    split = pd.Timestamp(get("events.regime_split_date", "2026-09-21"))
    v = stock[stock["is_valid"]]
    return {"Toàn mẫu": v, "Nhóm FTSE": v[v["symbol"].isin(ftse)], "Nhóm đối chứng": v[v["symbol"].isin(ctrl)],
            "Trước 21/9/2026": v[v["trade_date"] < split], "Sau 21/9/2026": v[v["trade_date"] >= split]}


def h2(stock: pd.DataFrame) -> List[Dict]:
    lags = int(get("events.nw_lags", 5))
    out = []
    s = stock.sort_values(["symbol", "trade_date"]).copy()
    s["nf_next"] = s.groupby("symbol")["nf"].shift(-1)
    s["ret_next"] = s.groupby("symbol")["ret"].shift(-1)
    for name, sub in _subsets(s).items():
        min_n = 8 if name in ("Nhóm FTSE", "Nhóm đối chứng") else 20
        for hyp, a, b, lbl in (("H2a", "nf", "ret", "ρ(nf_t, r_t)"), ("H2b", "nf", "nf_next", "ρ(nf_t, nf_t+1)"),
                               ("H2b", "nf", "ret_next", "ρ(nf_t, r_t+1)")):
            rho = _spearman_by_day(sub, a, b, min_n)
            r = nw_mean_test(rho, lags)
            out.append(_row(hyp, "Fama–MacBeth, t Newey–West 5 trễ", r["t"], r["p"], r["n"], r["mean"],
                            r["mean"] - 1.96 * r["se"], r["mean"] + 1.96 * r["se"], group=name, metric=lbl,
                            note="n = số phiên"))
    return out


def h2c(day: pd.DataFrame) -> List[Dict]:
    lags = int(get("events.nw_lags", 5))
    d = day[["D", "NF_top", "r_vni_pct"]].dropna().copy()
    out = []
    if len(d) < 30:
        return [_row("H2c", "OLS-HAC", np.nan, np.nan, len(d), note="Chưa đủ quan sát")]
    adf = {}
    for c in ("D", "NF_top"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            st_, p_, *_ = adfuller(d[c], autolag="AIC")
        adf[c] = p_
        out.append(_row("H2c", "ADF (tính dừng)", st_, p_, len(d), metric=c, note="p < 0,05: chuỗi dừng"))
    diff = any(p > 0.05 for p in adf.values())
    X = pd.DataFrame({"NF_top": d["NF_top"], "abs_rvni": d["r_vni_pct"].abs()})
    y = d["D"]
    if diff:
        X, y = X.diff().dropna(), y.diff().dropna()
    res = sm.OLS(y, sm.add_constant(X)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    ci = res.conf_int().loc["NF_top"]
    out.append(_row("H2c", "OLS D ~ NF_top + |r_VNI| (HAC 5 trễ)", float(res.tvalues["NF_top"]),
                    float(res.pvalues["NF_top"]), int(res.nobs), float(res.params["NF_top"]), float(ci[0]), float(ci[1]),
                    metric="b (NF_top)", note=f"R² = {res.rsquared:.3f}; {'sai phân' if diff else 'mức'}"))
    return out


# ── H4: cấu trúc thị trường theo giai đoạn nâng hạng ──────────────────────────
H4_METRICS = {                              # cột indicator_daily → (nhãn, phép biến đổi)
    "D": ("D – độ vênh (điểm %)", None),
    "CR5": ("CR5 – tập trung đóng góp", None),
    "IQR_pct": ("IQR lợi suất (%)", None),
    "abs_rvni": ("|r VN-Index| (%) – biến động", None),
    "ln_tv": ("ln giá trị khớp toàn sàn", None),
    "FPR_total": ("FPR – tỷ trọng GD khối ngoại", None),
    "nf_total_ratio": ("nf toàn sàn – cường độ ròng", None),
    "HHI": ("HHI – tập trung dòng vốn ngoại", None),
    "narrow": ("Tỷ lệ phiên thiếu lan tỏa", None),
}


def period_labels(td: pd.Series) -> pd.Series:
    """Gán giai đoạn: 0 = trước công bố E1, 1 = từ E1 đến trước ngày hiệu lực, 2 = từ ngày hiệu lực."""
    e1 = pd.Timestamp(get("periods.announce", "2025-10-08"))
    eff = pd.Timestamp(get("periods.effective", get("events.regime_split_date", "2026-09-21")))
    td = pd.to_datetime(td)
    return pd.Series(np.select([td < e1, td < eff], [0, 1], 2), index=td.index)


def h4_frame(day: pd.DataFrame, pre_sessions: int | None = None, pre_start: str | None = None) -> pd.DataFrame:
    """Chuỗi ngày dùng cho H4: nhóm cơ sở = `pre_sessions` phiên ngay trước E1 (0 → từ `pre_start`)."""
    d = day.copy()
    d["trade_date"] = pd.to_datetime(d["trade_date"])
    d = d.sort_values("trade_date")
    d["period"] = period_labels(d["trade_date"]).to_numpy()
    d["abs_rvni"] = d["r_vni_pct"].abs()
    d["ln_tv"] = np.log(d["tv_total"].where(d["tv_total"] > 0))
    d["narrow"] = d["session_type"].isin(NARROW).astype(float)
    pre_n = int(get("periods.pre_sessions", 250) if pre_sessions is None else pre_sessions)
    start = pd.Timestamp(pre_start or get("periods.pre_start", "2019-01-02"))
    pre = d[d["period"] == 0]
    pre = pre.tail(pre_n) if pre_n > 0 else pre[pre["trade_date"] >= start]
    return pd.concat([pre, d[d["period"] > 0]])


def h4(day: pd.DataFrame, pre_sessions: int | None = None, pre_start: str | None = None,
       variant: str = "base") -> List[Dict]:
    """y_t = a + b1·1[E1 ≤ t < hiệu lực] + b2·1[t ≥ hiệu lực] + e_t, sai số Newey–West.
    Mô tả thay đổi so với nhóm cơ sở trước công bố, KHÔNG quy nhân quả (trùng biến động vĩ mô).
    MDE 80% (α = 5%, hai phía) ≈ 2,8 × SE – thay đổi nhỏ hơn mức này mẫu hiện tại chưa phát hiện được."""
    lags = int(get("events.nw_lags", 5))
    d = h4_frame(day, pre_sessions, pre_start)
    n_pre, n_mid, n_post = (int((d["period"] == k).sum()) for k in (0, 1, 2))
    win = {1: "E1 → hiệu lực", 2: "Sau hiệu lực"}
    pre_n = int(get("periods.pre_sessions", 250) if pre_sessions is None else pre_sessions)
    base = (f"cơ sở {n_pre} phiên trước E1" if pre_n > 0
            else f"cơ sở từ {pre_start or get('periods.pre_start', '2019-01-02')} ({n_pre} phiên)")
    out = []
    for col, (label, _) in H4_METRICS.items():
        x = d[["period", col]].dropna()
        if x["period"].nunique() < 2 or (x["period"] == 0).sum() < 30:
            continue
        X = pd.DataFrame({"mid": (x["period"] == 1).astype(float), "post": (x["period"] == 2).astype(float)},
                         index=x.index)
        X = X.loc[:, X.sum() > 0]
        res = sm.OLS(x[col], sm.add_constant(X)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
        means = x.groupby("period")[col].mean()
        for k, name in ((1, "mid"), (2, "post")):
            if name not in res.params:
                continue
            se = float(res.bse[name])
            ci = res.conf_int().loc[name]
            n_k = int((x["period"] == k).sum())
            note = (f"TB cơ sở {means.get(0, np.nan):.4g} → {means.get(k, np.nan):.4g}; {base}, {n_k} phiên; "
                    f"MDE 80% ≈ {2.8 * se:.3g}")
            if n_k < 60:
                note += "; < 60 phiên – công suất thấp, kết quả sơ bộ"
            out.append(_row("H4", "OLS giả biến giai đoạn (HAC 5 trễ)", float(res.tvalues[name]),
                            float(res.pvalues[name]), int(res.nobs), float(res.params[name]), float(ci[0]),
                            float(ci[1]), metric=label, window=win[k], note=note, variant=variant))
        post = x.loc[x["period"] == 2, col]
        pre = x.loc[x["period"] == 0, col]
        if len(post) >= 10:
            u, p = stats.mannwhitneyu(post, pre, alternative="two-sided")
            out.append(_row("H4", "Mann–Whitney (sau hiệu lực vs cơ sở)", float(u), float(p), len(post) + len(pre),
                            float(post.median() - pre.median()), metric=label, window=win[2],
                            note="Ước lượng = chênh trung vị; bỏ qua tự tương quan – chỉ tham khảo", variant=variant))
    return out


def period_summary(day: pd.DataFrame) -> pd.DataFrame:
    """Bảng mô tả theo giai đoạn (trung bình, trung vị, số phiên) cho trang 8 / báo cáo."""
    d = h4_frame(day)
    names = {0: "Cơ sở trước E1", 1: "E1 → hiệu lực", 2: "Sau hiệu lực"}
    rows = []
    for col, (label, _) in H4_METRICS.items():
        for k, g in d.groupby("period")[col]:
            g = g.dropna()
            rows.append({"metric": label, "period": names[k], "n": len(g), "mean": g.mean(), "median": g.median(),
                         "d0": d.loc[g.index, "trade_date"].min(), "d1": d.loc[g.index, "trade_date"].max()})
    return pd.DataFrame(rows)


def holm(df: pd.DataFrame) -> pd.DataFrame:
    """Holm theo họ kiểm định cùng giả thuyết, cùng phép kiểm định, nhiều cửa sổ/mốc (B6.12)."""
    if df.empty:
        return df
    d = df.copy()
    d["p_holm"] = np.nan
    keys = ["hypothesis", "test", "group", "metric", "model", "variant"]
    for _, g in d.groupby(keys, dropna=False):
        ok = g["p_value"].notna()
        if ok.sum() == 0:
            continue
        d.loc[g.index[ok], "p_holm"] = multipletests(g.loc[ok, "p_value"].to_numpy(), method="holm")[1]
    return d


def run_all(day: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    rows = h1a(day) + h1b(day) + h2(stock) + h2c(day) + h4(day)
    return pd.DataFrame(rows)
