"""
Các trang báo cáo dùng chung cho Snapshot và Closing: tóm tắt điều hành, tổng quan thị trường (cùng khối với trang 1
dashboard), diễn biến tuần/tháng, triển vọng thống kê, bối cảnh nâng hạng FTSE (H4). Số liệu lấy từ context.build().
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from src.common import fmt
from src.data import database as db
from src.reports.pdf_base import FFRPdf

PERIOD_KEYS = ["1T", "1Th", "3Th", "6Th", "YTD", "1N"]


def _clr(v) -> Optional[str]:
    return None if v is None or pd.isna(v) else "up" if v > 0 else "down" if v < 0 else "ref"


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else "<0,001" if v < 0.001 else fmt.num(v, 3)


def _short(detail: str) -> str:
    """Rút gọn mô tả thành phần sức khỏe cho thẻ hẹp (▲MA20 → >MA20)."""
    return detail.replace("▲MA", ">MA").replace("▼MA", "<MA")


def page_summary(pdf: FFRPdf, ctx: Dict, months: int = 14) -> None:
    """Trang 1: tóm tắt điều hành + 4 chỉ số (kèm hiệu suất kỳ) + diễn biến VN-Index."""
    d = ctx["date"]
    pdf.h2(f"Tóm tắt điều hành · phiên {d:%d/%m/%Y}")
    rc = ctx["recap_text"]
    items = [ctx["summary"]] + rc[:1] + [rc[4] if len(rc) > 4 else ctx["foreign"]]
    out = ctx["outlook_text"]
    items += [s for s in out[:2]]
    pdf.bullets(items, 8.6)
    idx = ctx["index"].set_index("index_code")
    cards = []
    for code, name in (("VNINDEX", "VN-Index"), ("VN30", "VN30"), ("HNXINDEX", "HNX-Index"), ("UPCOMINDEX", "UPCoM-Index")):
        r = ctx["idx_ret"].get(name, {})
        if code in idx.index:
            cards.append((name, fmt.num(idx.loc[code, "value"]),
                          f"{fmt.pct(idx.loc[code, 'ratio_change'])} · 1Th {fmt.pct(r.get('1Th'), 1)} · YTD {fmt.pct(r.get('YTD'), 1)}",
                          _clr(idx.loc[code, "change"])))
        else:
            cards.append((name, "—", "không có dữ liệu phiên", None))
    pdf.cards(cards)
    vni = ctx["idx_hist"]["VN-Index"]
    view0 = d - pd.Timedelta(days=int(months * 30.5))
    full = vni[vni.index >= view0 - pd.Timedelta(days=90)]
    ser = {"VN-Index": vni[vni.index >= view0], "MA20": full.rolling(20).mean()[lambda s: s.index >= view0],
           "MA50": full.rolling(50).mean()[lambda s: s.index >= view0]}
    ev = ctx.get("events")
    marks = [(r.event_date, r.event_id) for r in ev.itertuples()] if ev is not None and not ev.empty else None
    pdf.line_chart(ser, 78, marks, title=f"VN-Index {months} tháng · MA20 · MA50 · mốc FTSE: E1 công bố 08/10/2025, "
                                          "E2 xác nhận 08/04/2026, E3 18/09/2026")


def page_overview(pdf: FFRPdf, ctx: Dict, n_movers: int = 3) -> None:
    """Tổng quan thị trường: sức khỏe, độ rộng mở rộng, hiệu suất chỉ số, ngành, cổ phiếu nổi bật."""
    x, h = ctx["day"], ctx["health"]
    pdf.h2("Sức khỏe thị trường (thang 0–100, theo quy tắc)")
    if h.get("available"):
        pdf.cards([("Điểm sức khỏe", fmt.num(h["score"], 0), h["label"],
                    "up" if h["score"] >= 70 else "ref" if h["score"] >= 40 else "down")] +
                  [(f"{v['label']} · {v['weight']}%", fmt.num(v["score"], 0), _short(v["detail"]), _clr(v["score"] - 50))
                   for v in list(h["components"].values())[:3]], per_row=4)
        rest = list(h["components"].values())[3:]
        if rest:
            pdf.para(" · ".join(f"{v['label']} ({v['weight']}%): {fmt.num(v['score'], 0)} – {v['detail']}" for v in rest), 8)
    else:
        pdf.para("Chưa đủ dữ liệu để chấm điểm.")
    s = ctx["stock"]
    v = s[s["is_valid"]]
    pdf.h2("Độ rộng mở rộng · HOSE")
    pdf.cards([("Mã trên MA20", fmt.num(ctx.get("pct_above_ma20"), 0, False, "%"), f"{len(v)} mã hợp lệ",
                _clr((ctx.get("pct_above_ma20") or 50) - 50)),
               ("Vượt đỉnh 20 phiên", str(int(v["new_high20"].sum())) if "new_high20" in v else "—", "mã", "up"),
               ("Thủng đáy 20 phiên", str(int(v["new_low20"].sum())) if "new_low20" in v else "—", "mã", "down"),
               ("GTGD khớp", fmt.bn(x["tv_total"], 0, False), f"5 phiên = {fmt.num((ctx['recap'].get('tv_ratio') or np.nan) * 100, 0)}% "
                                                          "mức 20 phiên trước", None)])
    pdf.h2("Hiệu suất chỉ số theo kỳ")
    rows = [[name] + [fmt.pct(r.get(k), 1) for k in PERIOD_KEYS] for name, r in ctx["idx_ret"].items()]
    pdf.table(["Chỉ số"] + ["1 tuần", "1 tháng", "3 tháng", "6 tháng", "Từ đầu năm", "1 năm"], rows,
              [40, 23, 23, 23, 23, 26, 24])
    pdf.h2("Ngành – lợi suất theo vốn hóa và khối ngoại ròng")
    s1 = ctx["sec1"].set_index("sector")["ret_pct"]
    s5 = ctx["sec5"].set_index("sector")["ret_pct"]
    s20 = ctx["sec20"].set_index("sector")
    order = s20.reindex(s20["ret_pct"].abs().sort_values(ascending=False).index).head(10).sort_values("ret_pct", ascending=False)
    rows = [[sec, fmt.pct(s1.get(sec), 1), fmt.pct(s5.get(sec), 1), fmt.pct(r.ret_pct, 1), fmt.bn(r.net_flow)]
            for sec, r in order.iterrows()]
    pdf.table(["Ngành (10 biến động mạnh nhất 20 phiên)", "1 phiên", "5 phiên", "20 phiên", "NN ròng 20 phiên"], rows,
              [66, 26, 26, 26, 38])
    from src.common.config import get
    min_tv = float(get("outlook.movers_min_tv_bn", 10)) * 1e9
    liq = v[v["tv"] >= min_tv]
    pdf.h2(f"Cổ phiếu nổi bật phiên (GTGD ≥ {fmt.num(min_tv / 1e9, 0)} tỷ)")
    pick = [("Tăng mạnh", liq.nlargest(n_movers, "ret")), ("Giảm mạnh", liq.nsmallest(n_movers, "ret")),
            ("GTGD lớn", v.nlargest(n_movers, "tv"))]
    if "vol_ratio" in v:
        pick.append(("Đột biến KL (≥2×)", liq[liq["vol_ratio"] >= 2].nlargest(n_movers, "vol_ratio")))
    rows = []
    for lbl, df in pick:
        for i, r in enumerate(df.itertuples()):
            rows.append([lbl if i == 0 else "", r.symbol, fmt.price(r.close), fmt.pct(r.ret * 100),
                         fmt.num(r.tv / 1e9, 1), fmt.num(getattr(r, "vol_ratio", np.nan), 1, False, "×"),
                         fmt.num(r.net_flow / 1e9, 1, True), fmt.pct(getattr(r, "ret_20d", np.nan), 1)])
    pdf.table(["Nhóm", "Mã", "Giá", "%", "GTGD (tỷ)", "KL/TB20", "NN ròng (tỷ)", "20 phiên"], rows,
              [34, 16, 22, 20, 22, 20, 26, 22])


def page_recap(pdf: FFRPdf, ctx: Dict) -> None:
    """Diễn biến 5 và 20 phiên: tóm tắt, dẫn dắt lũy kế, nhóm FTSE và đối chứng."""
    pdf.h2("Diễn biến tuần và tháng")
    pdf.bullets(ctx["recap_text"], 8.6)
    lead = ctx["lead20"]
    if not lead.empty:
        pdf.h2("Mã dẫn dắt lũy kế 20 phiên (ΣC, điểm VN-Index)")
        both = pd.concat([lead[lead["C"] > 0].nlargest(5, "C"), lead[lead["C"] < 0].nsmallest(5, "C")]).sort_values("C", ascending=False)
        pdf.hbars(both["symbol"].tolist(), both["C"].tolist(), fmt_fn=lambda v: fmt.num(v, 1, True))
    rel = ctx["ftse_rel"]
    if rel:
        pdf.h2("Nhóm FTSE và nhóm đối chứng (lợi suất đồng trọng số lũy kế)")
        rows = [[lbl, fmt.pct(dd.get("FTSE"), 1), fmt.pct(dd.get("CONTROL"), 1), fmt.pct(dd.get("VN30"), 1),
                 fmt.num((dd.get("FTSE", np.nan) - dd.get("CONTROL", np.nan)), 1, True, " đ.%")] for lbl, dd in rel.items()]
        pdf.table(["Kỳ", "Nhóm FTSE", "Đối chứng", "VN30", "FTSE − đối chứng"], rows, [50, 30, 30, 30, 42])


def page_outlook(pdf: FFRPdf, ctx: Dict) -> None:
    """Triển vọng thống kê: biên dao động EWMA, xác suất theo trạng thái tương tự, tín hiệu hôm nay."""
    pdf.h2("Triển vọng thống kê (không phải khuyến nghị)")
    vr, an = ctx["vol_range"], ctx["analog"]
    cards = []
    for hz in (5, 20):
        r = vr.get(hz)
        if r:
            cards.append((f"Biên 90% · {hz} phiên", f"{fmt.num(r['lo90'], 0)}–{fmt.num(r['hi90'], 0)}",
                          f"biên 68%: {fmt.num(r['lo68'], 0)}–{fmt.num(r['hi68'], 0)}", None))
    if an.get("available"):
        for hz in (5, 20):
            r = an["horizons"].get(hz)
            if r and r["n"]:
                cards.append((f"Xác suất tăng · {hz} phiên", fmt.frac_pct(r["p_up"], 0),
                              f"{r['n']} phiên tương tự · nền {fmt.frac_pct(r['base_p_up'], 0)}",
                              _clr(r["p_up"] - r["base_p_up"])))
    if cards:
        pdf.cards(cards[:4])
    pdf.bullets(ctx["outlook_text"], 8.6)
    pdf.para("Phương pháp: σ theo EWMA λ = 0,94 (RiskMetrics) trên log-lợi suất VN-Index; biên = I·exp(±z·σ·√h), "
             "z = 1 (68%) và 1,645 (90%); bao phủ thực tế được kiểm chứng ngoài mẫu từ 2019. Trạng thái tương tự = cùng vị trí so với "
             "MA50, cùng dấu lợi suất 20 phiên và cùng dấu khối ngoại ròng 20 phiên; chỉ tính các phiên đã có đủ h phiên sau đó. "
             "Cửa sổ chồng lấp và phân phối thay đổi theo thời gian nên đây là mô tả, không phải dự báo điểm.", 7.6, "I")


def page_phase(pdf: FFRPdf, ctx: Dict, db_path=None) -> None:
    """Bối cảnh nâng hạng: chỉ báo trung bình ba giai đoạn + kiểm định H4 (stats_results)."""
    from src.analytics.stats_tests import period_summary
    ps = period_summary(ctx["hist"])
    if ps.empty:
        return
    pdf.h2("Bối cảnh nâng hạng FTSE – so sánh ba giai đoạn (H4)")
    st = db.query_df("SELECT metric, \"window\", p_value, p_holm FROM stats_results WHERE hypothesis = 'H4' "
                     "AND test LIKE 'OLS%'", path=db_path) if db.table_exists("stats_results", db_path) else pd.DataFrame()
    pv = {(r.metric, r.window): r.p_holm for r in st.itertuples()} if not st.empty else {}
    piv = ps.pivot(index="metric", columns="period", values="mean")
    nper = ps.groupby("period")["n"].max()
    rows = []
    for m in ps["metric"].unique():
        rows.append([m, fmt.num(piv.loc[m].get("Cơ sở trước E1"), 3),
                     fmt.num(piv.loc[m].get("E1 → hiệu lực"), 3), _p(pv.get((m, "E1 → hiệu lực"))),
                     fmt.num(piv.loc[m].get("Sau hiệu lực"), 3), _p(pv.get((m, "Sau hiệu lực")))])
    pdf.table(["Chỉ báo (trung bình ngày)", f"Cơ sở ({int(nper.get('Cơ sở trước E1', 0))} ph.)",
               f"E1→HL ({int(nper.get('E1 → hiệu lực', 0))} ph.)", "p Holm", f"Sau HL ({int(nper.get('Sau hiệu lực', 0))} ph.)",
               "p Holm"], rows, [60, 25, 25, 18, 26, 18], 7.2)
    pdf.para("Hồi quy chỉ báo ngày lên giả biến giai đoạn, sai số Newey–West 5 trễ; cơ sở = 250 phiên ngay trước công bố E1 "
             "(08/10/2025). Giai đoạn sau hiệu lực (từ 21/09/2026) còn ngắn → công suất thấp, kết quả sơ bộ; thay đổi trùng "
             "biến động vĩ mô nên KHÔNG khẳng định nhân quả.", 7.6, "I")
