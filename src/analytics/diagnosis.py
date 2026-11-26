"""
Chẩn đoán thị trường – nối độ vênh, mã dẫn dắt, khối ngoại, nhóm FTSE và watchlist thành câu trả lời nghiên cứu.

Chỉ báo mới (mỗi phiên, tính từ indicator_stock_daily, không nhìn trước):
  codir      = Σ|C_i| của các mã có |nf_i| ≥ 5% VÀ dấu NF_i trùng dấu C_i  /  Σ|C_i|      (nf_i = NF_i / GTGD_i)
               → bao nhiêu phần biến động điểm đến từ những mã mà khối ngoại mua/bán ròng ĐÁNG KỂ, CÙNG CHIỀU giá.
               Lọc |nf_i| ≥ 5% để giao dịch ròng lặt vặt không được tính là "cùng chiều" (không lọc thì mức thường lệ
               đã ≈ 2/3 mọi phiên). codir_base = trung vị 250 phiên trước → so với mức thường lệ, không so với 50%.
               Đây là quan hệ CÙNG PHIÊN, không cho biết khối ngoại gây ra biến động.
  hhi_w      = Σ w_i²  (w_i = tỷ trọng vốn hóa trong rổ)  → độ tập trung TỶ TRỌNG chỉ số; biến kiểm soát cho CR5:
               CR5 có thể tăng chỉ vì vài mã phình tỷ trọng (VIC 2025), không phải vì thị trường "tập trung hơn".
  eff_n      = 1 / hhi_w  → số mã "hiệu dụng" của chỉ số.
  big_C      = ΣC của 10 mã tỷ trọng lớn nhất (điểm) · big_ret = big_C / I(t−1) × 100 (điểm %).
  big_nf     = NF của 10 mã tỷ trọng lớn nhất / GTGD của chúng.
  ftse_C     = ΣC của 27 mã vào rổ FTSE (danh sách chính thức 21/08/2026).
  hhi_flow_n = (HHI − 1/N) / (1 − 1/N), N = số mã có khối ngoại ròng ≠ 0  → HHI dòng vốn đã chuẩn hóa theo số mã.
  z_rob      = (NF − trung vị 60 phiên trước) / (1,4826 · MAD 60 phiên trước)  → z bền vững với đuôi dày.

Hồi quy gộp (HAC 5 trễ):  D_t = a + b1·hhi_w_t + b2·big_ret_t + b3·big_nf_t + b4·|r_VNI|_t + e_t
→ trả lời trực tiếp: độ vênh đến từ TẬP TRUNG tỷ trọng / nhóm vốn hóa lớn, hay từ KHỐI NGOẠI.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm

from src.common.config import ftse_universe, get

BIG_N = 10
CODIR_MIN_NF = 0.05          # |NF_i / GTGD_i| tối thiểu để coi là khối ngoại mua/bán ròng đáng kể


def codir_level(cod, base) -> str:
    """So codir của phiên với mức thường lệ (trung vị 250 phiên trước)."""
    if cod is None or base is None or pd.isna(cod) or pd.isna(base):
        return "chưa đủ lịch sử để so"
    if cod >= base + 0.10:
        return "cao hơn mức thường lệ"
    if cod <= base - 0.10:
        return "thấp hơn mức thường lệ"
    return "tương đương mức thường lệ"


def codir_sentence(cod, base) -> str:
    """Một câu dùng chung cho web, bot, PDF – nói rõ là quan hệ cùng phiên."""
    from src.common import fmt
    if cod is None or pd.isna(cod):
        return "Chưa đủ dữ liệu khối ngoại để đánh giá."
    return (f"{fmt.frac_pct(cod, 0)} biến động điểm đến từ các mã có khối ngoại mua/bán ròng đáng kể (≥ 5% GTGD của mã) "
            f"cùng chiều giá – {codir_level(cod, base)}"
            + (f" (trung vị 250 phiên: {fmt.frac_pct(base, 0)})" if base is not None and pd.notna(base) else "")
            + ". Đây là quan hệ cùng phiên, không cho biết khối ngoại gây ra biến động.")


def representative(x) -> str:
    """Chỉ số có đại diện cho số đông không – chỉ kết luận 'không đại diện' khi D ở 20% cao nhất/thấp nhất 250 phiên."""
    pct = x.get("D_pct250") if hasattr(x, "get") else None
    if pct is None or pd.isna(pct):
        return "chưa đủ lịch sử để đánh giá độ đại diện của chỉ số"
    if pct >= 80:
        return "chỉ số tăng mạnh hơn hẳn số đông cổ phiếu – ít đại diện cho danh mục thông thường" if x["D"] > 0 else             "độ vênh ở mức cao bất thường – chỉ số ít đại diện cho số đông"
    if pct <= 20:
        return "chỉ số giảm mạnh hơn hẳn số đông cổ phiếu – ít đại diện cho danh mục thông thường" if x["D"] < 0 else             "độ vênh ở mức thấp bất thường – chỉ số ít đại diện cho số đông"
    return "độ vênh trong vùng bình thường – chỉ số phản ánh tương đối sát số đông cổ phiếu"


def daily_extras(stock: pd.DataFrame, day: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    cols = ["trade_date", "symbol", "w", "C", "net_flow", "tv"] + (["nf"] if "nf" in stock else [])
    s = stock[stock["is_valid"].astype(bool)][cols].copy()
    s["trade_date"] = pd.to_datetime(s["trade_date"])
    s["absC"] = s["C"].abs()
    nf = s["net_flow"].fillna(0)
    nf_i = s["nf"] if "nf" in s else nf / s["tv"].replace(0, np.nan)     # nf đã dùng mẫu số gồm thỏa thuận
    s["same"] = (np.sign(nf) == np.sign(s["C"])) & (nf_i.abs() >= CODIR_MIN_NF) & (s["C"] != 0)
    s["absC_same"] = s["absC"].where(s["same"], 0.0)
    wsum = s.groupby("trade_date")["w"].transform("sum")
    s["wn"] = s["w"] / wsum.replace(0, np.nan)
    s["w2"] = s["wn"] ** 2
    s["rk"] = s.groupby("trade_date")["w"].rank(ascending=False, method="first")
    big = s[s["rk"] <= BIG_N]
    ftse = set(ftse_universe()["symbol"]) if not ftse_universe().empty else set()
    g = s.groupby("trade_date")
    out = pd.DataFrame({"absC": g["absC"].sum(), "absC_same": g["absC_same"].sum(), "hhi_w": g["w2"].sum(),
                        "n_flow": g["net_flow"].apply(lambda x: int((x.fillna(0) != 0).sum()))})
    out["codir"] = out["absC_same"] / out["absC"].replace(0, np.nan)
    out = out.sort_index()
    out["codir_base"] = out["codir"].shift(1).rolling(250, min_periods=60).median()
    out["eff_n"] = 1 / out["hhi_w"]
    gb = big.groupby("trade_date")
    out["big_C"] = gb["C"].sum()
    out["big_nf"] = gb["net_flow"].sum() / gb["tv"].sum().replace(0, np.nan)
    out["ftse_C"] = s[s["symbol"].isin(ftse)].groupby("trade_date")["C"].sum()
    out = out.reset_index()
    if day is not None and not day.empty:
        d = day[["trade_date", "prev_value", "dI", "HHI", "NF_total"]].copy()
        d["trade_date"] = pd.to_datetime(d["trade_date"])
        out = out.merge(d, on="trade_date", how="left")
        out["big_ret"] = out["big_C"] / out["prev_value"] * 100
        out["ftse_share"] = out["ftse_C"] / out["dI"].replace(0, np.nan)
        n = out["n_flow"].where(out["n_flow"] > 1)
        out["hhi_flow_n"] = (out["HHI"] - 1 / n) / (1 - 1 / n)
        out["hhi_eq_n"] = 1 / out["HHI"]                      # HHI ≈ dòng vốn trải đều trên 1/HHI mã
        x = out.set_index("trade_date")["NF_total"]
        med = x.shift(1).rolling(60, min_periods=30).median()
        mad = (x.shift(1) - med).abs().rolling(60, min_periods=30).median()
        out["z_rob"] = ((x - med) / (1.4826 * mad.replace(0, np.nan))).to_numpy()
    return out.sort_values("trade_date").reset_index(drop=True)


def d_regression(day: pd.DataFrame, extras: pd.DataFrame, start: Optional[str] = None) -> Dict:
    """Hồi quy gộp D ~ hhi_w + big_ret + big_nf + |r_VNI| (HAC). Biến chuẩn hóa z để so sánh độ lớn hệ số."""
    lags = int(get("events.nw_lags", 5))
    d = day[["trade_date", "D", "r_vni_pct"]].copy()
    d["trade_date"] = pd.to_datetime(d["trade_date"])
    m = d.merge(extras[["trade_date", "hhi_w", "big_ret", "big_nf"]], on="trade_date").dropna()
    m = m[m["trade_date"] >= pd.Timestamp(start or get("periods.pre_start", "2019-01-02"))]
    if len(m) < 60:
        return {"ok": False}
    X = pd.DataFrame({"hhi_w": m["hhi_w"], "big_ret": m["big_ret"], "big_nf": m["big_nf"], "abs_rvni": m["r_vni_pct"].abs()})
    Xz = (X - X.mean()) / X.std()
    res = sm.OLS(m["D"], sm.add_constant(Xz)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    labels = {"hhi_w": "Tập trung tỷ trọng chỉ số (HHI w)", "big_ret": "Lợi suất 10 mã tỷ trọng lớn nhất",
              "big_nf": "Khối ngoại ròng ở 10 mã lớn (nf)", "abs_rvni": "|Biến động VN-Index|"}
    rows = [{"var": k, "label": labels[k], "coef": float(res.params[k]), "t": float(res.tvalues[k]),
             "p": float(res.pvalues[k])} for k in labels]
    return {"ok": True, "rows": rows, "r2": float(res.rsquared), "n": int(res.nobs),
            "from": m["trade_date"].min(), "to": m["trade_date"].max()}


def evidence_label(p: float, sign_ok: bool = True) -> str:
    if p is None or pd.isna(p):
        return "Chưa đủ dữ liệu"
    if p < 0.05 and sign_ok:
        return "Có bằng chứng"
    if p < 0.10:
        return "Bằng chứng yếu"
    return "Chưa đủ bằng chứng"


def session_answers(ctx_day: pd.Series, ex_today: pd.Series, lead: pd.DataFrame, stock_day: pd.DataFrame,
                    watch: Optional[pd.DataFrame] = None) -> List[Dict]:
    """Ba câu trả lời của phiên, bằng lời thường + 2–3 con số (dùng chung cho web, bot, PDF)."""
    from src.common import fmt
    from src.finance.breadth import session_label
    x = ctx_day
    out = []
    pct = x.get("D_pct250")
    out.append({"q": "Chỉ số hôm nay có phản ánh đúng thị trường không?",
                "a": f"VN-Index {fmt.pct(x['r_vni_pct'])}, cổ phiếu trung vị {fmt.pct(x['median_ret_pct'])}: {representative(x)} "
                     f"(độ vênh D = {fmt.num(x['D'], 2, True)} điểm %, "
                     + (f"cao hơn {fmt.num(pct, 0)}% số phiên trong một năm). " if pd.notna(pct) and pct >= 50 else
                        f"thấp hơn {fmt.num(100 - pct, 0)}% số phiên trong một năm). " if pd.notna(pct) else "). ")
                     + f"Loại phiên: {session_label(x).lower()}, {fmt.num(x['pct_up'], 0)}% số mã tăng."})
    pos, neg = lead[lead["side"] == "pos"].head(3), lead[lead["side"] == "neg"].head(3)
    main = neg if x["dI"] < 0 else pos
    out.append({"q": "Ai tạo ra biến động, và khối ngoại đi cùng chiều đến đâu?",
                "a": f"5 mã ảnh hưởng nhất tạo {fmt.frac_pct(x['CR5'], 0)} tổng đóng góp, dẫn đầu "
                     f"{', '.join(main['symbol'])} ({fmt.num(main['C'].sum(), 2, True)} điểm). "
                     + codir_sentence(ex_today.get("codir"), ex_today.get("codir_base"))
                     + f" Nhóm 27 mã FTSE đóng góp {fmt.num(ex_today.get('ftse_C'), 2, True)} điểm."})
    if watch is not None and not watch.empty and "has_data" in watch:
        w = watch[watch["has_data"].astype(bool)]
        lead_set = set(top_leaders(stock_day))           # cùng định nghĩa với web, bot, PDF: 10 mã |C| lớn nhất toàn sàn
        in_lead = [s for s in w["symbol"] if s in lead_set]
        beat = int((w["ER_M"] > 0).sum())
        out.append({"q": "Điều đó có ý nghĩa gì với các mã tôi đang theo dõi?",
                    "a": f"{beat}/{len(w)} mã watchlist hơn trung vị thị trường; "
                         + (f"{len(in_lead)}/{len(w)} mã ({', '.join(in_lead)}) nằm trong 10 mã dẫn dắt toàn sàn nên chịu tác động "
                            f"trực tiếp của diễn biến chỉ số. " if in_lead else
                            "không mã nào nằm trong 10 mã dẫn dắt toàn sàn – diễn biến chỉ số ít đại diện cho danh mục. ")
                         + f"Khối ngoại ròng trên watchlist: {fmt.bn(w['net_flow'].sum())}."})
    return out


def top_leaders(stock_day: pd.DataFrame, n: int = 10) -> List[str]:
    """Nhóm dẫn dắt của phiên = n mã có |đóng góp điểm C| lớn nhất TOÀN SÀN HOSE (một định nghĩa cho web, bot, PDF)."""
    if stock_day is None or stock_day.empty or "C" not in stock_day:
        return []
    v = stock_day[stock_day["is_valid"].astype(bool)] if "is_valid" in stock_day else stock_day
    v = v.drop_duplicates("symbol")
    return list(v.reindex(v["C"].abs().sort_values(ascending=False).index).head(n)["symbol"])


def implications(x: pd.Series) -> List[str]:
    """Hàm ý dạng câu điều kiện – mô tả cách đọc chỉ số, KHÔNG phải lệnh mua/bán."""
    out = []
    pct = x.get("D_pct250")
    if pd.notna(pct) and (pct >= 80 or pct <= 20):
        out.append("Độ vênh D đang ở nhóm 20% cực trị của 250 phiên – VN-Index ít đại diện cho danh mục thông thường; "
                   "so danh mục với cổ phiếu trung vị sẽ sát hơn so với chỉ số.")
    else:
        out.append("Độ vênh D trong vùng bình thường của 250 phiên – VN-Index phản ánh tương đối sát số đông cổ phiếu.")
    out.append("Khối ngoại mua/bán ròng đáng kể cùng chiều giá ở các mã dẫn dắt cho thấy biến động chỉ số diễn ra cùng lúc "
               "với dòng vốn ngoại – đây là quan hệ cùng phiên, không chứng minh khối ngoại gây ra biến động.")
    out.append("Biên dao động EWMA mô tả mức biến động bình thường của chỉ số – vượt biên 90% là tình huống hiếm "
               "(khoảng 1/10 phiên), không phải tín hiệu giao dịch.")
    return out


def watch_exposure(symbols: List[str], date, stock_hist: pd.DataFrame, day: pd.DataFrame, profile: Optional[pd.DataFrame] = None,
                   market: Optional[pd.DataFrame] = None) -> Dict:
    """Mức phơi nhiễm của watchlist với nhóm dẫn dắt (thay khối tối ưu danh mục – đúng câu hỏi 'tác động lên danh mục'):
      lead_share  – số mã watchlist nằm trong 10 mã |C| lớn nhất của phiên
      vin_share   – số mã thuộc họ Vingroup
      beta_mean   – β Dimson bình quân (đồng trọng số)
      lose_hiD    – tỷ lệ phiên watchlist (đồng trọng số) THUA trung vị thị trường khi độ vênh D ở phân vị ≥ 80 (250 phiên gần nhất)."""
    d = pd.Timestamp(date)
    s = stock_hist.reset_index(drop=True).copy()
    s["trade_date"] = pd.to_datetime(s["trade_date"])
    s = s.drop_duplicates(["trade_date", "symbol"])
    today = s[s["trade_date"] == d]
    # nhóm dẫn dắt phải chọn trên TOÀN SÀN (market = mọi mã của phiên); chọn trong chính watchlist thì luôn ra n/n
    mk = market if market is not None and not market.empty else today
    top = set(top_leaders(mk[pd.to_datetime(mk["trade_date"]) == d] if "trade_date" in mk else mk))
    lead = [x for x in symbols if x in top]
    fam = today.set_index("symbol")["family"] if "family" in today else pd.Series(dtype=object)
    vin = [x for x in symbols if fam.get(x) == "VINGROUP"]
    beta = float(profile["beta_dimson"].astype(float).mean()) if profile is not None and "beta_dimson" in profile else np.nan
    dd = day.copy()
    dd["trade_date"] = pd.to_datetime(dd["trade_date"])
    dd = dd[dd["trade_date"] <= d].tail(250)
    hi = dd[dd["D_pct250"] >= 80]["trade_date"]
    w = s[s["symbol"].isin(symbols) & s["trade_date"].isin(hi)].groupby("trade_date")["ER_M"].mean()
    return {"lead": lead, "vin": vin, "n": len(symbols), "beta": beta,
            "lose_hiD": float((w < 0).mean()) if len(w) else np.nan, "n_hiD": int(len(w)),
            "er_hiD": float(w.mean() * 100) if len(w) else np.nan}


RESEARCH_QUESTIONS = [
    ("CR5 – tập trung đóng góp", "Tập trung đóng góp (CR5) tăng sau công bố FTSE?", "base"),
    ("CR5 – tập trung đóng góp · kiểm soát HHI tỷ trọng", "… vẫn tăng khi đã kiểm soát tỷ trọng phình to?", "control_hhi_w"),
    ("Tỷ lệ phiên thiếu lan tỏa", "Phiên thiếu lan tỏa nhiều hơn sau công bố?", "base"),
    ("Tỷ lệ phiên thiếu lan tỏa · kiểm soát HHI tỷ trọng", "… vẫn nhiều hơn khi đã kiểm soát tỷ trọng phình to?", "control_hhi_w"),
    ("FPR – tỷ trọng GD khối ngoại", "Khối ngoại tham gia giao dịch nhiều hơn?", "base"),
    ("nf toàn sàn – cường độ ròng", "Khối ngoại mua ròng mạnh hơn?", "base"),
    ("D – độ vênh (điểm %)", "Độ vênh bình quân thay đổi?", "base"),
]


def research_rows(sr: pd.DataFrame) -> List[Dict]:
    """Mỗi giả thuyết một dòng (E1 → ngày hiệu lực so với 250 phiên trước E1) + H2c: câu hỏi, ước lượng, p Holm, mức bằng chứng."""
    out = []
    if sr is None or sr.empty:
        return out
    h4 = sr[(sr["hypothesis"] == "H4") & sr["test"].astype(str).str.startswith("OLS")]
    for metric, q, var in RESEARCH_QUESTIONS:
        r = h4[(h4["metric"] == metric) & (h4["window"] == "E1 → hiệu lực") & (h4["variant"] == var)]
        if r.empty:
            continue
        r = r.iloc[0]
        ph = r.get("p_holm") if pd.notna(r.get("p_holm")) else r["p_value"]
        out.append({"key": metric, "q": q, "est": float(r["estimate"]), "p": float(ph), "label": evidence_label(ph)})
    h2c = sr[(sr["hypothesis"] == "H2c") & sr["test"].astype(str).str.startswith("OLS")]
    if not h2c.empty:
        r = h2c.iloc[0]
        out.append({"key": "H2c", "q": "Dòng vốn ngoại vào nhóm vốn hóa lớn giải thích được D?", "est": float(r["estimate"]),
                    "p": float(r["p_value"]), "label": evidence_label(r["p_value"])})
    return out


def main_conclusion(reg: Dict, rows: List[Dict]) -> str:
    """Kết luận nghiên cứu chính, sinh từ số liệu (không viết tay)."""
    from src.common import fmt
    if not reg.get("ok"):
        return "Chưa đủ dữ liệu để kết luận."
    b = {x["var"]: x for x in reg["rows"]}
    big_ok, nf_ok = b["big_ret"]["p"] < 0.05, b["big_nf"]["p"] < 0.05
    ctrl = next((r for r in rows if r["key"].endswith("kiểm soát HHI tỷ trọng")), None)
    s = ("Độ vênh D gắn với " + ("diễn biến của nhóm vốn hóa lớn" if big_ok else "các yếu tố ngoài nhóm vốn hóa lớn")
         + (", không phải với việc khối ngoại mua/bán ròng ở nhóm này" if not nf_ok else " và cả dòng vốn ngoại ở nhóm này")
         + f" (hồi quy gộp {reg['n']} phiên, R² = {fmt.num(reg['r2'], 2)}; p khối ngoại = {fmt.num(b['big_nf']['p'], 2)}). ")
    if ctrl is not None:
        s += ("Sau công bố FTSE, tập trung đóng góp (CR5) tăng và vẫn có ý nghĩa khi đã kiểm soát độ tập trung tỷ trọng chỉ số. "
              if ctrl["label"] == "Có bằng chứng" else
              "Sau công bố FTSE, mức tăng tập trung đóng góp chưa đứng vững khi đã kiểm soát độ tập trung tỷ trọng chỉ số. ")
    return s + "Mô tả thống kê, không khẳng định quan hệ nhân quả."
