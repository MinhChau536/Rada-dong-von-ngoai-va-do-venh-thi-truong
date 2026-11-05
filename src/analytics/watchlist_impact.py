"""
Module D – Watchlist Impact (bước B7.1–B7.6).

  (12) ER^I = r_i − r_VNI ;  ER^M = r_i − median_j(r_j)
  (13) r_i,t = a + Σ_{k=−1..1} b_k r_VNI,t+k + u ;  β^D = Σ b̂_k   (Dimson 1979, 120 phiên)
  β^ID: lợi suất 5 phút so với VN30 trong 20 phiên, bỏ nến ATO (09:15) và ATC (14:45).
  Phản ứng theo loại phiên: trung bình/trung vị lợi suất; Kruskal–Wallis + Dunn (Holm) khi mỗi loại ≥ 15 phiên.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from src.common.config import get
from src.data import database as db
from src.finance.breadth import SESSION_TYPES


# ── B7.1 quản lý watchlist ────────────────────────────────────────────────────
def get_watchlist(path: Optional[Path] = None) -> List[str]:
    df = db.query_df("SELECT symbol FROM watchlist ORDER BY added_at", path=path)
    if df.empty:
        return list(get("watchlist_default", ["FPT", "HPG", "MBB", "VNM", "SSI"]))
    return df["symbol"].tolist()


def ensure_default(path: Optional[Path] = None) -> None:
    db.init_schema(path)
    df = db.query_df("SELECT COUNT(*) AS n FROM watchlist", path=path)
    if df.empty or int(df["n"].iloc[0]) == 0:
        for s in get("watchlist_default", []):
            add(s, "Mặc định", path)


def add(symbol: str, note: str = "", path: Optional[Path] = None) -> None:
    s = symbol.strip().upper()
    if not s:
        return
    db.upsert("watchlist", pd.DataFrame([{"symbol": s, "added_at": datetime.now(), "note": note}]), path)


def remove(symbol: str, path: Optional[Path] = None) -> None:
    db.execute("DELETE FROM watchlist WHERE symbol = ?", [symbol.strip().upper()], path)


# ── chỉ số ────────────────────────────────────────────────────────────────────
def beta_ols(r: pd.Series, m: pd.Series) -> float:
    d = pd.concat([r, m], axis=1).dropna()
    if len(d) < 30:
        return np.nan
    x, y = d.iloc[:, 1].to_numpy(), d.iloc[:, 0].to_numpy()
    return float(np.polyfit(x, y, 1)[0])


def beta_dimson(r: pd.Series, m: pd.Series, window: int = 120, min_obs: int = 100) -> float:
    d = pd.DataFrame({"r": r, "m0": m, "mlag": m.shift(1), "mlead": m.shift(-1)}).dropna().tail(window)
    if len(d) < min(min_obs, window):
        return np.nan
    X = np.column_stack([np.ones(len(d)), d["mlag"], d["m0"], d["mlead"]])
    coef, *_ = np.linalg.lstsq(X, d["r"].to_numpy(), rcond=None)
    return float(coef[1:].sum())


def beta_intraday(intra: pd.DataFrame, sym: str, bench: str = "VN30") -> float:
    if intra is None or intra.empty or sym not in set(intra["symbol"]):
        return np.nan
    d = intra[intra["symbol"].isin([sym, bench])].copy()
    d["t"] = pd.to_datetime(d["ts"]).dt.strftime("%H:%M")
    d = d[~d["t"].isin(["09:15", "14:45"])]                  # bỏ ATO, ATC
    d["session"] = pd.to_datetime(d["ts"]).dt.date
    piv = d.pivot_table(index="ts", columns="symbol", values="close").sort_index()
    if sym not in piv or bench not in piv:
        return np.nan
    sess = pd.Series(pd.to_datetime(piv.index).date, index=piv.index)
    rets = piv.groupby(sess.values).pct_change().dropna()     # không nối qua đêm
    if len(rets) < 50:
        return np.nan
    return float(np.polyfit(rets[bench], rets[sym], 1)[0])


def dunn(groups: Dict[str, np.ndarray]) -> List[Dict]:
    allv = np.concatenate(list(groups.values()))
    ranks = stats.rankdata(allv)
    N = len(allv)
    pos, mean_rank, ns = 0, {}, {}
    for k, v in groups.items():
        mean_rank[k] = ranks[pos:pos + len(v)].mean()
        ns[k] = len(v)
        pos += len(v)
    keys = list(groups)
    pairs, ps = [], []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            z = (mean_rank[a] - mean_rank[b]) / np.sqrt(N * (N + 1) / 12 * (1 / ns[a] + 1 / ns[b]))
            pairs.append((a, b, z))
            ps.append(2 * stats.norm.sf(abs(z)))
    adj = multipletests(ps, method="holm")[1] if ps else []
    return [{"a": a, "b": b, "z": z, "p": p, "p_holm": q} for (a, b, z), p, q in zip(pairs, ps, adj)]


def compute(stock: pd.DataFrame, day: pd.DataFrame, intra: Optional[pd.DataFrame], symbols: List[str],
            as_of=None) -> Dict[str, pd.DataFrame]:
    s = stock.copy()
    s["trade_date"] = pd.to_datetime(s["trade_date"])
    d = day.set_index(pd.to_datetime(day["trade_date"])).sort_index()
    rm = d["r_vni_pct"] / 100
    last = pd.Timestamp(as_of) if as_of is not None else d.index.max()
    w_er = int(get("windows.er_sd_window", 60))
    bw = int(get("windows.beta_window", 120))
    min_obs = int(get("windows.beta_min_obs", 100))
    min_type = int(get("events.min_obs_per_type", 15))
    today_type = d.loc[last, "session_type"] if last in d.index else None
    prof, react, srows = [], [], []
    for sym in symbols:
        g = s[s["symbol"] == sym].set_index("trade_date").sort_index()
        g = g[g.index <= last]
        if g.empty:
            prof.append({"symbol": sym, "trade_date": last, "has_data": False})
            continue
        row = g.iloc[-1]
        has_today = g.index[-1] == last
        r = g["ret"].where(g["is_valid"])
        er_m_hist = g["ER_M"].where(g["is_valid"])
        sd60 = float(er_m_hist.iloc[:-1].tail(w_er).std()) if len(er_m_hist) > 10 else np.nan
        dayC = s[s["trade_date"] == last][["symbol", "C"]].dropna()
        dayC["rk_pos"] = dayC["C"].rank(ascending=False)
        dayC["rk_neg"] = dayC["C"].rank(ascending=True)
        rk = None
        if sym in set(dayC["symbol"]):
            x = dayC[dayC["symbol"] == sym].iloc[0]
            rk = int(x["rk_pos"]) if x["C"] > 0 else int(x["rk_neg"])
        m_al = rm.reindex(r.index)
        t_r = d["session_type"].reindex(r.index)
        by_type = {}
        for code in SESSION_TYPES:
            v = r[t_r == code].dropna()
            by_type[code] = v.to_numpy()
            react.append({"symbol": sym, "session_type": code, "label": SESSION_TYPES[code], "n": len(v),
                          "mean_ret_pct": float(v.mean() * 100) if len(v) else np.nan,
                          "median_ret_pct": float(v.median() * 100) if len(v) else np.nan})
        enough = {k: v for k, v in by_type.items() if len(v) >= min_type}
        kw_p = np.nan
        if len(enough) >= 2:
            kw = stats.kruskal(*enough.values())
            kw_p = float(kw.pvalue)
            srows.append({"hypothesis": "RQ4", "metric": "Lợi suất theo loại phiên", "event_id": "", "group": sym,
                          "window": "toàn mẫu", "model": "", "variant": "base", "test": "Kruskal–Wallis",
                          "statistic": float(kw.statistic), "p_value": kw_p, "n": int(sum(len(v) for v in enough.values())),
                          "estimate": np.nan, "ci_lo": np.nan, "ci_hi": np.nan,
                          "note": f"{len(enough)} loại phiên đủ ≥ {min_type} quan sát"})
            for pr in dunn(enough):
                srows.append({"hypothesis": "RQ4", "metric": f"{SESSION_TYPES[pr['a']]} vs {SESSION_TYPES[pr['b']]}",
                              "event_id": "", "group": sym, "window": "toàn mẫu", "model": "", "variant": "base",
                              "test": "Dunn (Holm)", "statistic": pr["z"], "p_value": pr["p"], "n": np.nan,
                              "estimate": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "note": f"p_holm={pr['p_holm']:.3g}"})
        tt = by_type.get(today_type, np.array([])) if today_type else np.array([])
        prof.append({
            "symbol": sym, "trade_date": last, "has_data": bool(has_today), "sector": row.get("sector"),
            "close": row["close"], "ret": float(row["ret"]) if has_today else None,
            "ER_I": float(row["ER_I"]) if has_today else None, "ER_M": float(row["ER_M"]) if has_today else None,
            "sd60_ER_M": sd60, "C": float(row["C"]) if has_today and pd.notna(row["C"]) else None,
            "leader_rank": rk, "net_flow": float(row["net_flow"]) if has_today else None, "nf": float(row["nf"]) if has_today else None,
            "z_nf": row["z_nf"], "pct60_nf": row["pct60_nf"], "streak": int(row["streak"]),
            "absorb_state": row["absorb_state"], "U": row["U"], "room_changed": bool(row["room_changed"]),
            "beta_ols": beta_ols(r.tail(bw), m_al.tail(bw)),
            "beta_dimson": beta_dimson(r, m_al, bw, min_obs),
            "beta_intraday": beta_intraday(intra, sym),
            "today_type": today_type, "today_type_mean_pct": float(tt.mean() * 100) if len(tt) else np.nan,
            "today_type_n": len(tt), "kw_p": kw_p, "ret_20d": row.get("ret_20d"),
        })
    from src.analytics.narrative import stock_line
    pdf = pd.DataFrame(prof)
    pdf["sentence"] = [stock_line(p) if p.get("has_data") else f"{p['symbol']}: chưa có dữ liệu phiên." for p in prof]
    return {"profile": pdf, "reaction": pd.DataFrame(react), "stats": pd.DataFrame(srows)}
