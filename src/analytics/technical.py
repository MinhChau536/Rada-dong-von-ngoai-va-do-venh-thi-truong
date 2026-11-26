"""
Chẩn đoán kỹ thuật VN-Index từ giá đóng cửa và giá trị giao dịch (SSI FastConnect V3):

  Xu hướng      MA20, MA50, MA200; cấu trúc đỉnh – đáy kiểu Dow: so đỉnh/đáy của 20 phiên gần nhất với 20 phiên trước đó
                (đỉnh cao dần + đáy cao dần = xu hướng tăng; đỉnh thấp dần + đáy thấp dần = xu hướng giảm; còn lại: đi ngang)
  Động lượng    RSI(14) Wilder: RSI = 100 − 100/(1 + RS), RS = trung bình tăng / trung bình giảm (làm trơn 1/14);
                ≥ 70 quá mua, ≤ 30 quá bán. MACD = EMA12 − EMA26, tín hiệu = EMA9(MACD), histogram = MACD − tín hiệu
  Khối lượng    GTGD phiên / TB 20 phiên; xác nhận khi giá và thanh khoản cùng chiều (tăng giá + GTGD ≥ TB20 = xác nhận tăng;
                giảm giá + GTGD ≥ TB20 = áp lực bán thật; biến động giá với GTGD thấp = thiếu xác nhận)
  Ngưỡng        Hỗ trợ / kháng cự = đáy / đỉnh giá đóng cửa 20/60/120/250 phiên TRƯỚC phiên này và MA20/50/200;
                khi giá đang ở đáy mới của 250 phiên, hỗ trợ tham chiếu = cận dưới biên dao động EWMA 68%/90% 5 phiên
Mọi quy tắc cố định trước, mô tả trạng thái – không phải tín hiệu mua/bán.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up, dn = d.clip(lower=0), (-d).clip(lower=0)
    au = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = au / ad.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9) -> pd.DataFrame:
    m = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    s = m.ewm(span=sig, adjust=False).mean()
    return pd.DataFrame({"macd": m, "signal": s, "hist": m - s})


def snapshot(day: pd.DataFrame) -> Dict:
    """Các chỉ báo kỹ thuật của phiên cuối cùng trong `day` (indicator_daily)."""
    d = day.copy()
    d["trade_date"] = pd.to_datetime(d["trade_date"])
    d = d.set_index("trade_date").sort_index()
    c = d["vni"].astype(float)
    tv = d["tv_total"].astype(float)
    r = rsi(c)
    m = macd(c)
    last = float(c.iloc[-1])
    hi20, lo20 = c.iloc[-20:].max(), c.iloc[-20:].min()
    hi20p, lo20p = c.iloc[-40:-20].max(), c.iloc[-40:-20].min()
    hi60, lo60 = c.iloc[-60:].max(), c.iloc[-60:].min()
    if hi20 > hi20p and lo20 > lo20p:
        struct = ("Đỉnh và đáy cao dần – cấu trúc tăng", "pos")
    elif hi20 < hi20p and lo20 < lo20p:
        struct = ("Đỉnh và đáy thấp dần – cấu trúc giảm", "neg")
    else:
        struct = ("Đỉnh/đáy không cùng chiều – đi ngang, tích lũy", "neu")
    tv20 = tv.iloc[-21:-1].mean()
    tvr = float(tv.iloc[-1] / tv20) if tv20 else np.nan
    r1 = float(c.iloc[-1] / c.iloc[-2] - 1) * 100
    if r1 > 0 and tvr >= 1:
        vconf = ("Giá tăng kèm thanh khoản ≥ TB20 – lực cầu được xác nhận", "pos")
    elif r1 < 0 and tvr >= 1:
        vconf = ("Giá giảm kèm thanh khoản ≥ TB20 – áp lực bán thực sự", "neg")
    elif r1 > 0:
        vconf = ("Giá tăng nhưng thanh khoản thấp – thiếu xác nhận, dễ là nhịp hồi kỹ thuật", "neu")
    else:
        vconf = ("Giá giảm với thanh khoản thấp – lực bán chưa mạnh, chủ yếu do thiếu cầu", "neu")
    # chuỗi phiên giảm/tăng có thanh khoản cao trong 20 phiên (phân phối / tích lũy kiểu O'Neil, chỉ để mô tả)
    rr = c.pct_change()
    hv = tv > tv.rolling(20).mean().shift(1)
    dist = int(((rr < -0.002) & hv).iloc[-20:].sum())
    accu = int(((rr > 0.002) & hv).iloc[-20:].sum())
    ma20, ma50 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1]
    ma200 = c.rolling(200).mean().iloc[-1]
    rv, mh, mh_prev = float(r.iloc[-1]), float(m["hist"].iloc[-1]), float(m["hist"].iloc[-2])
    prev = c.iloc[:-1]                                   # ngưỡng lấy từ các phiên TRƯỚC (phiên này có thể là đỉnh/đáy mới)
    lows = [prev.iloc[-n:].min() for n in (20, 60, 120, 250)]
    highs = [prev.iloc[-n:].max() for n in (20, 60, 120, 250)]
    supports = sorted({round(x, 0) for x in lows + [ma20, ma50, ma200] if pd.notna(x) and x < last * 0.999}, reverse=True)
    resists = sorted({round(x, 0) for x in highs + [ma20, ma50, ma200] if pd.notna(x) and x > last * 1.001})
    return {"close": last, "r1": r1, "ma20": ma20, "ma50": ma50, "ma200": ma200, "rsi": rv, "rsi_series": r,
            "macd": float(m["macd"].iloc[-1]), "macd_signal": float(m["signal"].iloc[-1]), "macd_hist": mh,
            "macd_hist_prev": mh_prev, "macd_df": m, "hi20": hi20, "lo20": lo20, "hi60": hi60, "lo60": lo60,
            "structure": struct, "tv_ratio": tvr, "vol_confirm": vconf, "dist_days": dist, "accu_days": accu,
            "supports": supports[:3], "resists": resists[:3], "close_series": c}


def rows(t: Dict) -> List[Dict]:
    """Bảng chẩn đoán kỹ thuật: khía cạnh · số liệu · đọc kết quả · đánh giá · quy tắc."""
    from src.common import fmt
    out = []

    def add(name, val, txt, tone, rule):
        out.append({"group": "Kỹ thuật", "name": name, "value": val, "reading": txt, "tone": tone, "rule": rule})

    above = [n for n, v in (("MA20", t["ma20"]), ("MA50", t["ma50"]), ("MA200", t["ma200"])) if pd.notna(v) and t["close"] > v]
    add("Đường trung bình", f"MA20 {fmt.num(t['ma20'], 0)} · MA50 {fmt.num(t['ma50'], 0)} · MA200 {fmt.num(t['ma200'], 0)}",
        f"trên {', '.join(above)}" if above else "dưới cả ba đường MA",
        "pos" if len(above) == 3 else "neg" if not above else "neu", "Giá so với MA20/50/200")
    add("Cấu trúc đỉnh – đáy (Dow)", f"20 phiên: {fmt.num(t['lo20'], 0)} – {fmt.num(t['hi20'], 0)}", t["structure"][0],
        t["structure"][1], "So đỉnh/đáy 20 phiên gần nhất với 20 phiên trước")
    rv = t["rsi"]
    add("RSI(14)", fmt.num(rv, 1), "quá mua" if rv >= 70 else "quá bán" if rv <= 30 else
        "nghiêng yếu" if rv < 45 else "nghiêng mạnh" if rv > 55 else "trung tính",
        "neg" if rv < 45 else "pos" if rv > 55 else "neu", "≥ 70 quá mua · ≤ 30 quá bán · 45–55 trung tính")
    mh, mp = t["macd_hist"], t["macd_hist_prev"]
    add("MACD (12, 26, 9)", f"MACD {fmt.num(t['macd'], 1, True)} · tín hiệu {fmt.num(t['macd_signal'], 1, True)}",
        ("trên đường tín hiệu" if mh > 0 else "dưới đường tín hiệu")
        + (", histogram mở rộng" if abs(mh) > abs(mp) else ", histogram thu hẹp")
        + (" – vừa cắt lên" if mh > 0 >= mp else " – vừa cắt xuống" if mh < 0 <= mp else ""),
        "pos" if mh > 0 else "neg", "MACD − tín hiệu > 0: động lượng tăng")
    add("Khối lượng xác nhận", f"GTGD = {fmt.num(t['tv_ratio'], 2)} × TB20", t["vol_confirm"][0], t["vol_confirm"][1],
        "Chiều giá × (GTGD ≥ TB20)")
    add("Phiên phân phối / tích lũy (20 phiên)", f"{t['dist_days']} phiên phân phối · {t['accu_days']} phiên tích lũy",
        "áp lực phân phối chiếm ưu thế" if t["dist_days"] >= t["accu_days"] + 2 else
        "lực tích lũy chiếm ưu thế" if t["accu_days"] >= t["dist_days"] + 2 else "cân bằng",
        "neg" if t["dist_days"] >= t["accu_days"] + 2 else "pos" if t["accu_days"] >= t["dist_days"] + 2 else "neu",
        "Đếm phiên |r| > 0,2% và GTGD > TB20")
    return out


def scenarios(t: Dict, vr: Dict) -> List[Dict]:
    """Kịch bản theo dõi dạng điều kiện từ các ngưỡng kỹ thuật và biên dao động EWMA."""
    from src.common import fmt
    if not t["supports"] and 5 in (vr or {}):            # đáy mới của 250 phiên: dùng cận dưới biên 68% 5 phiên
        t = {**t, "supports": [round(vr[5]["lo68"], 0), round(vr[5]["lo90"], 0)]}
    sup = t["supports"][0] if t["supports"] else t["lo20"]
    res = t["resists"][0] if t["resists"] else t["hi20"]
    out = [{"case": "Tích cực", "cond": f"Đóng cửa trên {fmt.num(res, 0)} (kháng cự gần nhất) với GTGD ≥ TB20",
            "meaning": "Phá vỡ có thanh khoản xác nhận – cấu trúc ngắn hạn cải thiện; ngưỡng kế tiếp "
                       + (fmt.num(t["resists"][1], 0) if len(t["resists"]) > 1 else fmt.num(t["hi60"], 0)) + "."},
           {"case": "Cơ sở", "cond": f"Dao động trong vùng {fmt.num(sup, 0)} – {fmt.num(res, 0)}",
            "meaning": "Thị trường tích lũy; chỉ số chưa xác nhận hướng, ưu tiên quan sát độ rộng và khối ngoại."},
           {"case": "Tiêu cực", "cond": f"Đóng cửa dưới {fmt.num(sup, 0)} (hỗ trợ gần nhất)",
            "meaning": "Thủng hỗ trợ – rủi ro giảm tiếp về "
                       + (fmt.num(t["supports"][1], 0) if len(t["supports"]) > 1 else fmt.num(t["lo60"], 0)) + "."}]
    if 5 in (vr or {}):
        r = vr[5]
        out.append({"case": "Biên thống kê 5 phiên", "cond": f"90%: {fmt.num(r['lo90'], 0)} – {fmt.num(r['hi90'], 0)}",
                    "meaning": f"Vượt ra ngoài là tình huống hiếm (bao phủ lịch sử {fmt.frac_pct(r.get('coverage90'), 0)})."})
    return out


def market_state(day: pd.DataFrame) -> List[Dict]:
    """Bảng trạng thái thị trường theo từng chỉ báo (quy tắc cố định, không chấm điểm tổng):
    nhóm "Kỹ thuật" (rows) + nhóm "Cấu trúc & dòng vốn" (lan tỏa, CR5, khối ngoại 5 phiên, σ EWMA)."""
    from src.analytics.outlook import ewma_sigma
    from src.common import fmt
    d = day.copy()
    d["trade_date"] = pd.to_datetime(d["trade_date"])
    d = d.set_index("trade_date").sort_index()
    v = d["vni"].astype(float)
    nf = d["NF_total"].astype(float)
    sd60 = nf.shift(1).rolling(60, min_periods=30).std()
    nf5z = float((nf.rolling(5).sum() / (sd60 * np.sqrt(5))).iloc[-1])
    sig = float(ewma_sigma(np.log(v / v.shift(1))).iloc[-1] * 100)
    x = d.iloc[-1]
    out = rows(snapshot(day))

    def add(name, val, txt, tone, rule):
        out.append({"group": "Cấu trúc & dòng vốn", "name": name, "value": val, "reading": txt, "tone": tone, "rule": rule})

    add("Độ lan tỏa", f"{fmt.num(x['pct_up'], 0)}% mã tăng · D {fmt.num(x['D'], 2, True)}",
        "lan tỏa tốt" if x["pct_up"] >= 55 else "lan tỏa yếu" if x["pct_up"] <= 40 else "trung tính",
        "pos" if x["pct_up"] >= 55 else "neg" if x["pct_up"] <= 40 else "neu", "≥ 55% mã tăng: tốt · ≤ 40%: yếu")
    add("Tập trung đóng góp", f"CR5 {fmt.frac_pct(x['CR5'], 0)} (phân vị {fmt.num(x.get('CR5_pct250'), 0)}%)",
        "chỉ số bị vài mã chi phối" if (x.get("CR5_pct250") or 0) >= 80 else "bình thường",
        "neg" if (x.get("CR5_pct250") or 0) >= 80 else "neu", "Phân vị 250 phiên ≥ 80: tập trung cao")
    add("Khối ngoại 5 phiên", f"z = {fmt.num(nf5z, 2, True)}",
        "mua ròng mạnh" if nf5z >= 2 else "mua ròng cao hơn bình thường" if nf5z >= 1 else
        "bán ròng mạnh" if nf5z <= -2 else "bán ròng cao hơn bình thường" if nf5z <= -1 else "trung tính",
        "pos" if nf5z >= 1 else "neg" if nf5z <= -1 else "neu", "|z| ≥ 2: mạnh · |z| ≥ 1: cao hơn bình thường (so 60 phiên)")
    add("Biến động", f"σ ngày {fmt.num(sig, 2)}%",
        "biến động cao" if sig >= 1.5 else "biến động thấp" if sig <= 0.8 else "bình thường",
        "neg" if sig >= 1.5 else "neu", "σ EWMA ≥ 1,5%: cao · ≤ 0,8%: thấp")
    return out


def headline(state: List[Dict]) -> str:
    """Một câu nhận định kỹ thuật tự nhiên từ bảng trạng thái."""
    r = {x["name"]: x for x in state}
    ma = r.get("Đường trung bình", {}).get("reading", "")
    st_ = r.get("Cấu trúc đỉnh – đáy (Dow)", {}).get("reading", "").split(" – ")[0].lower()
    rsi = r.get("RSI(14)", {})
    neg = sum(x["tone"] == "neg" for x in state)
    pos = sum(x["tone"] == "pos" for x in state)
    tone = "tiêu cực" if neg > pos else "tích cực" if pos > neg else "trung tính"
    return (f"VN-Index {ma}, {st_}, RSI(14) {rsi.get('value', '—')} ({rsi.get('reading', '')}) – bức tranh kỹ thuật {tone} "
            f"({pos} chỉ báo tích cực, {neg} tiêu cực trên {len(state)}).")
