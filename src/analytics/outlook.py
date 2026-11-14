"""
Tóm tắt diễn biến và triển vọng thống kê của thị trường (dùng cho báo cáo PDF).

Phần "dự báo" CHỈ gồm các ước lượng xác suất có kiểm chứng lịch sử, không phải khuyến nghị:
  (a) Biên dao động kỳ vọng của VN-Index trong h phiên tới theo độ biến động EWMA (RiskMetrics, λ = 0,94):
      σ_t² = λ·σ_{t−1}² + (1 − λ)·r_t²,  biên = I_t · exp(± z · σ_t · √h). Kèm tỷ lệ bao phủ thực tế của biên 90%
      trên lịch sử (đánh giá ngoài mẫu: σ_t chỉ dùng dữ liệu đến t, so với lợi suất t+1…t+h).
  (b) Xác suất có điều kiện theo "trạng thái tương tự": các phiên lịch sử cùng xu hướng (trên/dưới MA50), cùng dấu
      động lượng 20 phiên và cùng dấu khối ngoại ròng lũy kế 20 phiên; tần suất VN-Index tăng sau h phiên.
      Chỉ dùng các phiên mà cửa sổ t+1…t+h đã kết thúc trước ngày báo cáo (không nhìn trước).
  (c) Tín hiệu cảnh báo kích hoạt hôm nay và thành tích lịch sử của chính tín hiệu đó (bảng alert_predictive).
Các ước lượng mang tính MÔ TẢ – cửa sổ chồng lấp, phân phối thay đổi theo thời gian, mẫu theo trạng thái nhỏ.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.common import fmt
from src.common.config import get

Z68, Z90 = 1.0, 1.645


def _log_ret(close: pd.Series) -> pd.Series:
    c = close.astype(float)
    return np.log(c / c.shift(1))


def ewma_sigma(r: pd.Series, lam: float = 0.94, warmup: int = 30) -> pd.Series:
    """σ_t theo EWMA của r² (r là log-return ngày), chỉ dùng dữ liệu đến t."""
    v = (r ** 2).ewm(alpha=1 - lam, adjust=False, min_periods=warmup).mean()
    return np.sqrt(v)


def vol_range(close: pd.Series, horizons=(5, 20), lam: float | None = None,
              start: str | None = None) -> Dict[int, Dict]:
    """Biên 68%/90% cho h phiên tới + tỷ lệ bao phủ lịch sử của biên 90% (từ `start`)."""
    lam = float(get("outlook.ewma_lambda", 0.94) if lam is None else lam)
    start = pd.Timestamp(start or get("outlook.history_start", "2019-01-02"))
    c = close.dropna().astype(float)
    r = _log_ret(c)
    sig = ewma_sigma(r, lam)
    last, s = float(c.iloc[-1]), float(sig.iloc[-1])
    out = {}
    for h in horizons:
        fwd = sum(r.shift(-k) for k in range(1, h + 1))
        ok = fwd.notna() & sig.notna() & (c.index >= start)
        cover = float((fwd[ok].abs() <= Z90 * sig[ok] * np.sqrt(h)).mean()) if ok.any() else np.nan
        band = lambda z: (last * np.exp(-z * s * np.sqrt(h)), last * np.exp(z * s * np.sqrt(h)))  # noqa: E731
        out[h] = {"sigma_d": s, "lo68": band(Z68)[0], "hi68": band(Z68)[1], "lo90": band(Z90)[0],
                  "hi90": band(Z90)[1], "coverage90": cover, "n_backtest": int(ok.sum())}
    return out


def states(close: pd.Series, nf: pd.Series) -> pd.DataFrame:
    """Trạng thái mỗi phiên: xu hướng (so MA50), động lượng 20 phiên, khối ngoại ròng lũy kế 20 phiên."""
    c = close.astype(float)
    ma50 = c.rolling(50, min_periods=50).mean()
    st = pd.DataFrame(index=c.index)
    st["trend"] = np.where(ma50.isna(), np.nan, np.where(c > ma50, 1.0, -1.0))
    st["mom"] = np.sign(c / c.shift(20) - 1)
    st["flow"] = np.sign(nf.reindex(c.index).rolling(20, min_periods=15).sum())
    return st


STATE_LABELS = {"trend": {1: "trên MA50", -1: "dưới MA50"},
                "mom": {1: "20 phiên tăng", -1: "20 phiên giảm", 0: "20 phiên đi ngang"},
                "flow": {1: "khối ngoại mua ròng 20 phiên", -1: "khối ngoại bán ròng 20 phiên", 0: "khối ngoại cân bằng"}}


def analog_probabilities(close: pd.Series, nf: pd.Series, horizons=(5, 20), start: str | None = None,
                         min_n: int = 30) -> Dict:
    """Tần suất VN-Index tăng sau h phiên trong các phiên lịch sử cùng trạng thái với phiên cuối."""
    start = pd.Timestamp(start or get("outlook.history_start", "2019-01-02"))
    c = close.dropna().astype(float)
    st = states(c, nf)
    now = st.iloc[-1]
    if now.isna().any():
        return {"available": False}
    label = ", ".join(STATE_LABELS[k].get(int(now[k]), "") for k in ("trend", "mom", "flow"))
    res = {"available": True, "state": label, "horizons": {}}
    for h in horizons:
        fwd = (c.shift(-h) / c - 1) * 100
        ok = fwd.notna() & (c.index >= start) & st.notna().all(axis=1)
        same = ok & (st["trend"] == now["trend"]) & (st["mom"] == now["mom"]) & (st["flow"] == now["flow"])
        relaxed = False
        if same.sum() < min_n:            # quá ít phiên tương tự → nới điều kiện (bỏ khối ngoại)
            same = ok & (st["trend"] == now["trend"]) & (st["mom"] == now["mom"])
            relaxed = True
        x, base = fwd[same], fwd[ok]
        res["horizons"][h] = {"n": int(len(x)), "p_up": float((x > 0).mean()) if len(x) else np.nan,
                              "median": float(x.median()) if len(x) else np.nan,
                              "p10": float(x.quantile(.1)) if len(x) else np.nan,
                              "p90": float(x.quantile(.9)) if len(x) else np.nan,
                              "base_p_up": float((base > 0).mean()) if len(base) else np.nan,
                              "base_median": float(base.median()) if len(base) else np.nan,
                              "n_base": int(len(base)), "relaxed": relaxed}
    return res


def signals_today(day: pd.Series, predictive: Optional[pd.DataFrame]) -> List[Dict]:
    """Quy tắc 1–3 kích hoạt ở phiên báo cáo + thành tích lịch sử (t+1…t+5) của quy tắc đó."""
    A = get("alerts", {})
    on = []
    dI, cr5, z = day.get("dI"), day.get("CR5"), day.get("z_NF_total")
    if dI is not None and cr5 is not None and not pd.isna(dI) and not pd.isna(cr5) \
            and abs(dI) >= A.get("dI_min", 5) and cr5 >= A.get("cr5_min", .6):
        on.append("1. Chỉ số do ít mã dẫn dắt")
    if bool(day.get("high_divergence")):
        on.append("2. Độ vênh cao (D ≥ P90 250 phiên)")
    if z is not None and not pd.isna(z):
        if z >= A.get("z_total_nf", 2):
            on.append("3a. Khối ngoại MUA ròng mạnh (z ≥ 2)")
        elif z <= -A.get("z_total_nf", 2):
            on.append("3b. Khối ngoại BÁN ròng mạnh (z ≤ −2)")
    out = []
    for rule in on:
        rec = {"rule": rule}
        if predictive is not None and not predictive.empty:
            p = predictive[(predictive["rule"] == rule) & (predictive["horizon"] == "t+1…t+5")]
            if not p.empty:
                rec.update(p.iloc[0].to_dict())
        out.append(rec)
    return out


def outlook_sentences(vni_close: pd.Series, vr: Dict, an: Dict, sig: List[Dict]) -> List[str]:
    last = float(vni_close.dropna().iloc[-1])
    out = []
    if 5 in vr:
        v5, v20 = vr[5], vr.get(20)
        txt = (f"Độ biến động ngày hiện tại (EWMA) ≈ {fmt.num(v5['sigma_d'] * 100, 2)}%. Với mức này, biên dao động "
               f"68% của VN-Index trong 5 phiên tới là {fmt.num(v5['lo68'], 0)} – {fmt.num(v5['hi68'], 0)} điểm, "
               f"biên 90% là {fmt.num(v5['lo90'], 0)} – {fmt.num(v5['hi90'], 0)} điểm (hiện {fmt.num(last, 0)})")
        if v20:
            txt += f"; 20 phiên tới (90%): {fmt.num(v20['lo90'], 0)} – {fmt.num(v20['hi90'], 0)} điểm"
        txt += (f". Kiểm chứng lịch sử: biên 90% của 5 phiên bao trùm {fmt.frac_pct(v5['coverage90'], 0)} số lần "
                f"({v5['n_backtest']} phiên).")
        out.append(txt)
    if an.get("available"):
        for h in (5, 20):
            x = an["horizons"].get(h)
            if not x or not x["n"]:
                continue
            cond = "cùng xu hướng và động lượng" if x["relaxed"] else "cùng trạng thái"
            out.append(f"{h} phiên tới – trong {x['n']} phiên lịch sử {cond} ({an['state']}), VN-Index cao hơn sau "
                       f"{h} phiên ở {fmt.frac_pct(x['p_up'], 0)} trường hợp (bình quân mọi phiên: "
                       f"{fmt.frac_pct(x['base_p_up'], 0)}); trung vị {fmt.pct(x['median'], 1)}, khoảng 10–90%: "
                       f"{fmt.pct(x['p10'], 1)} đến {fmt.pct(x['p90'], 1)}.")
    if sig:
        for s in sig:
            if "hit_rate" in s and not pd.isna(s.get("hit_rate")):
                out.append(f"Tín hiệu hôm nay: {s['rule']}. Lịch sử ({int(s['n_signal'])} lần): lợi suất 5 phiên sau "
                           f"theo hướng tín hiệu TB {fmt.pct(s['mean_signal_pct'], 2)} so với {fmt.pct(s['mean_base_pct'], 2)} "
                           f"ở phiên thường, cùng hướng {fmt.frac_pct(s['hit_rate'], 0)} (p Welch = "
                           f"{fmt.num(s['welch_p'], 3)}).")
            else:
                out.append(f"Tín hiệu hôm nay: {s['rule']} (chưa đủ lịch sử để đánh giá).")
    else:
        out.append("Không có tín hiệu cảnh báo thị trường (quy tắc 1–3) nào kích hoạt ở phiên này.")
    out.append("Đây là ước lượng thống kê mô tả từ dữ liệu quá khứ, KHÔNG phải dự báo chắc chắn hay khuyến nghị đầu tư.")
    return out


# ── tóm tắt diễn biến nhiều kỳ ─────────────────────────────────────────────────
def recap(hist: pd.DataFrame, n_short: int = 5, n_long: int = 20) -> Dict:
    """Thống kê 5 và 20 phiên gần nhất từ indicator_daily (đã sắp theo ngày, kết thúc tại phiên báo cáo)."""
    h = hist.sort_values("trade_date")
    out = {}
    for n in (n_short, n_long):
        x = h.tail(n)
        prev = h.iloc[-(n + 1)] if len(h) > n else None
        out[n] = {
            "n": len(x),
            "d0": pd.Timestamp(x["trade_date"].iloc[0]),
            "vni_chg": float(x["vni"].iloc[-1] - prev["vni"]) if prev is not None else np.nan,
            "vni_ret": float((x["vni"].iloc[-1] / prev["vni"] - 1) * 100) if prev is not None else np.nan,
            "up_sessions": int((x["r_vni_pct"] > 0).sum()),
            "nf_cum": float(x["NF_total"].sum()),
            "nf_buy_days": int((x["NF_total"] > 0).sum()),
            "nf_missing": int(x["NF_total"].isna().sum()),
            "tv_avg": float(x["tv_total"].mean()),
            "pct_up_avg": float(x["pct_up"].mean()),
            "D_avg": float(x["D"].mean()),
            "CR5_avg": float(x["CR5"].mean()),
            "types": x["session_type"].value_counts().to_dict(),
        }
    tv_prev = h["tv_total"].iloc[-(n_long + n_short):-n_short]
    out["tv_ratio"] = float(out[n_short]["tv_avg"] / tv_prev.mean()) if len(tv_prev) else np.nan
    return out


def sector_returns(stock: pd.DataFrame, dates: List[pd.Timestamp]) -> pd.DataFrame:
    """Lợi suất ngành lũy kế theo vốn hóa (cùng cách tính trang Tổng quan) + khối ngoại ròng trong kỳ."""
    s = stock[stock["trade_date"].isin(dates) & stock["is_valid"]].copy()
    if s.empty:
        return pd.DataFrame(columns=["sector", "ret_pct", "net_flow"])
    s["wr"] = s["w"] * s["ret"]
    agg = s.groupby(["trade_date", "sector"]).agg(wr=("wr", "sum"), w=("w", "sum"), nf=("net_flow", "sum")).reset_index()
    agg["r"] = agg["wr"] / agg["w"].replace(0, np.nan)
    out = agg.groupby("sector").agg(ret_pct=("r", lambda r: ((1 + r.fillna(0)).prod() - 1) * 100),
                                    net_flow=("nf", "sum")).reset_index()
    return out.sort_values("ret_pct", ascending=False)


def cum_leaders(stock: pd.DataFrame, dates: List[pd.Timestamp], n: int = 5) -> pd.DataFrame:
    """Mã đóng góp điểm lũy kế lớn nhất trong kỳ (ΣC)."""
    s = stock[stock["trade_date"].isin(dates)]
    g = s.groupby("symbol").agg(C=("C", "sum"), nf=("net_flow", "sum")).reset_index()
    return pd.concat([g.nlargest(n, "C"), g.nsmallest(n, "C")]).drop_duplicates("symbol")


def group_cum_returns(groups: pd.DataFrame, since: pd.Timestamp) -> Dict[str, float]:
    """Lợi suất đồng trọng số lũy kế (%) của các rổ universe (FTSE, CONTROL, VN30) từ `since`."""
    g = groups[(groups["group_type"] == "universe") & (pd.to_datetime(groups["trade_date"]) >= since)]
    return {k: float(((1 + v.sort_values("trade_date")["ret_eq"].fillna(0)).prod() - 1) * 100)
            for k, v in g.groupby("group_name")}


def recap_sentences(rc: Dict, idx_ret: Dict[str, Dict], sec5: pd.DataFrame, lead20: pd.DataFrame,
                    ftse_rel: Dict[str, Dict[str, float]]) -> List[str]:
    from src.finance.breadth import session_type_label
    a, b = rc[5], rc[20]
    out = []
    v = idx_ret.get("VN-Index", {})
    out.append(f"Tuần qua (5 phiên từ {a['d0']:%d/%m}): VN-Index {fmt.num(a['vni_chg'], 2, True)} điểm "
               f"({fmt.pct(a['vni_ret'])}), {a['up_sessions']}/5 phiên tăng; 1 tháng {fmt.pct(v.get('1Th'))}, "
               f"3 tháng {fmt.pct(v.get('3Th'))}, từ đầu năm {fmt.pct(v.get('YTD'))}.")
    out.append(f"20 phiên gần nhất: {b['up_sessions']}/20 phiên tăng; bình quân {fmt.num(b['pct_up_avg'], 0)}% số mã tăng "
               f"mỗi phiên (5 phiên gần nhất: {fmt.num(a['pct_up_avg'], 0)}%); độ vênh D bình quân "
               f"{fmt.num(b['D_avg'], 2, True)} đ.%, CR5 bình quân {fmt.frac_pct(b['CR5_avg'], 0)}.")
    types = sorted(b["types"].items(), key=lambda kv: -kv[1])
    out.append("Cơ cấu loại phiên 20 phiên: " + ", ".join(f"{session_type_label(k)} {n}" for k, n in types) + ".")
    tvr = rc.get("tv_ratio")
    out.append(f"Thanh khoản khớp lệnh 5 phiên bình quân {fmt.bn(a['tv_avg'], 0, False)}/phiên"
               + (f", bằng {fmt.num(tvr * 100, 0)}% mức 20 phiên trước đó." if tvr and not pd.isna(tvr) else "."))
    miss = b.get("nf_missing", 0)
    out.append(f"Khối ngoại: ròng {fmt.bn(a['nf_cum'])} trong 5 phiên ({a['nf_buy_days']}/5 phiên mua ròng) và "
               f"{fmt.bn(b['nf_cum'])} trong 20 phiên ({b['nf_buy_days']}/20 phiên mua ròng)"
               + (f"; {miss} phiên SSI chưa công bố số liệu khối ngoại (không tính)." if miss else "."))
    if not sec5.empty:
        top, bot = sec5.head(2), sec5.tail(2).iloc[::-1]
        out.append("Ngành 5 phiên – mạnh nhất: " + ", ".join(f"{r.sector} {fmt.pct(r.ret_pct, 1)}" for r in top.itertuples())
                   + "; yếu nhất: " + ", ".join(f"{r.sector} {fmt.pct(r.ret_pct, 1)}" for r in bot.itertuples()) + ".")
    if not lead20.empty:
        pos = lead20[lead20["C"] > 0].nlargest(3, "C")
        neg = lead20[lead20["C"] < 0].nsmallest(3, "C")
        out.append("Dẫn dắt 20 phiên (ΣC): kéo lên " + (", ".join(f"{r.symbol} {fmt.num(r.C, 1, True)}" for r in pos.itertuples()) or "—")
                   + " điểm; kéo xuống " + (", ".join(f"{r.symbol} {fmt.num(r.C, 1, True)}" for r in neg.itertuples()) or "—") + " điểm.")
    for lbl, d in ftse_rel.items():
        if "FTSE" in d and "CONTROL" in d:
            out.append(f"Nhóm FTSE {lbl}: {fmt.pct(d['FTSE'], 1)} so với nhóm đối chứng {fmt.pct(d['CONTROL'], 1)} "
                       f"(chênh {fmt.num(d['FTSE'] - d['CONTROL'], 1, True)} đ.%, đồng trọng số).")
    return out
