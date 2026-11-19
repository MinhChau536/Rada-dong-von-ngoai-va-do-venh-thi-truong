"""
Các chương báo cáo dùng chung cho Market Snapshot và Closing Report. Số liệu lấy từ context.build().

Nguyên tắc viết: mỗi ý là MỘT SO SÁNH SỐ LIỆU (hôm nay so với phiên trước / trung bình 5–20 phiên / phân vị lịch sử /
nhóm đối chứng), nêu rõ đơn vị và kỳ so sánh; không dùng tính từ đánh giá (tích cực, tiêu cực, mạnh, yếu…) khi số liệu
không đi kèm; không khuyến nghị mua/bán.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.common import fmt
from src.common.config import get
from src.data import database as db
from src.finance.breadth import session_type_label
from src.finance.domestic import ABSORB_LABELS
from src.reports import charts
from src.reports.pdf_base import FFRPdf

PERIOD_KEYS = ["1T", "1Th", "3Th", "6Th", "YTD", "1N"]
INDEX_CODES = (("VNINDEX", "VN-Index"), ("VN30", "VN30"), ("HNXINDEX", "HNX-Index"), ("UPCOMINDEX", "UPCoM-Index"))


def _clr(v) -> Optional[str]:
    return None if v is None or pd.isna(v) else "up" if v > 0 else "down" if v < 0 else "ref"


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else "<0,001" if v < 0.001 else fmt.num(v, 3)


def _rank_pct(series: pd.Series, n: int = 250) -> float:
    """Phân vị của giá trị cuối so với n phiên TRƯỚC đó (0–100)."""
    s = series.dropna()
    if len(s) < 21:
        return np.nan
    prev = s.iloc[-(n + 1):-1]
    return float((prev < s.iloc[-1]).mean() * 100)


def _cmp(a, b, unit: str = "", d: int = 1, rel: bool = False) -> str:
    """'cao hơn/thấp hơn/bằng' kèm chênh lệch – câu so sánh trung tính."""
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return "—"
    if rel and b:
        r = (a / b - 1) * 100
        return "bằng" if abs(r) < 0.5 else f"{'cao' if r > 0 else 'thấp'} hơn {fmt.num(abs(r), 0)}%"
    diff = a - b
    return "bằng" if abs(diff) < 10 ** -d / 2 else f"{'cao' if diff > 0 else 'thấp'} hơn {fmt.num(abs(diff), d)}{unit}"


def index_cards(ctx: Dict) -> List:
    idx = ctx["index"].set_index("index_code")
    out = []
    for code, name in INDEX_CODES:
        r = ctx["idx_ret"].get(name, {})
        if code in idx.index:
            out.append((name, fmt.num(idx.loc[code, "value"]),
                        f"{fmt.num(idx.loc[code, 'change'], 2, True)} ({fmt.pct(idx.loc[code, 'ratio_change'])}) · YTD {fmt.pct(r.get('YTD'), 1)}",
                        _clr(idx.loc[code, "change"])))
        else:
            out.append((name, "—", "không có dữ liệu phiên", None))
    return out


def _events(ctx: Dict):
    ev = ctx.get("events")
    return [(r.event_date, r.event_id) for r in ev.itertuples()] if ev is not None and not ev.empty else None


# ── số liệu so sánh ──────────────────────────────────────────────────────────
def key_table(ctx: Dict) -> List[List[str]]:
    """Bảng chỉ tiêu chính: phiên này / phiên trước / TB 5 / TB 20 / phân vị 250 phiên."""
    h = ctx["hist"].copy()
    h["tv_bn"] = h["tv_total"] / 1e9
    h["nf_bn"] = h["NF_total"] / 1e9
    h["CR5p"] = h["CR5"] * 100
    spec = [("Thay đổi VN-Index (%)", "r_vni_pct", 2, True), ("Trung vị lợi suất cổ phiếu (%)", "median_ret_pct", 2, True),
            ("Tỷ lệ mã tăng (%)", "pct_up", 0, False), ("GTGD khớp lệnh (tỷ đồng)", "tv_bn", 0, False),
            ("Khối ngoại ròng (tỷ đồng)", "nf_bn", 0, True), ("Độ vênh D (điểm %)", "D", 2, True),
            ("CR5 – tỷ trọng 5 mã đóng góp (%)", "CR5p", 0, False), ("HHI dòng vốn ngoại", "HHI", 3, False)]
    rows = []
    for lbl, col, d, sg in spec:
        s = h[col]
        prev = s.iloc[-2] if len(s) > 1 else np.nan
        rows.append([lbl, fmt.num(s.iloc[-1], d, sg), fmt.num(prev, d, sg), fmt.num(s.tail(5).mean(), d, sg),
                     fmt.num(s.tail(20).mean(), d, sg), fmt.num(_rank_pct(s), 0, False, "%")])
    return rows


def key_facts(ctx: Dict) -> List[str]:
    """Các ý tóm tắt – mỗi ý là một phép so sánh số liệu."""
    x, h, v = ctx["day"], ctx["hist"], ctx["stock"][ctx["stock"]["is_valid"]]
    vni = ctx["idx_hist"]["VN-Index"]
    out = []
    ma20, ma50 = vni.rolling(20).mean().iloc[-1], vni.rolling(50).mean().iloc[-1]
    rc = ctx["recap"]
    out.append(f"VN-Index đóng cửa {fmt.num(x['vni'])} điểm, {fmt.num(x['dI'], 2, True)} điểm ({fmt.pct(x['r_vni_pct'])}) so với "
               f"phiên trước; {fmt.pct(rc[5]['vni_ret'])} trong 5 phiên và {fmt.pct(rc[20]['vni_ret'])} trong 20 phiên. "
               f"Chỉ số {_cmp(x['vni'], ma20, rel=True)} MA20 ({fmt.num(ma20, 0)}) và {_cmp(x['vni'], ma50, rel=True)} "
               f"MA50 ({fmt.num(ma50, 0)}).")
    pu20 = h["pct_up"].tail(20).mean()
    out.append(f"Độ rộng HOSE: {int(x['n_up'])} mã tăng, {int(x['n_unch'])} đứng giá, {int(x['n_down'])} giảm "
               f"(trần {int(x['n_ceiling'])}, sàn {int(x['n_floor'])}). Tỷ lệ mã tăng {fmt.num(x['pct_up'], 0)}%, "
               f"{_cmp(x['pct_up'], pu20, ' điểm %', 0)} mức bình quân 20 phiên ({fmt.num(pu20, 0)}%). "
               f"Trung vị lợi suất {fmt.pct(x['median_ret_pct'])} so với VN-Index {fmt.pct(x['r_vni_pct'])} "
               f"→ độ vênh D = {fmt.num(x['D'], 2, True)} điểm %.")
    lead = ctx["leaders"]
    pos, neg = lead[lead["side"] == "pos"].head(5), lead[lead["side"] == "neg"].head(5)
    if not lead.empty:
        out.append(f"Đóng góp điểm: 5 mã kéo lên nhiều nhất cộng {fmt.num(pos['C'].sum(), 2, True)} điểm "
                   f"({', '.join(pos['symbol'].head(3))}…); 5 mã kéo xuống nhiều nhất cộng {fmt.num(neg['C'].sum(), 2, True)} điểm "
                   f"({', '.join(neg['symbol'].head(3))}…). Năm mã ảnh hưởng nhất chiếm {fmt.frac_pct(x['CR5'], 0)} tổng "
                   f"đóng góp tuyệt đối (bình quân 20 phiên: {fmt.frac_pct(h['CR5'].tail(20).mean(), 0)}).")
    tv20 = h["tv_total"].tail(21).iloc[:-1].mean()
    out.append(f"Thanh khoản: GTGD khớp lệnh {fmt.bn(x['tv_total'], 0, False)}, {_cmp(x['tv_total'], tv20, rel=True)} "
               f"bình quân 20 phiên trước ({fmt.bn(tv20, 0, False)}).")
    if not pd.isna(x["NF_total"]):
        nf20 = h["NF_total"].tail(21).iloc[:-1].mean()
        tb, ts = ctx["top_buy"], ctx["top_sell"]
        out.append(f"Khối ngoại ròng {fmt.bn(x['NF_total'])} (bình quân 20 phiên trước: {fmt.bn(nf20)}/phiên; "
                   f"z60 = {fmt.num(x['z_NF_total'], 2, True)}). Lũy kế {fmt.bn(rc[5]['nf_cum'])} trong 5 phiên, "
                   f"{fmt.bn(rc[20]['nf_cum'])} trong 20 phiên. Mua ròng nhiều nhất "
                   f"{tb['symbol'].iloc[0]} ({fmt.bn(tb['net_flow'].iloc[0])}); bán ròng nhiều nhất "
                   f"{ts['symbol'].iloc[0]} ({fmt.bn(ts['net_flow'].iloc[0])}).")
    s1 = ctx["sec1"]
    if not s1.empty:
        n_up, n_dn = int((s1["ret_pct"] > 0).sum()), int((s1["ret_pct"] < 0).sum())
        out.append(f"Ngành: {n_up}/{len(s1)} ngành tăng, {n_dn} ngành giảm. Cao nhất {s1.iloc[0]['sector']} "
                   f"({fmt.pct(s1.iloc[0]['ret_pct'], 1)}), thấp nhất {s1.iloc[-1]['sector']} ({fmt.pct(s1.iloc[-1]['ret_pct'], 1)}).")
    return out


def _head(pdf: FFRPdf, sub: bool, title: str, lead: str = "") -> None:
    """Tiêu đề chương (h1, có trong mục lục) hoặc mục con (h2) khi gộp vào một chương lớn."""
    if not sub:
        pdf.h1(title, lead)
        return
    pdf.h2(title, keep=105)                 # mục con thường mở đầu bằng biểu đồ ~90 mm
    if lead:
        pdf.para(lead, 7.8, "I")


# ── 1. Tóm tắt thị trường ────────────────────────────────────────────────────
def ch_summary(pdf: FFRPdf, ctx: Dict) -> None:
    pdf.h1(f"Tóm tắt thị trường phiên {ctx['date']:%d/%m/%Y}",
           "Toàn cảnh phiên giao dịch trong một trang: các con số chính, so sánh với phiên trước và với trung bình gần đây.")
    pdf.cards(index_cards(ctx))
    pdf.callout("Số liệu đáng chú ý", key_facts(ctx))
    pdf.h2("Bảng chỉ tiêu chính – so với lịch sử gần")
    pdf.table(["Chỉ tiêu", "Phiên này", "Phiên trước", "TB 5 phiên", "TB 20 phiên", "Phân vị 250 ph."], key_table(ctx),
              [58, 24, 24, 24, 26, 26])
    pdf.para("Phân vị 250 phiên: tỷ lệ phiên trong 250 phiên trước có giá trị thấp hơn phiên này (50% = mức trung vị một năm).",
             7.2, "I")


# ── 2. Chỉ số và thanh khoản ─────────────────────────────────────────────────
def ch_index(pdf: FFRPdf, ctx: Dict, sub: bool = False) -> None:
    _head(pdf, sub, "Diễn biến chỉ số và thanh khoản", "VN-Index 12 tháng với đường trung bình 20/50 phiên, giá trị khớp lệnh và các mốc nâng hạng FTSE.")
    pdf.figure(charts.index_chart(ctx["idx_hist"]["VN-Index"], ctx["tv_hist"], _events(ctx)),
               caption="Mốc FTSE: E1 công bố 08/10/2025 · E2 xác nhận 08/04/2026 · E3 18/09/2026. GTGD: giá trị khớp lệnh HOSE.")
    pdf.h2("Hiệu suất chỉ số theo kỳ")
    rows = [[name] + [fmt.pct(r.get(k), 1) for k in PERIOD_KEYS] for name, r in ctx["idx_ret"].items()]
    pdf.table(["Chỉ số", "1 tuần", "1 tháng", "3 tháng", "6 tháng", "Từ đầu năm", "1 năm"], rows, [40, 23, 23, 23, 23, 26, 24])
    rc = ctx["recap"]
    pdf.bullets([
        f"5 phiên từ {rc[5]['d0']:%d/%m}: VN-Index {fmt.num(rc[5]['vni_chg'], 2, True)} điểm, {rc[5]['up_sessions']}/5 phiên tăng; "
        f"20 phiên từ {rc[20]['d0']:%d/%m}: {fmt.num(rc[20]['vni_chg'], 2, True)} điểm, {rc[20]['up_sessions']}/20 phiên tăng.",
        f"GTGD bình quân 5 phiên {fmt.bn(rc[5]['tv_avg'], 0, False)}/phiên, bằng {fmt.num((rc.get('tv_ratio') or np.nan) * 100, 0)}% "
        f"mức bình quân 20 phiên trước đó ({fmt.bn(rc[20]['tv_avg'], 0, False)}/phiên)."], 8.4)


# ── 3. Độ rộng và độ vênh ────────────────────────────────────────────────────
def ch_breadth(pdf: FFRPdf, ctx: Dict, sub: bool = False) -> None:
    x, h = ctx["day"], ctx["hist"]
    _head(pdf, sub, "Độ rộng và độ vênh thị trường",
           "Chỉ số tăng/giảm có đi cùng số đông cổ phiếu không: tỷ lệ mã tăng, độ vênh D = %VN-Index − % cổ phiếu trung vị.")
    pdf.figure(charts.breadth_today(x))
    pdf.figures_row([charts.breadth_history(h), charts.divergence_chart(h)])
    s = ctx["stock"]
    v = s[s["is_valid"]]
    pm = ctx.get("pct_above_ma20")
    pdf.cards([("Mã trên MA20", fmt.num(pm, 0, False, "%"), f"{len(v)} mã hợp lệ", _clr((pm or 50) - 50)),
               ("Vượt đỉnh 20 phiên", str(int(v["new_high20"].sum())) if "new_high20" in v else "—", "số mã", None),
               ("Thủng đáy 20 phiên", str(int(v["new_low20"].sum())) if "new_low20" in v else "—", "số mã", None),
               ("Loại phiên", session_type_label(x["session_type"]), f"AD = {fmt.num(x['AD'], 2, True)} · IQR {fmt.num(x['IQR_pct'], 1)}%", None)])
    rc = ctx["recap"][20]
    types = sorted(rc["types"].items(), key=lambda kv: -kv[1])
    pdf.bullets([
        f"Độ vênh D phiên này {fmt.num(x['D'], 2, True)} điểm %, cao hơn {fmt.num(x['D_pct250'], 0)}% số phiên trong 250 phiên trước; "
        f"bình quân 20 phiên {fmt.num(rc['D_avg'], 2, True)} điểm %.",
        f"Bình quân 20 phiên: {fmt.num(rc['pct_up_avg'], 0)}% số mã tăng mỗi phiên; cơ cấu loại phiên: "
        + ", ".join(f"{session_type_label(k)} {n}" for k, n in types) + "."], 8.4)


# ── 4. Mã dẫn dắt ────────────────────────────────────────────────────────────
def ch_leaders(pdf: FFRPdf, ctx: Dict, sub: bool = False) -> None:
    x, lead = ctx["day"], ctx["leaders"]
    _head(pdf, sub, "Cổ phiếu dẫn dắt chỉ số",
           f"Đóng góp điểm C = I(t−1) · tỷ trọng vốn hóa · lợi suất. ΔVN-Index phiên = {fmt.num(x['dI'], 2, True)} điểm; "
           f"sai số tái lập ε = {fmt.num(x['eps'], 2, True)} điểm.")
    both = pd.concat([lead[lead["side"] == "pos"].head(6), lead[lead["side"] == "neg"].head(6)]).sort_values("C", ascending=False)
    rest = float(x["sumC"] - both["C"].sum()) if "sumC" in x else 0.0
    b1 = charts.hbar(both["symbol"].tolist() + ["Còn lại"], both["C"].tolist() + [rest], "Đóng góp điểm phiên này",
                     total=("ΔVN-Index", float(x["dI"])), size=(3.7, 3.4))
    l20 = ctx["lead20"].sort_values("C", ascending=False)
    b2 = charts.hbar(l20["symbol"].tolist(), l20["C"].tolist(), "Đóng góp lũy kế 20 phiên (ΣC)", dec=1, size=(3.7, 3.4))
    pdf.figures_row([b1, b2])
    g = ctx["groups"]
    fam = g[g["group_type"] == "family"].sort_values("C", ascending=False)
    if not fam.empty:
        pdf.h2("Họ cổ phiếu – đóng góp và chỉ số khi loại trừ họ")
        pdf.table(["Họ cổ phiếu", "Số mã", "Đóng góp (điểm)", "VN-Index loại trừ họ", "VN-Index thực tế", "Chênh lệch (đ.%)"],
                  [[r.group_name, str(int(r.n)), fmt.num(r.C, 2, True), fmt.pct(r.index_ex_group_ret_pct), fmt.pct(x["r_vni_pct"]),
                    fmt.num(x["r_vni_pct"] - r.index_ex_group_ret_pct, 2, True)] for r in fam.itertuples()],
                  [40, 18, 30, 34, 30, 30])


# ── 5. Ngành ─────────────────────────────────────────────────────────────────
def ch_sectors(pdf: FFRPdf, ctx: Dict, n_movers: int = 3, sub: bool = False) -> None:
    _head(pdf, sub, "Ngành và cổ phiếu nổi bật", "Lợi suất ngành tính theo vốn hóa; bản đồ nhiệt các mã có giá trị giao dịch lớn nhất.")
    pdf.figure(charts.sector_compare(ctx["sec1"], ctx["sec20"]))
    pdf.figure(charts.treemap(ctx["stock"]))
    s1 = ctx["sec1"].set_index("sector")["ret_pct"]
    s5 = ctx["sec5"].set_index("sector")["ret_pct"]
    s20 = ctx["sec20"].set_index("sector")
    order = s20.sort_values("ret_pct", ascending=False)
    rows = [[sec, fmt.pct(s1.get(sec), 1), fmt.pct(s5.get(sec), 1), fmt.pct(r.ret_pct, 1), f"{i}/{len(order)}", fmt.bn(r.net_flow)]
            for i, (sec, r) in enumerate(order.iterrows(), 1)]
    pdf.h2("Bảng lợi suất ngành và khối ngoại", keep=min(16 + 5.2 * len(rows), pdf.room(full=True)))
    pdf.table(["Ngành", "1 phiên", "5 phiên", "20 phiên", "Hạng 20 phiên", "NN ròng 20 phiên"], rows,
              [62, 22, 22, 22, 26, 28], 7.2)
    v = ctx["stock"][ctx["stock"]["is_valid"]]
    min_tv = float(get("outlook.movers_min_tv_bn", 10)) * 1e9
    liq = v[v["tv"] >= min_tv]
    pick = [("Tăng mạnh nhất", liq.nlargest(n_movers, "ret")), ("Giảm mạnh nhất", liq.nsmallest(n_movers, "ret")),
            ("GTGD lớn nhất", v.nlargest(n_movers, "tv"))]
    if "vol_ratio" in v:
        pick.append(("KL ≥ 2× TB20", liq[liq["vol_ratio"] >= 2].nlargest(n_movers, "vol_ratio")))
    rows = []
    for lbl, df in pick:
        for i, r in enumerate(df.itertuples()):
            rows.append([lbl if i == 0 else "", r.symbol, fmt.price(r.close), fmt.pct(r.ret * 100), fmt.num(r.tv / 1e9, 1),
                         fmt.num(getattr(r, "vol_ratio", np.nan), 1, False, "×"), fmt.num(r.net_flow / 1e9, 1, True),
                         fmt.pct(getattr(r, "ret_20d", np.nan), 1)])
    pdf.h2(f"Cổ phiếu nổi bật phiên (lọc GTGD ≥ {fmt.num(min_tv / 1e9, 0)} tỷ đồng)")
    pdf.table(["Nhóm", "Mã", "Giá", "% phiên", "GTGD (tỷ)", "KL/TB20", "NN ròng (tỷ)", "% 20 phiên"], rows,
              [34, 16, 22, 20, 22, 20, 26, 22])


# ── 6. Khối ngoại ────────────────────────────────────────────────────────────
def ch_foreign(pdf: FFRPdf, ctx: Dict) -> None:
    x = ctx["day"]
    pdf.h1("Ra-đa khối ngoại", "Mua − bán của nhà đầu tư nước ngoài trên HOSE. Mua ròng khối nội = − bán ròng khối ngoại "
                                  "(không có số liệu tách riêng tổ chức/cá nhân trong nước).")
    if pd.isna(x["NF_total"]):
        pdf.para("SSI chưa công bố số liệu khối ngoại cho phiên này.")
    pdf.figure(charts.foreign_flow(ctx["hist"]))
    top = pd.concat([ctx["top_buy"][ctx["top_buy"]["net_flow"] > 0], ctx["top_sell"][ctx["top_sell"]["net_flow"] < 0]])
    top = top.sort_values("net_flow", ascending=False)
    g = ctx["groups"]
    uni = g[g["group_type"] == "universe"]
    lbl = {"FTSE": "Nhóm FTSE", "CONTROL": "Đối chứng", "VN30": "VN30"}
    has_nf = uni["net_flow"].notna().any() if not uni.empty else False
    # Phiên SSI không công bố khối ngoại: không vẽ biểu đồ rỗng
    b1 = charts.hbar(top["symbol"].tolist(), (top["net_flow"] / 1e9).tolist(), "Top mua/bán ròng phiên (tỷ đồng)", dec=0,
                     size=(3.7, 3.0)) if not top.empty else None
    b2 = charts.hbar([lbl.get(n, n) for n in uni["group_name"]], (uni["net_flow"].fillna(0) / 1e9).tolist(),
                     "Ròng theo nhóm cổ phiếu phiên này (tỷ)", dec=0, size=(3.7, 3.0)) if has_nf else None
    figs = [b for b in (b1, b2) if b is not None]
    if figs:
        pdf.figures_row(figs)
    rows = [["Mua (tỷ)", fmt.bn(x["FB_total"], 0, False)], ["Bán (tỷ)", fmt.bn(x["FS_total"], 0, False)],
            ["Ròng (tỷ)", fmt.bn(x["NF_total"])], ["Tham gia / GTGD (FPR)", fmt.frac_pct(x["FPR_total"], 1)],
            ["Độ tập trung HHI", fmt.num(x["HHI"], 3)], ["z-score 60 phiên", fmt.num(x["z_NF_total"], 2, True)],
            ["Chuỗi phiên cùng chiều", fmt.num(x["streak_total"], 0, True)]]
    rc = ctx["recap"]
    rows += [["Lũy kế 5 phiên", f"{fmt.bn(rc[5]['nf_cum'])} ({rc[5]['nf_buy_days']}/5 phiên mua ròng)"],
             ["Lũy kế 20 phiên", f"{fmt.bn(rc[20]['nf_cum'])} ({rc[20]['nf_buy_days']}/20 phiên mua ròng)"]]
    pdf.h2("Chỉ số dòng vốn ngoại")
    pdf.table(["Chỉ tiêu", "Giá trị"], rows, [70, 112], aligns=["L", "L"])
    if not uni.empty:
        pdf.table(["Nhóm", "Số mã", "NF", "nf = NF/GTGD", "FPR", "Trạng thái ngoại – nội"],
                  [[lbl.get(r.group_name, r.group_name), str(int(r.n)), fmt.bn(r.net_flow), fmt.num(r.nf, 3, True),
                    fmt.frac_pct(r.FPR, 1), ABSORB_LABELS.get(r.absorb_state, "")] for r in uni.itertuples()],
                  [32, 18, 30, 30, 24, 48])
    st = ctx["stock"][ctx["stock"]["is_valid"]]
    cnt = st["absorb_state"].value_counts()
    pdf.para("Phân loại theo mã (|nf| ≥ 5% và |giá| ≥ 0,5%): " + "; ".join(
        f"{ABSORB_LABELS[k]} {int(cnt.get(k, 0))} mã" for k in ABSORB_LABELS) + ".", 7.8)


# ── 7. Nhóm FTSE ─────────────────────────────────────────────────────────────
def ch_ftse(pdf: FFRPdf, ctx: Dict, with_h4: bool = False, db_path=None) -> None:
    pdf.h1("Sự kiện nâng hạng FTSE",
           "So sánh lợi suất đồng trọng số của rổ dự kiến vào FTSE với nhóm đối chứng có quy mô tương đương.")
    e1 = pd.Timestamp(get("periods.announce", "2025-10-08"))
    gh = ctx.get("groups_hist")
    if gh is not None and not gh.empty:
        pdf.figure(charts.groups_cum(gh, e1, _events(ctx)))
    rel = ctx["ftse_rel"]
    if rel:
        pdf.table(["Kỳ", "Nhóm FTSE", "Đối chứng", "VN30", "FTSE − đối chứng"],
                  [[lbl, fmt.pct(dd.get("FTSE"), 1), fmt.pct(dd.get("CONTROL"), 1), fmt.pct(dd.get("VN30"), 1),
                    fmt.num(dd.get("FTSE", np.nan) - dd.get("CONTROL", np.nan), 1, True, " đ.%")] for lbl, dd in rel.items()],
                  [50, 30, 30, 30, 42])
    if with_h4:
        _h4_table(pdf, ctx, db_path)


def _h4_table(pdf: FFRPdf, ctx: Dict, db_path=None) -> None:
    from src.analytics.stats_tests import period_summary
    ps = period_summary(ctx["hist"])
    if ps.empty:
        return
    pdf.h2("Cấu trúc thị trường qua ba giai đoạn (kiểm định H4)")
    st = db.query_df("SELECT metric, \"window\", p_value, p_holm FROM stats_results WHERE hypothesis = 'H4' "
                     "AND test LIKE 'OLS%'", path=db_path) if db.table_exists("stats_results", db_path) else pd.DataFrame()
    pv = {(r.metric, r.window): r.p_holm for r in st.itertuples()} if not st.empty else {}
    piv = ps.pivot(index="metric", columns="period", values="mean")
    nper = ps.groupby("period")["n"].max()
    rows = [[m, fmt.num(piv.loc[m].get("Cơ sở trước E1"), 3), fmt.num(piv.loc[m].get("E1 → hiệu lực"), 3),
             _p(pv.get((m, "E1 → hiệu lực"))), fmt.num(piv.loc[m].get("Sau hiệu lực"), 3), _p(pv.get((m, "Sau hiệu lực")))]
            for m in ps["metric"].unique()]
    pdf.table(["Chỉ báo (trung bình ngày)", f"Cơ sở ({int(nper.get('Cơ sở trước E1', 0))} ph.)",
               f"E1→HL ({int(nper.get('E1 → hiệu lực', 0))} ph.)", "p Holm", f"Sau HL ({int(nper.get('Sau hiệu lực', 0))} ph.)",
               "p Holm"], rows, [60, 25, 25, 18, 26, 18], 7.2)
    pdf.para("Hồi quy chỉ báo ngày lên giả biến giai đoạn, sai số Newey–West 5 trễ; cơ sở = 250 phiên trước công bố E1. "
             "p Holm < 0,05: khác biệt có ý nghĩa thống kê sau hiệu chỉnh nhiều kiểm định. Giai đoạn sau hiệu lực còn ngắn và "
             "trùng các biến động vĩ mô, nên kết quả không chứng minh quan hệ nhân quả.", 7.4, "I")


# ── 8. Triển vọng thống kê ───────────────────────────────────────────────────
def ch_outlook(pdf: FFRPdf, ctx: Dict, sub: bool = False) -> None:
    _head(pdf, sub, "Biên dao động thống kê", "Ước lượng từ dữ liệu quá khứ, có kiểm chứng ngoài mẫu – mô tả khả năng, không phải dự báo "
                                     "điểm và không phải khuyến nghị đầu tư.")
    vr, an = ctx["vol_range"], ctx["analog"]
    if vr:
        pdf.figure(charts.outlook_fan(ctx["idx_hist"]["VN-Index"], vr))
    rows = []
    for hz in sorted(vr):
        r = vr[hz]
        a = an.get("horizons", {}).get(hz) if an.get("available") else None
        rows.append([f"{hz} phiên tới", f"{fmt.num(r['lo68'], 0)} – {fmt.num(r['hi68'], 0)}",
                     f"{fmt.num(r['lo90'], 0)} – {fmt.num(r['hi90'], 0)}",
                     fmt.frac_pct(a["p_up"], 0) if a and a["n"] else "—", fmt.frac_pct(a["base_p_up"], 0) if a and a["n"] else "—",
                     str(a["n"]) if a else "—"])
    if rows:
        pdf.table(["Kỳ", "Biên 68%", "Biên 90%", "Tỷ lệ cao hơn (trạng thái tương tự)", "Tỷ lệ mọi phiên", "Số phiên mẫu"], rows,
                  [24, 30, 30, 46, 28, 24])
    pdf.bullets(ctx["outlook_text"][:-1], 8.2)
    pdf.para("Phương pháp: độ lệch chuẩn ngày theo EWMA (λ = 0,94) trên log-lợi suất; biên = I·exp(±k·σ·√h), k = phân vị 68% / 90% "
             "thực nghiệm của sai số dự báo quá khứ (hiệu chỉnh đuôi dày, không nhìn trước). Trạng thái tương tự = cùng vị trí so với MA50, cùng dấu lợi suất 20 phiên và cùng dấu khối ngoại ròng "
             "20 phiên.", 7.4, "I")


# ── 9. Danh mục theo dõi ─────────────────────────────────────────────────────
def ch_watch(pdf: FFRPdf, ctx: Dict, full: bool = False) -> None:
    pf = ctx["watch"]
    pdf.h1("Watchlist Impact – danh mục theo dõi", "Phản ứng của các mã trong watchlist so với thị trường: lợi suất vượt trội, đóng góp điểm, khối ngoại.")
    if pf is None or pf.empty:
        pdf.para("Danh mục trống.")
        return
    wl = ctx.get("wl_hist")
    if wl is not None and not wl.empty:
        pdf.figure(charts.watch_perf(wl, ctx["idx_hist"]["VN-Index"], list(ctx.get("watch_symbols") or [])))
    rows = []
    for r in pf.itertuples():
        if not r.has_data:
            rows.append([r.symbol] + ["—"] * (8 if full else 6))
            continue
        base = [r.symbol, fmt.price(r.close), fmt.pct(r.ret * 100), fmt.num(r.ER_M * 100, 2, True),
                fmt.num(r.C, 2, True) if r.C is not None else "—", fmt.bn(r.net_flow, 1), ABSORB_LABELS.get(r.absorb_state, "")]
        if full:
            base += [fmt.num(r.pct60_nf, 0), fmt.num(r.beta_dimson, 2)]
        rows.append(base)
    heads = ["Mã", "Giá", "%", "Vượt TT (đ.%)", "Đóng góp", "NN ròng", "Ngoại – nội"] + (["Phân vị nf", "β Dimson"] if full else [])
    widths = ([14, 18, 17, 22, 18, 22, 33, 19, 19] if full else [16, 22, 20, 26, 22, 28, 48])
    pdf.table(heads, rows, widths)
    pdf.bullets([r.sentence for r in pf.itertuples()], 8.2)


# ── Chương gộp theo tab của ứng dụng ─────────────────────────────────────────
def ch_overview(pdf: FFRPdf, ctx: Dict) -> None:
    pdf.h1("Tổng quan thị trường", "Chỉ số, thanh khoản, ngành, bản đồ nhiệt và cổ phiếu nổi bật – tương ứng trang "
                                   "Tổng quan thị trường của ứng dụng.")
    ch_index(pdf, ctx, sub=True)
    ch_sectors(pdf, ctx, sub=True)


def ch_lead_div(pdf: FFRPdf, ctx: Dict) -> None:
    pdf.h1("Dẫn dắt & độ vênh", "Ai đang kéo VN-Index và chỉ số có phản ánh số đông cổ phiếu không – tương ứng trang "
                                "Dẫn dắt & độ vênh của ứng dụng.")
    ch_leaders(pdf, ctx, sub=True)
    ch_breadth(pdf, ctx, sub=True)
