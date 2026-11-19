"""
Các chương báo cáo PDF theo bố cục phân tích (thay bố cục sao chép các trang web):

  Bìa (+ kết luận phiên) → Trang 2: mục lục + tóm tắt điều hành (3 câu trả lời) →
  1. Chẩn đoán phiên (5 bước: lan tỏa → mã dẫn dắt → khối ngoại có đứng sau không → phản ứng giá → watchlist)
  2. Dòng vốn ngoại · 3. Bối cảnh FTSE (danh sách chính thức 21/08/2026, H4 có kiểm soát, hồi quy gộp D)
  4. Tác động lên watchlist · 5. Kết luận và hàm ý · 6. Thị trường chung (1 trang) · Phụ lục

Mỗi chương mở đầu bằng một câu kết luận in đậm sinh từ số liệu. Không chấm điểm khuyến nghị, không dùng xác suất
“trạng thái tương tự” (chênh lệch nhỏ, cửa sổ chồng lấp).
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from src.analytics import diagnosis as dg
from src.common import fmt
from src.common.config import get
from src.data import database as db
from src.finance.breadth import session_type_label
from src.finance.domestic import ABSORB_LABELS
from src.reports import charts
from src.reports.pdf_base import FFRPdf
from src.reports.sections import PERIOD_KEYS, _events, _p, key_table


def _stats(db_path=None) -> pd.DataFrame:
    return db.query_df("SELECT * FROM stats_results", path=db_path) if db.table_exists("stats_results", db_path) else pd.DataFrame()


def session_conclusion(ctx: Dict) -> str:
    """Một câu kết luận phiên (dùng cho bìa và chương 5)."""
    x, et, lead = ctx["day"], ctx.get("ex_today", pd.Series(dtype=float)), ctx["leaders"]
    main = lead[lead["side"] == ("neg" if x["dI"] < 0 else "pos")].head(2)
    return (f"Phiên {session_type_label(x['session_type']).lower()}: năm mã tạo {fmt.frac_pct(x['CR5'], 0)} biến động, dẫn đầu "
            f"{', '.join(main['symbol'])}; {fmt.frac_pct(et.get('codir'), 0)} biến động điểm đến từ các mã khối ngoại giao dịch cùng chiều.")


# ── 1. Chẩn đoán phiên ────────────────────────────────────────────────────────
def ch_diagnosis(pdf: FFRPdf, ctx: Dict) -> None:
    x, et, lead = ctx["day"], ctx["ex_today"], ctx["leaders"]
    v = ctx["stock"][ctx["stock"]["is_valid"]]
    g = ctx["groups"]
    vin = g[(g["group_type"] == "family") & (g["group_name"] == "VINGROUP")]
    pdf.h1("Chẩn đoán phiên", "Chuỗi 5 bước: lan tỏa → ai tạo biến động → khối ngoại có đứng sau không → phản ứng giá → watchlist.",
           concl=ctx["answers"][0]["a"] if ctx.get("answers") else "")
    main = lead[lead["side"] == ("neg" if x["dI"] < 0 else "pos")].head(3)
    rho = v[["C", "net_flow"]].dropna().corr(method="spearman").iloc[0, 1] if len(v) > 10 else np.nan
    top10 = v[v["symbol"].isin(lead["symbol"])]
    stc = top10["absorb_state"].value_counts()
    steps = [
        f"1 · Lan tỏa: D = {fmt.num(x['D'], 2, True)} điểm % (phân vị {fmt.num(x['D_pct250'], 0)}% của 250 phiên), loại phiên "
        f"{session_type_label(x['session_type']).lower()}, {fmt.num(x['pct_up'], 0)}% số mã tăng.",
        f"2 · Ai tạo biến động: CR5 = {fmt.frac_pct(x['CR5'], 0)}; dẫn đầu {', '.join(main['symbol'])} "
        f"({fmt.num(main['C'].sum(), 2, True)} điểm). Nếu bỏ họ Vingroup, VN-Index "
        f"{fmt.pct(vin['index_ex_group_ret_pct'].iloc[0]) if not vin.empty else '—'} (thực tế {fmt.pct(x['r_vni_pct'])}).",
        f"3 · Khối ngoại có đứng sau không: {fmt.frac_pct(et.get('codir'), 0)} biến động điểm đến từ mã có khối ngoại cùng chiều; "
        f"tương quan hạng ρ(C, NF) = {fmt.num(rho, 2, True)}; NN ròng {fmt.bn(x['NF_total'])}.",
        "4 · Phản ứng giá ở 10 mã dẫn dắt: " + "; ".join(f"{ABSORB_LABELS[k].lower()} {int(n)}" for k, n in stc.items() if k != "neutral")
        + (f"; {int(stc.get('neutral', 0))} mã biến động nhỏ." if stc.get("neutral") else "."),
        (ctx["answers"][2]["a"] if len(ctx.get("answers", [])) > 2 else "5 · Watchlist: danh mục trống."),
    ]
    steps[4] = "5 · Watchlist: " + steps[4] if not steps[4].startswith("5 ·") else steps[4]
    pdf.callout("Năm bước chẩn đoán", steps)
    both = pd.concat([lead[lead["side"] == "pos"].head(6), lead[lead["side"] == "neg"].head(6)]).sort_values("C", ascending=False)
    rest = float(x["sumC"] - both["C"].sum()) if "sumC" in x else 0.0
    b1 = charts.hbar(both["symbol"].tolist() + ["Còn lại"], both["C"].tolist() + [rest], "Đóng góp điểm phiên này",
                     total=("ΔVN-Index", float(x["dI"])), size=(3.7, 3.2))
    pdf.figures_row([b1, charts.codir_chart(ctx["extras"])])
    tot = v["C"].abs().sum() or 1
    top = v.reindex(v["C"].abs().sort_values(ascending=False).index).head(10)
    nf = top["net_flow"].fillna(0)
    same = (np.sign(nf) == np.sign(top["C"])) & (nf != 0)
    pdf.h2("Bảng đóng góp điểm – cột khối ngoại cùng chiều nối sang chương 2")
    pdf.table(["Mã", "Ngành", "% giá", "Đóng góp (điểm)", "% tổng |C|", "NN ròng (tỷ)", "Ngoại cùng chiều"],
              [[r.symbol, str(r.sector)[:22], fmt.pct(r.ret * 100), fmt.num(r.C, 2, True), fmt.num(abs(r.C) / tot * 100, 1, False, "%"),
                fmt.num(r.net_flow / 1e9, 1, True), "có" if s else "không"] for r, s in zip(top.itertuples(), same)],
              [16, 46, 20, 28, 22, 26, 24], aligns=["L", "L", "R", "R", "R", "R", "L"])
    pdf.h2("Bảng chỉ tiêu chính so với lịch sử gần")
    pdf.table(["Chỉ tiêu", "Phiên này", "Phiên trước", "TB 5 phiên", "TB 20 phiên", "Phân vị 250 ph."], key_table(ctx),
              [58, 24, 24, 24, 26, 26])
    pdf.figures_row([charts.breadth_history(ctx["hist"]), charts.divergence_chart(ctx["hist"])])


# ── 2. Dòng vốn ngoại ────────────────────────────────────────────────────────
def ch_flow(pdf: FFRPdf, ctx: Dict) -> None:
    x, rc = ctx["day"], ctx["recap"]
    concl = ("SSI chưa công bố số liệu khối ngoại phiên này." if pd.isna(x["NF_total"]) else
             f"Khối ngoại {'mua' if x['NF_total'] > 0 else 'bán'} ròng {fmt.bn(abs(x['NF_total']), 0, False)} trên HOSE "
             f"(z60 = {fmt.num(x['z_NF_total'], 2, True)}); lũy kế 20 phiên {fmt.bn(rc[20]['nf_cum'])} với "
             f"{rc[20]['nf_buy_days']}/20 phiên mua ròng.")
    pdf.h1("Dòng vốn ngoại", "Mua − bán của nhà đầu tư nước ngoài trên HOSE; ròng khối nội = − ròng khối ngoại.", concl=concl)
    hhi_n = 1 / x["HHI"] if x["HHI"] else np.nan
    pdf.cards([("Ròng phiên", fmt.bn(x["NF_total"], 0), f"mua {fmt.bn(x['FB_total'], 0, False)} · bán {fmt.bn(x['FS_total'], 0, False)}",
                "up" if (x["NF_total"] or 0) > 0 else "down"),
               ("Lũy kế 5 / 20 phiên", fmt.bn(rc[5]["nf_cum"], 0), f"20 phiên {fmt.bn(rc[20]['nf_cum'], 0)}", None),
               ("Tham gia / GTGD (FPR)", fmt.frac_pct(x["FPR_total"], 1), "phần còn lại thuộc khối nội", None),
               ("Tập trung HHI", fmt.num(x["HHI"], 3), f"≈ trải đều trên {fmt.num(hhi_n, 0)} mã", None)])
    pdf.figure(charts.foreign_flow(ctx["hist"]))
    top = pd.concat([ctx["top_buy"][ctx["top_buy"]["net_flow"] > 0], ctx["top_sell"][ctx["top_sell"]["net_flow"] < 0]])
    top = top.sort_values("net_flow", ascending=False)
    g = ctx["groups"]
    uni = g[g["group_type"] == "universe"]
    lbl = {"FTSE": "Nhóm FTSE", "CONTROL": "Đối chứng", "VN30": "VN30"}
    figs = []
    if not top.empty:
        figs.append(charts.hbar(top["symbol"].tolist(), (top["net_flow"] / 1e9).tolist(), "Top mua/bán ròng phiên (tỷ đồng)", dec=0,
                                size=(3.7, 3.0)))
    if not uni.empty and uni["net_flow"].notna().any():
        figs.append(charts.hbar([lbl.get(n, n) for n in uni["group_name"]], (uni["net_flow"].fillna(0) / 1e9).tolist(),
                                "Ròng theo nhóm phiên này (tỷ)", dec=0, size=(3.7, 3.0)))
    if figs:
        pdf.figures_row(figs)
    if not uni.empty:
        pdf.table(["Nhóm", "Số mã", "NF", "nf = NF/GTGD", "FPR", "Chiều giá – ngoại"],
                  [[lbl.get(r.group_name, r.group_name), str(int(r.n)), fmt.bn(r.net_flow), fmt.num(r.nf, 3, True),
                    fmt.frac_pct(r.FPR, 1), ABSORB_LABELS.get(r.absorb_state, "")] for r in uni.itertuples()],
                  [32, 18, 30, 30, 24, 48])
    sec = g[g["group_type"] == "sector"].sort_values("net_flow")
    if not sec.empty:
        pick = pd.concat([sec.head(4), sec.tail(4)]).drop_duplicates("group_name").sort_values("net_flow", ascending=False)
        pdf.table(["Ngành (4 mua ròng và 4 bán ròng nhiều nhất)", "Ròng (tỷ)", "nf", "FPR"],
                  [[r.group_name, fmt.num(r.net_flow / 1e9, 1, True), fmt.num(r.nf, 3, True), fmt.frac_pct(r.FPR, 1)]
                   for r in pick.itertuples()], [86, 32, 32, 32])


# ── 3. Bối cảnh FTSE ─────────────────────────────────────────────────────────
def _caar_rows(sr: pd.DataFrame):
    rows = []
    for eid in ("L1", "E3"):
        for w in ("[-5;5]", "[0;20]"):
            x = sr[(sr["hypothesis"] == "H3a") & (sr["metric"] == "CAR") & (sr["event_id"] == eid) & (sr["window"] == w)
                   & (sr["variant"] == "base")]
            f = x[(x["group"] == "FTSE") & (x["test"] == "t cắt ngang")]
            c = x[(x["group"] == "CONTROL") & (x["test"] == "t cắt ngang")]
            d = x[(x["group"] == "FTSE−CONTROL") & x["test"].astype(str).str.startswith("Welch")]
            aw = x[(x["group"] == "FTSE_AW") & (x["test"] == "t cắt ngang")]
            if f.empty or c.empty:
                continue
            ph = d["p_holm"].iloc[0] if not d.empty and pd.notna(d["p_holm"].iloc[0]) else (d["p_value"].iloc[0] if not d.empty else np.nan)
            pct = lambda df: fmt.num(df["estimate"].iloc[0] * 100, 2, True) + "%" if not df.empty else "—"  # noqa: E731
            rows.append([f"{eid} {w}", pct(f), pct(c), pct(d), pct(aw), _p(ph),
                         "Khác biệt có ý nghĩa" if pd.notna(ph) and ph < 0.05 else "Không có bằng chứng bất thường"])
    return rows


def ch_ftse_context(pdf: FFRPdf, ctx: Dict, db_path=None) -> None:
    sr = _stats(db_path)
    rows = dg.research_rows(sr)
    if ctx.get("extras_full") is None:
        st_ = db.query_df("SELECT trade_date, symbol, is_valid, w, C, net_flow, tv FROM indicator_stock_daily WHERE trade_date <= ?",
                          [ctx["date"]], path=db_path)
        ctx["extras_full"] = dg.daily_extras(st_, ctx["hist"])
    reg = dg.d_regression(ctx["hist"], ctx["extras_full"])
    pdf.h1("Bối cảnh nâng hạng FTSE", "27 mã theo công bố chính thức của FTSE Russell ngày 21/08/2026 (6 mã vào All-World); "
                                       "mốc L1 21/08 · L2 04/09 · E3 18/09 · hiệu lực 21/09/2026.",
           concl=dg.main_conclusion(reg, rows))
    gh = ctx.get("groups_hist")
    e1 = pd.Timestamp(get("periods.announce", "2025-10-08"))
    figs = []
    if gh is not None and not gh.empty:
        pdf.figure(charts.groups_cum(gh, e1, _events(ctx)))
    figs.append(charts.ftse_contrib_chart(ctx["extras"]))
    cr = _caar_rows(sr)
    if cr:
        pdf.h2("Lợi suất bất thường quanh mốc công bố danh sách và phiên điều chỉnh rổ")
        pdf.table(["Mốc · cửa sổ", "Nhóm FTSE", "Đối chứng", "Chênh lệch", "6 mã All-World", "p Holm", "Kết luận"], cr,
                  [26, 22, 22, 22, 26, 18, 46], aligns=["L", "R", "R", "R", "R", "R", "L"])
    if rows:
        pdf.h2("Cấu trúc thị trường sau công bố (E1 → hiệu lực so với 250 phiên trước E1)")
        pdf.table(["Câu hỏi", "Thay đổi", "p Holm", "Mức bằng chứng"],
                  [[r["q"], fmt.num(r["est"], 3, True), _p(r["p"]), r["label"]] for r in rows], [98, 24, 22, 38],
                  aligns=["L", "R", "R", "L"])
    if reg.get("ok"):
        pdf.h2("Hồi quy gộp: độ vênh đến từ tập trung hay từ khối ngoại?")
        pdf.table(["Biến (chuẩn hóa z)", "Hệ số (đ.%)", "t", "p", "Mức bằng chứng"],
                  [[x["label"], fmt.num(x["coef"], 3, True), fmt.num(x["t"], 2, True), _p(x["p"]), dg.evidence_label(x["p"])]
                   for x in reg["rows"]], [76, 26, 18, 20, 42], aligns=["L", "R", "R", "R", "L"])
        pdf.para(f"D_t = a + b1·HHI tỷ trọng + b2·lợi suất 10 mã lớn + b3·nf 10 mã lớn + b4·|r VN-Index| + e_t; sai số HAC 5 trễ; "
                 f"{reg['n']} phiên từ {reg['from']:%d/%m/%Y}; R² = {fmt.num(reg['r2'], 2)}.", 7.6, "I")
    pdf.figures_row(figs + [charts.codir_chart(ctx["extras"], 120)])


# ── 4. Tác động lên watchlist ────────────────────────────────────────────────
def ch_watch_impact(pdf: FFRPdf, ctx: Dict) -> None:
    pf = ctx["watch"]
    syms = list(ctx.get("watch_symbols") or [])
    if pf is None or pf.empty:
        pdf.h1("Tác động lên watchlist", concl="Danh mục theo dõi trống.")
        return
    wl = ctx.get("wl_hist")
    e = dg.watch_exposure(syms, ctx["date"], pd.concat([wl, ctx["stock"]]).drop_duplicates(["trade_date", "symbol"]),
                          ctx["hist"], pf) if wl is not None else {}
    w = pf[pf["has_data"].astype(bool)] if "has_data" in pf else pf
    concl = (f"{int((w['ER_M'] > 0).sum())}/{len(w)} mã hơn trung vị thị trường hôm nay; {len(e.get('lead', []))}/{e.get('n', len(syms))} mã "
             f"nằm trong nhóm dẫn dắt; khi độ vênh cao, watchlist thua trung vị {fmt.frac_pct(e.get('lose_hiD'), 0)} số phiên.")
    pdf.h1("Tác động lên watchlist", "Mức phơi nhiễm với nhóm dẫn dắt và phản ứng so với thị trường (ERᴹ = r − trung vị).", concl=concl)
    pdf.cards([("Trong nhóm dẫn dắt", f"{len(e.get('lead', []))}/{e.get('n', 0)}", ", ".join(e.get("lead", [])) or "không mã nào", None),
               ("Họ Vingroup", f"{len(e.get('vin', []))}/{e.get('n', 0)}", ", ".join(e.get("vin", [])) or "—", None),
               ("β Dimson bình quân", fmt.num(e.get("beta"), 2), ">1: dao động mạnh hơn thị trường", None),
               ("Thua trung vị khi D cao", fmt.frac_pct(e.get("lose_hiD"), 0), f"{e.get('n_hiD', 0)} phiên D ≥ phân vị 80", None)])
    if wl is not None and not wl.empty:
        pdf.figure(charts.watch_perf(wl, ctx["idx_hist"]["VN-Index"], syms))
    rows = []
    for r in pf.itertuples():
        if not r.has_data:
            rows.append([r.symbol] + ["—"] * 7)
            continue
        rows.append([r.symbol, fmt.price(r.close), fmt.pct(r.ret * 100), fmt.num(r.ER_M * 100, 2, True),
                     fmt.num(r.C, 2, True) if r.C is not None else "—", fmt.bn(r.net_flow, 1),
                     ABSORB_LABELS.get(r.absorb_state, ""), fmt.num(r.beta_dimson, 2)])
    pdf.table(["Mã", "Giá", "%", "ERᴹ (đ.%)", "Đóng góp", "NN ròng", "Chiều giá – ngoại", "β Dimson"], rows,
              [14, 20, 18, 22, 20, 24, 44, 20])
    pdf.bullets([r.sentence for r in pf.itertuples()], 8.2)


# ── 5. Kết luận và hàm ý ─────────────────────────────────────────────────────
def ch_conclusion(pdf: FFRPdf, ctx: Dict, db_path=None) -> None:
    sr = _stats(db_path)
    rows = dg.research_rows(sr)
    pdf.h1("Kết luận và hàm ý", "(a) kết luận phiên · (b) kết luận giai đoạn với mức bằng chứng · (c) hàm ý dạng điều kiện · "
                                 "(d) các ngưỡng cần theo dõi.", concl=session_conclusion(ctx))
    pdf.h2("(a) Kết luận phiên")
    pdf.bullets([f"{a['q']} {a['a']}" for a in ctx.get("answers", [])], 8.3)
    pdf.h2("(b) Kết luận giai đoạn FTSE")
    if rows:
        pdf.table(["Câu hỏi", "p Holm", "Mức bằng chứng"], [[r["q"], _p(r["p"]), r["label"]] for r in rows], [118, 24, 40],
                  aligns=["L", "R", "L"])
    pdf.h2("(c) Hàm ý cho nhà đầu tư – câu điều kiện, không phải khuyến nghị mua/bán")
    pdf.bullets(ctx.get("implications", []), 8.3)
    pdf.h2("(d) Các ngưỡng cần theo dõi")
    vni = ctx["idx_hist"]["VN-Index"]
    vr = ctx["vol_range"]
    rows = [["VN-Index hiện tại", fmt.num(vni.iloc[-1], 2), "Đóng cửa phiên báo cáo"],
            ["MA20 / MA50", f"{fmt.num(vni.rolling(20).mean().iloc[-1], 0)} / {fmt.num(vni.rolling(50).mean().iloc[-1], 0)}",
             "Trung bình giá 20 / 50 phiên"]]
    for h in sorted(vr):
        r = vr[h]
        rows.append([f"Biên dao động {h} phiên", f"68%: {fmt.num(r['lo68'], 0)}–{fmt.num(r['hi68'], 0)} · 90%: "
                                                f"{fmt.num(r['lo90'], 0)}–{fmt.num(r['hi90'], 0)}",
                     f"EWMA hiệu chỉnh đuôi dày; bao phủ thực tế 90%: {fmt.frac_pct(r.get('coverage90'), 0)}"])
    pdf.table(["Ngưỡng", "Giá trị", "Ghi chú"], rows, [44, 70, 68], aligns=["L", "L", "L"])
    pdf.para("Biên mô tả mức dao động bình thường, không phải dự báo hướng đi. Không xét yếu tố cơ bản doanh nghiệp, vĩ mô hay khẩu "
             "vị rủi ro của từng nhà đầu tư.", 7.6, "I")


# ── 6. Thị trường chung ──────────────────────────────────────────────────────
def ch_market(pdf: FFRPdf, ctx: Dict, n_movers: int = 3) -> None:
    rc = ctx["recap"]
    pdf.h1("Thị trường chung", "Hiệu suất chỉ số, thanh khoản và cổ phiếu nổi bật (GTGD ≥ 10 tỷ).",
           concl=f"VN-Index {fmt.pct(rc[5]['vni_ret'])} trong 5 phiên và {fmt.pct(rc[20]['vni_ret'])} trong 20 phiên; GTGD bình quân "
                 f"5 phiên bằng {fmt.num((rc.get('tv_ratio') or np.nan) * 100, 0)}% mức 20 phiên trước.")
    pdf.figure(charts.index_chart(ctx["idx_hist"]["VN-Index"], ctx["tv_hist"], _events(ctx)), w=170)
    pdf.table(["Chỉ số", "1 tuần", "1 tháng", "3 tháng", "6 tháng", "Từ đầu năm", "1 năm"],
              [[name] + [fmt.pct(r.get(k), 1) for k in PERIOD_KEYS] for name, r in ctx["idx_ret"].items()],
              [40, 23, 23, 23, 23, 26, 24])
    v = ctx["stock"][ctx["stock"]["is_valid"]]
    liq = v[v["tv"] >= float(get("outlook.movers_min_tv_bn", 10)) * 1e9]
    rows = []
    for lbl, df in (("Tăng mạnh nhất", liq.nlargest(n_movers, "ret")), ("Giảm mạnh nhất", liq.nsmallest(n_movers, "ret")),
                    ("GTGD lớn nhất", liq.nlargest(n_movers, "tv"))):
        for i, r in enumerate(df.itertuples()):
            rows.append([lbl if i == 0 else "", r.symbol, fmt.price(r.close), fmt.pct(r.ret * 100), fmt.num(r.tv / 1e9, 1),
                         fmt.num(r.net_flow / 1e9, 1, True)])
    pdf.table(["Nhóm", "Mã", "Giá", "% phiên", "GTGD (tỷ)", "NN ròng (tỷ)"], rows, [40, 20, 28, 26, 30, 38])


# ── Phụ lục ──────────────────────────────────────────────────────────────────
def ch_appendix(pdf: FFRPdf, ctx: Dict, db_path=None) -> None:
    pdf.h1("Phụ lục – Phương pháp, ký hiệu và chất lượng dữ liệu")
    pdf.table(["Phần", "Phương pháp", "Cách tính"], [
        ["Lan tỏa", "D, AD, IQR, loại phiên", "D = r VN-Index − trung vị r; loại phiên theo dấu r VN-Index × dấu AD"],
        ["Dẫn dắt", "Đóng góp điểm C, ε, CR5", "C = I(t−1)·w·r; ε = ΔI − ΣC; CR5 = Σ|C| top 5 / Σ|C|"],
        ["Dẫn dắt", "HHI tỷ trọng chỉ số", "Σw²; 1/HHI = số mã hiệu dụng – biến kiểm soát cho CR5"],
        ["Nối khối ngoại", "Đóng góp có ngoại cùng chiều", "Σ|C| các mã có dấu NF trùng dấu C / Σ|C|"],
        ["Khối ngoại", "NF, nf, FPR, HHI, z60", "Mua − bán; NF/GTGD; (mua + bán)/2GTGD; Σ tỷ trọng²; z theo 60 phiên trước"],
        ["Khối ngoại", "Chiều giá – ngoại", "Dấu NF × dấu giá khi |nf| ≥ 5% và |r| ≥ 0,5% (ròng khối nội = −NF)"],
        ["FTSE", "Sự kiện, DiD", "CAR/CAAR, BMP + Kolari–Pynnönen, Welch FTSE − đối chứng, p Holm; DiD hiệu ứng cố định"],
        ["FTSE", "H4 có kiểm soát", "Chỉ báo ~ giả biến giai đoạn + HHI tỷ trọng; OLS Newey–West 5 trễ"],
        ["Kết luận", "Hồi quy gộp D", "D ~ HHI_w + r 10 mã lớn + nf 10 mã lớn + |r VN-Index|, HAC 5 trễ"],
        ["Watchlist", "ERᴹ, β Dimson, phơi nhiễm", "ER = r − trung vị; Kruskal–Wallis trên ERᴹ theo loại phiên"],
        ["Biên dao động", "EWMA hiệu chỉnh đuôi dày", "σ EWMA λ = 0,94; biên I·exp(±k·σ·căn h), k = phân vị sai số quá khứ"],
    ], [24, 50, 108], aligns=["L", "L", "L"])
    q = db.query_df("SELECT check_name, value, status, detail FROM data_quality_log WHERE trade_date = ?", [ctx["date"]], path=db_path)
    if not q.empty:
        pdf.h2(f"Chất lượng dữ liệu phiên {ctx['date']:%d/%m/%Y}")
        pdf.table(["Kiểm tra", "Giá trị", "Trạng thái", "Ghi chú"],
                  [[r.check_name, fmt.num(r.value, 4), r.status, str(r.detail or "")[:70]] for r in q.itertuples()],
                  [36, 24, 20, 102], aligns=["L", "R", "L", "L"])
    pdf.bullets([
        "Vốn hóa xấp xỉ bằng số cổ phiếu niêm yết (chưa trừ cổ phiếu quỹ, free-float); một phần số cổ phiếu được suy ra từ room "
        "khối ngoại; hệ số chỉnh k ước lượng trên toàn mẫu – sai số đo hằng ngày bằng ε.",
        "Ròng khối nội = − ròng khối ngoại; nhãn chiều giá – ngoại chỉ mô tả, không đo hành vi riêng của khối nội.",
        "Tương quan cùng phiên không phải nhân quả; nghiên cứu sự kiện mẫu nhỏ (27 mã), giai đoạn sau hiệu lực còn ngắn.",
        get("app.disclaimer")], 8.0)
