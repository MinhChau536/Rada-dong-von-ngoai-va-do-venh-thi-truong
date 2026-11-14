"""
Tối ưu hóa danh mục theo khẩu vị rủi ro – dùng chung cho trang Watchlist và bot Telegram.

Đầu vào: lợi suất ngày đã điều chỉnh quyền (indicator_stock_daily.ret) của các mã trong danh mục, cửa sổ `lookback`.
  • Hiệp phương sai co cụm Ledoit–Wolf (2004) về ma trận đường chéo trung bình – ổn định hơn ma trận mẫu khi số mã
    gần số phiên; lợi suất kỳ vọng = trung bình mẫu co 50% về trung bình chung (giảm sai số ước lượng μ).
  • Năm phương án (long-only, tổng tỷ trọng = 1, trần tỷ trọng mỗi mã theo khẩu vị):
      Đồng tỷ trọng · Phương sai nhỏ nhất · Cân bằng rủi ro (đóng góp rủi ro bằng nhau) · Sharpe lớn nhất ·
      Theo khẩu vị (lợi suất kỳ vọng lớn nhất với biến động ≤ mục tiêu của khẩu vị).
  • Kiểm chứng NGOÀI MẪU: tái cân bằng hằng tháng, mỗi lần chỉ dùng `lookback` phiên trước đó (không nhìn trước).
  • Gợi ý theo quy tắc: cặp tương quan cao, tập trung rủi ro / ngành, thanh khoản, room ngoại, beta so với khẩu vị,
    mã bổ sung có tương quan thấp để đa dạng hóa.
Kết quả là công cụ phân tích định lượng tham khảo – KHÔNG phải khuyến nghị đầu tư.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.common.config import get
from src.data import database as db

TRADING_DAYS = 250


@dataclass
class Profile:
    name: str
    target_vol: float      # biến động năm mục tiêu
    max_weight: float      # trần tỷ trọng một mã
    max_beta: float        # beta danh mục khuyến nghị tối đa
    note: str


def profiles() -> Dict[str, Profile]:
    cfg = get("portfolio.profiles", {}) or {}
    base = {
        "Thận trọng": Profile("Thận trọng", 0.15, 0.25, 0.9, "Ưu tiên giữ vốn, chấp nhận lợi suất thấp hơn; biến động năm ≤ 15%."),
        "Cân bằng": Profile("Cân bằng", 0.22, 0.30, 1.1, "Cân bằng tăng trưởng và rủi ro; biến động năm ≤ 22%."),
        "Tăng trưởng": Profile("Tăng trưởng", 0.30, 0.40, 1.4, "Chấp nhận biến động cao để tìm lợi suất; biến động năm ≤ 30%."),
    }
    for k, v in cfg.items():
        if k in base:
            for f in ("target_vol", "max_weight", "max_beta"):
                if f in v:
                    setattr(base[k], f, float(v[f]))
    return base


# ── dữ liệu ───────────────────────────────────────────────────────────────────
def load_returns(symbols: List[str], end=None, lookback: int = 250, path=None, min_obs: float = 0.8) -> pd.DataFrame:
    """Ma trận lợi suất ngày (phiên × mã) gồm `lookback` phiên kết thúc tại `end`. Mã thiếu > 20% phiên bị loại."""
    if not symbols:
        return pd.DataFrame()
    end = pd.Timestamp(end) if end is not None else None
    q = ("SELECT trade_date, symbol, ret FROM indicator_stock_daily WHERE symbol IN ({}) AND is_valid {}"
         .format(",".join("?" * len(symbols)), "AND trade_date <= ?" if end is not None else ""))
    df = db.query_df(q, [s.upper() for s in symbols] + ([end] if end is not None else []), path=path)
    if df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    r = df.pivot_table(index="trade_date", columns="symbol", values="ret").sort_index()
    r = r.tail(lookback)
    keep = [c for c in r.columns if r[c].notna().mean() >= min_obs]
    return r[keep].fillna(0.0)


def market_returns(end=None, lookback: int = 250, path=None) -> pd.Series:
    df = db.query_df("SELECT trade_date, r_vni_pct FROM indicator_daily ORDER BY trade_date", path=path)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    s = df.set_index("trade_date")["r_vni_pct"] / 100
    if end is not None:
        s = s[s.index <= pd.Timestamp(end)]
    return s.tail(lookback)


# ── ước lượng ─────────────────────────────────────────────────────────────────
def ledoit_wolf(x: np.ndarray) -> np.ndarray:
    """Ledoit–Wolf (2004): co ma trận hiệp phương sai mẫu về μ·I, hệ số co tối ưu ước lượng từ dữ liệu."""
    t, n = x.shape
    xc = x - x.mean(axis=0)
    s = xc.T @ xc / t
    mu = np.trace(s) / n
    f = mu * np.eye(n)
    d2 = np.sum((s - f) ** 2)
    b2 = sum(np.sum((np.outer(r, r) - s) ** 2) for r in xc) / t ** 2
    delta = min(b2, d2) / d2 if d2 > 0 else 1.0
    return delta * f + (1 - delta) * s


def estimate(r: pd.DataFrame, shrink_mu: float = 0.5) -> Dict:
    mu_d = r.mean().to_numpy()
    mu = (1 - shrink_mu) * mu_d + shrink_mu * mu_d.mean()
    cov = ledoit_wolf(r.to_numpy())
    return {"mu": mu * TRADING_DAYS, "cov": cov * TRADING_DAYS, "symbols": list(r.columns)}


# ── tối ưu ────────────────────────────────────────────────────────────────────
def _solve(obj, n: int, max_w: float, extra=()) -> np.ndarray:
    max_w = max(max_w, 1.0 / n + 1e-9)                       # trần phải ≥ 1/n để có nghiệm
    w0 = np.full(n, 1.0 / n)
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}, *extra]
    res = minimize(obj, w0, method="SLSQP", bounds=[(0.0, max_w)] * n, constraints=cons,
                   options={"maxiter": 500, "ftol": 1e-10})
    w = np.clip(res.x if res.success else w0, 0, None)
    return w / w.sum()


def vol(w, cov) -> float:
    return float(np.sqrt(max(w @ cov @ w, 0.0)))


def optimize(est: Dict, method: str, max_w: float = 1.0, target_vol: Optional[float] = None, rf: float = 0.0) -> np.ndarray:
    mu, cov = est["mu"], est["cov"]
    n = len(mu)
    if n == 1:
        return np.ones(1)
    if method == "equal":
        return np.full(n, 1.0 / n)
    if method == "min_var":
        return _solve(lambda w: w @ cov @ w, n, max_w)
    if method == "risk_parity":
        def rp(w):
            v = w @ cov @ w
            rc = w * (cov @ w) / max(v, 1e-12)
            return float(np.sum((rc - 1.0 / n) ** 2))
        return _solve(rp, n, max_w)
    if method == "max_sharpe":
        return _solve(lambda w: -(w @ mu - rf) / max(vol(w, cov), 1e-9), n, max_w)
    if method == "target":
        tv = target_vol or 0.2
        w_mv = optimize(est, "min_var", max_w)
        if vol(w_mv, cov) >= tv:                              # mục tiêu thấp hơn mức rủi ro nhỏ nhất có thể
            return w_mv
        return _solve(lambda w: -(w @ mu), n, max_w,
                      ({"type": "ineq", "fun": lambda w: tv ** 2 - w @ cov @ w},))
    raise ValueError(method)


METHODS = {"equal": "Đồng tỷ trọng", "min_var": "Phương sai nhỏ nhất", "risk_parity": "Cân bằng rủi ro",
           "max_sharpe": "Sharpe lớn nhất", "target": "Theo khẩu vị rủi ro"}


def metrics(w: np.ndarray, r: pd.DataFrame, est: Dict, m: Optional[pd.Series] = None, rf: float = 0.0) -> Dict:
    port = r.to_numpy() @ w
    ps = pd.Series(port, index=r.index)
    cum = (1 + ps).cumprod()
    dd = float((cum / cum.cummax() - 1).min())
    ann_ret, ann_vol = float(w @ est["mu"]), vol(w, est["cov"])
    rc = w * (est["cov"] @ w) / max(w @ est["cov"] @ w, 1e-12)
    sd_i = np.sqrt(np.diag(est["cov"]))
    beta = np.nan
    if m is not None:
        j = pd.concat([ps, m], axis=1).dropna()
        if len(j) > 30 and j.iloc[:, 1].var() > 0:
            beta = float(np.cov(j.iloc[:, 0], j.iloc[:, 1])[0, 1] / j.iloc[:, 1].var())
    var95 = float(np.quantile(port, 0.05))
    return {"ret": ann_ret, "vol": ann_vol, "sharpe": (ann_ret - rf) / ann_vol if ann_vol > 0 else np.nan,
            "mdd": dd, "var95": var95, "cvar95": float(port[port <= var95].mean()) if (port <= var95).any() else var95,
            "beta": beta, "risk_contrib": rc, "eff_n": float(1 / np.sum(w ** 2)),
            "div_ratio": float(w @ sd_i / ann_vol) if ann_vol > 0 else np.nan, "hist_ret": float(cum.iloc[-1] - 1)}


def frontier(est: Dict, max_w: float, n_pts: int = 25) -> pd.DataFrame:
    w_mv = optimize(est, "min_var", max_w)
    lo, hi = vol(w_mv, est["cov"]), float(np.sqrt(np.diag(est["cov"])).max())
    rows = []
    for tv in np.linspace(lo, hi, n_pts):
        w = optimize(est, "target", max_w, tv)
        rows.append({"vol": vol(w, est["cov"]), "ret": float(w @ est["mu"])})
    return pd.DataFrame(rows).drop_duplicates().sort_values("vol")


def walk_forward(symbols: List[str], method: str, max_w: float, target_vol: Optional[float], end=None,
                 lookback: int = 250, months: int = 24, rf: float = 0.0, path=None) -> pd.Series:
    """Lợi suất ngày ngoài mẫu: đầu mỗi tháng tối ưu bằng `lookback` phiên trước đó, giữ tỷ trọng tới tháng sau."""
    r_all = load_returns(symbols, end, lookback + months * 22 + 30, path=path, min_obs=0.0)
    if r_all.empty or len(r_all) < lookback + 40:
        return pd.Series(dtype=float)
    idx = r_all.index
    starts = [d for d in pd.Series(idx).groupby([idx.year, idx.month]).min() if idx.get_loc(d) >= lookback]
    out = []
    for i, d0 in enumerate(starts):
        p0 = idx.get_loc(d0)
        win = r_all.iloc[p0 - lookback:p0]
        cols = [c for c in win.columns if (win[c] != 0).mean() >= 0.6]
        if not cols:
            continue
        est = estimate(win[cols])
        w = optimize(est, method, max_w, target_vol, rf)
        p1 = idx.get_loc(starts[i + 1]) if i + 1 < len(starts) else len(idx)
        out.append(pd.Series(r_all.iloc[p0:p1][cols].to_numpy() @ w, index=idx[p0:p1]))
    return pd.concat(out) if out else pd.Series(dtype=float)


# ── gợi ý ────────────────────────────────────────────────────────────────────
def suggestions(r: pd.DataFrame, w: np.ndarray, m: Dict, prof: Profile, info: pd.DataFrame) -> List[str]:
    """Gợi ý theo quy tắc. info: symbol, sector, tv20 (VND/phiên), U (room đã dùng), close."""
    out = []
    syms = list(r.columns)
    corr = r.corr()
    pairs = [(a, b, corr.loc[a, b]) for i, a in enumerate(syms) for b in syms[i + 1:] if corr.loc[a, b] >= 0.6]
    for a, b, c in sorted(pairs, key=lambda x: -x[2])[:3]:
        out.append(f"🔗 {a} và {b} tương quan cao ({c:.2f}) – nắm cả hai gần như nhân đôi cùng một rủi ro; cân nhắc giữ một mã."
                   .replace(f"{c:.2f}", f"{c:.2f}".replace(".", ",")))
    rc = pd.Series(m["risk_contrib"], index=syms)
    top = rc.idxmax()
    if rc.max() > 0.35 and len(syms) > 2:
        out.append(f"⚖️ {top} chiếm {rc.max():.0%} tổng rủi ro danh mục – rủi ro đang dồn vào một mã.")
    if info is not None and not info.empty:
        sec = pd.Series(w, index=syms).groupby(info.set_index("symbol").reindex(syms)["sector"].fillna("Khác")).sum()
        if sec.max() > 0.5:
            out.append(f"🏭 Ngành {sec.idxmax()} chiếm {sec.max():.0%} tỷ trọng – rủi ro tập trung ngành.")
        ilq = info[(info["symbol"].isin(syms)) & (info["tv20"] < 10e9)]
        for s in ilq.itertuples():
            out.append(f"💧 {s.symbol} thanh khoản thấp (GTGD TB 20 phiên ≈ {s.tv20 / 1e9:.1f} tỷ) – khó mua/bán khối lượng lớn.")
        full = info[(info["symbol"].isin(syms)) & (info["U"] >= 0.95)]
        for s in full.itertuples():
            out.append(f"🌏 {s.symbol} đã dùng {s.U:.0%} room ngoại – khối ngoại khó mua thêm.")
    if not np.isnan(m["beta"]) and m["beta"] > prof.max_beta:
        out.append(f"📈 Beta danh mục {m['beta']:.2f} cao hơn mức phù hợp khẩu vị {prof.name} (≤ {prof.max_beta:.1f}) – "
                   "danh mục dao động mạnh hơn thị trường.")
    if m["vol"] > prof.target_vol * 1.05:
        out.append(f"🌡️ Biến động năm ước tính {m['vol']:.0%} vượt mục tiêu {prof.target_vol:.0%} của khẩu vị {prof.name} – "
                   "các mã hiện có không đủ để hạ rủi ro; nên bổ sung mã phòng thủ / tương quan thấp.")
    if m["eff_n"] < 3 and len(syms) >= 4:
        out.append(f"🎯 Số mã hiệu dụng chỉ {m['eff_n']:.1f} – danh mục thực chất tập trung vào vài mã.")
    if not out:
        out.append("✅ Không phát hiện điểm tập trung rủi ro đáng kể theo các quy tắc kiểm tra.")
    return out


def diversifiers(port_ret: pd.Series, exclude: List[str], end=None, lookback: int = 250, n: int = 5,
                 min_tv: float = 50e9, path=None) -> pd.DataFrame:
    """Mã HOSE thanh khoản tốt có tương quan thấp nhất với danh mục hiện tại (ứng viên đa dạng hóa)."""
    end = pd.Timestamp(end) if end is not None else None
    cond = "AND trade_date <= ?" if end is not None else ""
    liq = db.query_df(
        f"WITH last AS (SELECT DISTINCT trade_date FROM indicator_stock_daily WHERE 1=1 {cond} ORDER BY trade_date DESC LIMIT 20) "
        "SELECT s.symbol, ANY_VALUE(s.sector) AS sector, AVG(s.tv) AS tv20 FROM indicator_stock_daily s JOIN last USING (trade_date) "
        "WHERE s.is_valid GROUP BY 1 HAVING AVG(s.tv) >= ?", ([end] if end is not None else []) + [min_tv], path=path)
    cand = [s for s in liq["symbol"] if s not in set(exclude)]
    if not cand or port_ret.empty:
        return pd.DataFrame()
    rc = load_returns(cand, end, lookback, path=path)
    j = rc.join(port_ret.rename("_p"), how="inner")
    if len(j) < 60:
        return pd.DataFrame()
    corr = j.drop(columns="_p").corrwith(j["_p"])
    vol_a = j.drop(columns="_p").std() * np.sqrt(TRADING_DAYS)
    out = pd.DataFrame({"symbol": corr.index, "corr": corr.values, "vol": vol_a.reindex(corr.index).values})
    out = out.merge(liq, on="symbol", how="left").sort_values("corr").head(n)
    return out


def stock_info(symbols: List[str], end=None, path=None) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    end = pd.Timestamp(end) if end is not None else None
    cond = "AND trade_date <= ?" if end is not None else ""
    q = (f"WITH last AS (SELECT DISTINCT trade_date FROM indicator_stock_daily WHERE 1=1 {cond} ORDER BY trade_date DESC LIMIT 20) "
         "SELECT s.symbol, ANY_VALUE(s.sector) AS sector, AVG(s.tv) AS tv20, "
         "ARG_MAX(s.U, s.trade_date) AS U, ARG_MAX(s.close, s.trade_date) AS close FROM indicator_stock_daily s "
         "JOIN last USING (trade_date) WHERE s.symbol IN ({}) GROUP BY 1").format(",".join("?" * len(symbols)))
    return db.query_df(q, ([end] if end is not None else []) + [s.upper() for s in symbols], path=path)


def allocate_shares(w: pd.Series, prices: pd.Series, capital: float, lot: int = 100) -> pd.DataFrame:
    """Quy tỷ trọng ra số cổ phiếu theo lô 100 (làm tròn xuống) với số vốn cho trước."""
    rows = []
    for s, wi in w.items():
        p = float(prices.get(s, np.nan))
        if not p or np.isnan(p) or wi <= 0:
            continue
        qty = int(capital * wi / p // lot * lot)
        rows.append({"symbol": s, "weight": wi, "price": p, "shares": qty, "value": qty * p})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["cash_left"] = capital - df["value"].sum()
    return df


def analyze(symbols: List[str], profile: str = "Cân bằng", end=None, lookback: int | None = None,
            max_weight: float | None = None, target_vol: float | None = None, rf: float | None = None, path=None) -> Dict:
    """Gói phân tích đầy đủ cho một danh mục và khẩu vị."""
    prof = profiles()[profile]
    lookback = int(lookback or get("portfolio.lookback", 250))
    max_w = float(max_weight or prof.max_weight)
    tv = float(target_vol or prof.target_vol)
    rf = float(get("portfolio.risk_free", 0.045) if rf is None else rf)
    r = load_returns(symbols, end, lookback, path=path)
    if r.shape[1] < 2 or len(r) < 60:
        return {"ok": False, "reason": "Cần ít nhất 2 mã có ≥ 60 phiên dữ liệu trong cửa sổ đã chọn.",
                "dropped": [s for s in symbols if s not in r.columns]}
    est = estimate(r)
    mkt = market_returns(end, lookback, path)
    res = {}
    for k in METHODS:
        w = optimize(est, k, max_w, tv, rf)
        res[k] = {"w": pd.Series(w, index=est["symbols"]), **metrics(w, r, est, mkt, rf)}
    info = stock_info(est["symbols"], end, path)
    w_t = res["target"]["w"].to_numpy()
    port = pd.Series(r.to_numpy() @ w_t, index=r.index)
    return {"ok": True, "profile": prof, "max_w": max_w, "target_vol": tv, "rf": rf, "lookback": len(r),
            "returns": r, "est": est, "results": res, "corr": r.corr(), "info": info,
            "suggest": suggestions(r, w_t, res["target"], prof, info), "port_ret": port,
            "dropped": [s for s in symbols if s not in r.columns], "d0": r.index[0], "d1": r.index[-1]}
