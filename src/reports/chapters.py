"""
Các chương báo cáo PDF – thứ tự đọc từ toàn cảnh đến kết luận:

  Bìa (+ kết luận phiên) → mục lục + tóm tắt điều hành (3 câu trả lời) →
  1. Tổng quan thị trường · 2. Dẫn dắt & độ vênh · 3. Dòng vốn ngoại · 4. Bối cảnh nâng hạng FTSE ·
  5. Chẩn đoán thị trường · 6. Tác động lên watchlist · 7. Kết luận và điều cần theo dõi · 8. Phụ lục

Quy ước trình bày: mỗi chương bắt đầu ở TRANG MỚI, mở đầu bằng một câu kết luận in đậm sinh từ số liệu và một khung
"Diễn giải" vài dòng cho người đọc không chuyên; nếu trang cuối của chương còn trống quá nửa, chương được bổ sung biểu
đồ/bảng phụ (hàm _fill). Khuyến nghị ở chương 7 chỉ suy ra từ chỉ báo theo quy tắc cố định, không đánh giá doanh nghiệp.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd

from src.analytics import diagnosis as dg
from src.common import fmt
from src.common.config import get
from src.data import database as db
from src.finance.breadth import session_label, session_type_label  # noqa: F401
from src.finance.domestic import ABSORB_LABELS
from src.reports import charts
from src.reports.pdf_base import FFRPdf
from src.reports.sections import PERIOD_KEYS, _events, _p, key_facts, key_table

HALF_PAGE = 125.0      # mm – trang còn trống nhiều hơn mức này thì bổ sung nội dung phụ


def _stats(db_path=None) -> pd.DataFrame:
    return db.query_df("SELECT * FROM stats_results", path=db_path) if db.table_exists("stats_results", db_path) else pd.DataFrame()


def _fill(pdf: FFRPdf, extras: List[Tuple[float, Callable[[], None]]]) -> None:
    """Bổ sung nội dung phụ (ước lượng chiều cao, hàm vẽ) khi trang hiện tại còn trống quá nửa."""
    for h, fn in extras:
        if pdf.room() <= HALF_PAGE:
            return
        if pdf.room() >= h:
            fn()


def _explain(pdf: FFRPdf, items: List[str], title: str = "Diễn giải – điểm chính") -> None:
    items = [t for t in items if t]
    if items:
        pdf.callout(title, items, 8.2)


def _state(ctx: Dict):
    """Bảng trạng thái chỉ báo (kỹ thuật + cấu trúc dòng vốn) – tính một lần cho cả báo cáo."""
    if "regime" not in ctx:
        from src.analytics import technical
        ctx["regime"] = technical.market_state(ctx["hist"])
    return ctx["regime"]


def session_conclusion(ctx: Dict) -> str:
    """Một câu kết luận phiên (dùng cho bìa và chương kết luận)."""
    x, et, lead = ctx["day"], ctx.get("ex_today", pd.Series(dtype=float)), ctx["leaders"]
    main = lead[lead["side"] == ("neg" if x["dI"] < 0 else "pos")].head(2)
    return (f"Phiên {session_label(x).lower()}: năm mã tạo {fmt.frac_pct(x['CR5'], 0)} biến động, dẫn đầu "
            f"{', '.join(main['symbol'])}. " + dg.codir_sentence(et.get("codir"), et.get("codir_base")))


# ── 1. Tổng quan thị trường ──────────────────────────────────────────────────
def ch_market(pdf: FFRPdf, ctx: Dict, n_movers: int = 3) -> None:
    x, rc = ctx["day"], ctx["recap"]
    vni = ctx["idx_hist"]["VN-Index"]
    ma20, ma50 = vni.rolling(20).mean().iloc[-1], vni.rolling(50).mean().iloc[-1]
    pdf.h1("Tổng quan thị trường", "Chỉ số, thanh khoản, ngành và cổ phiếu nổi bật của phiên, đặt cạnh 5 và 20 phiên gần nhất.",
           concl=f"VN-Index {fmt.pct(x['r_vni_pct'])} còn {fmt.num(x['vni'], 2)} điểm; {fmt.pct(rc[5]['vni_ret'])} trong 5 phiên, "
                 f"{fmt.pct(rc[20]['vni_ret'])} trong 20 phiên; GTGD bình quân 5 phiên bằng "
                 f"{fmt.num((rc.get('tv_ratio') or np.nan) * 100, 0)}% mức 20 phiên trước.")
    from src.reports.sections import index_cards
    pdf.cards(index_cards(ctx))
    tv20 = ctx["hist"]["tv_total"].tail(21).iloc[:-1].mean()
    pdf.figure(charts.index_chart(vni, ctx["tv_hist"], _events(ctx)), w=170)
    pdf.table(["Chỉ số", "1 tuần", "1 tháng", "3 tháng", "6 tháng", "Từ đầu năm", "1 năm"],
              [[name] + [fmt.pct(r.get(k), 1) for k in PERIOD_KEYS] for name, r in ctx["idx_ret"].items()],
              [40, 23, 23, 23, 23, 26, 24])
    if not ctx["sec1"].empty:
        pdf.figure(charts.sector_compare(ctx["sec1"], ctx["sec20"]))
    v = ctx["stock"][ctx["stock"]["is_valid"]]
    liq = v[v["tv"] >= float(get("outlook.movers_min_tv_bn", 10)) * 1e9]
    rows = []
    for lbl, df in (("Tăng mạnh nhất", liq.nlargest(n_movers, "ret")), ("Giảm mạnh nhất", liq.nsmallest(n_movers, "ret")),
                    ("GTGD lớn nhất", liq.nlargest(n_movers, "tv"))):
        for i, r in enumerate(df.itertuples()):
            rows.append([lbl if i == 0 else "", r.symbol, fmt.price(r.close), fmt.pct(r.ret * 100), fmt.num(r.tv / 1e9, 1),
                         fmt.num(r.net_flow / 1e9, 1, True)])
    pdf.h2("Cổ phiếu nổi bật (GTGD ≥ 10 tỷ đồng)")
    pdf.table(["Nhóm", "Mã", "Giá", "% phiên", "GTGD (tỷ)", "NN ròng (tỷ)"], rows, [40, 20, 28, 26, 30, 38])
    _fill(pdf, [(95, lambda: pdf.figure(charts.treemap(ctx["stock"]))),
                (25, lambda: pdf.figure(charts.breadth_today(x)))])


# ── 2. Dẫn dắt & độ vênh ─────────────────────────────────────────────────────
def ch_leaders_div(pdf: FFRPdf, ctx: Dict) -> None:
    x, lead, h = ctx["day"], ctx["leaders"], ctx["hist"]
    g = ctx["groups"]
    vin = g[(g["group_type"] == "family") & (g["group_name"] == "VINGROUP")]
    ex_vin = vin["index_ex_group_ret_pct"].iloc[0] if not vin.empty else np.nan
    pdf.h1("Dẫn dắt và độ vênh", "Ai đang kéo VN-Index và chỉ số có phản ánh số đông cổ phiếu không. "
                                 "Đóng góp điểm C = I(t−1)·tỷ trọng·lợi suất; độ vênh D = %VN-Index − % cổ phiếu trung vị.",
           concl=ctx["answers"][0]["a"] if ctx.get("answers") else "")
    main = lead[lead["side"] == ("neg" if x["dI"] < 0 else "pos")].head(3)
    _explain(pdf, [
        f"Năm mã ảnh hưởng nhất chiếm {fmt.frac_pct(x['CR5'], 0)} tổng đóng góp tuyệt đối (phân vị 250 phiên "
        f"{fmt.num(x.get('CR5_pct250'), 0)}%) – " + ("chỉ số đang bị một nhóm nhỏ chi phối." if (x.get("CR5_pct250") or 0) >= 80
                                                     else "mức tập trung không bất thường so với một năm qua."),
        f"Dẫn dắt chính: {', '.join(main['symbol'])} ({fmt.num(main['C'].sum(), 2, True)} điểm / ΔVN-Index "
        f"{fmt.num(x['dI'], 2, True)} điểm).",
        f"Nếu loại họ Vingroup, VN-Index {fmt.pct(ex_vin)} so với thực tế {fmt.pct(x['r_vni_pct'])} – "
        + ("họ Vingroup làm biến động chỉ số mạnh hơn đáng kể." if pd.notna(ex_vin) and abs(x["r_vni_pct"] - ex_vin) >= 0.3
           else "ảnh hưởng của họ Vingroup không lớn trong phiên."),
        f"Độ vênh D = {fmt.num(x['D'], 2, True)} điểm %: "
        + dg.representative(x) + f" (phân vị 250 phiên {fmt.num(x.get('D_pct250'), 0)}%).",
    ])
    both = pd.concat([lead[lead["side"] == "pos"].head(6), lead[lead["side"] == "neg"].head(6)]).sort_values("C", ascending=False)
    rest = float(x["sumC"] - both["C"].sum()) if "sumC" in x else 0.0
    b1 = charts.hbar(both["symbol"].tolist() + ["Còn lại"], both["C"].tolist() + [rest], "Đóng góp điểm phiên này",
                     total=("ΔVN-Index", float(x["dI"])), size=(3.7, 3.4))
    l20 = ctx["lead20"].sort_values("C", ascending=False)
    b2 = charts.hbar(l20["symbol"].tolist(), l20["C"].tolist(), "Đóng góp lũy kế 20 phiên (ΣC)", dec=1, size=(3.7, 3.4))
    pdf.figures_row([b1, b2])
    v = ctx["stock"][ctx["stock"]["is_valid"]]
    tot = v["C"].abs().sum() or 1
    top = v.reindex(v["C"].abs().sort_values(ascending=False).index).head(10)
    nf = top["net_flow"].fillna(0)
    same = (np.sign(nf) == np.sign(top["C"])) & (nf != 0)
    pdf.h2("Mười mã đóng góp lớn nhất")
    pdf.table(["Mã", "Ngành", "% giá", "Đóng góp (điểm)", "% tổng |C|", "NN ròng (tỷ)", "Ngoại cùng chiều"],
              [[r.symbol, str(r.sector)[:22], fmt.pct(r.ret * 100), fmt.num(r.C, 2, True), fmt.num(abs(r.C) / tot * 100, 1, False, "%"),
                fmt.num(r.net_flow / 1e9, 1, True), "có" if s else "không"] for r, s in zip(top.itertuples(), same)],
              [16, 46, 20, 28, 22, 26, 24], aligns=["L", "L", "R", "R", "R", "R", "L"])
    pdf.figures_row([charts.breadth_history(h), charts.divergence_chart(h)])
    fam = g[g["group_type"] == "family"].sort_values("C", ascending=False)

    def _fam():
        pdf.h2("Họ cổ phiếu – đóng góp và chỉ số khi loại trừ họ")
        pdf.table(["Họ cổ phiếu", "Số mã", "Đóng góp (điểm)", "VN-Index loại trừ họ", "Thực tế", "Chênh lệch (đ.%)"],
                  [[r.group_name, str(int(r.n)), fmt.num(r.C, 2, True), fmt.pct(r.index_ex_group_ret_pct), fmt.pct(x["r_vni_pct"]),
                    fmt.num(x["r_vni_pct"] - r.index_ex_group_ret_pct, 2, True)] for r in fam.itertuples()], [40, 18, 30, 34, 30, 30])

    def _key():
        pdf.h2("Chỉ tiêu chính so với lịch sử gần")
        pdf.table(["Chỉ tiêu", "Phiên này", "Phiên trước", "TB 5 phiên", "TB 20 phiên", "Phân vị 250 ph."], key_table(ctx),
                  [58, 24, 24, 24, 26, 26])
    _fam() if not fam.empty else None
    _fill(pdf, [(60, _key)])


# ── 3. Dòng vốn ngoại ────────────────────────────────────────────────────────
def ch_flow(pdf: FFRPdf, ctx: Dict) -> None:
    x, rc = ctx["day"], ctx["recap"]
    et = ctx.get("ex_today", pd.Series(dtype=float))
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
    tb, ts = ctx["top_buy"], ctx["top_sell"]
    pdf.figure(charts.foreign_flow(ctx["hist"]))
    top = pd.concat([tb[tb["net_flow"] > 0], ts[ts["net_flow"] < 0]]).sort_values("net_flow", ascending=False)
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
    _fill(pdf, [(65, lambda: pdf.figure(charts.codir_chart(ctx["extras"], 120, size=(7.4, 2.4))))])


# ── 4. Bối cảnh FTSE ─────────────────────────────────────────────────────────
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
    yes = [r for r in rows if r["label"] == "Có bằng chứng"]
    no = [r for r in rows if r["label"] != "Có bằng chứng"]
    _explain(pdf, [
        ("Có bằng chứng thống kê: " + "; ".join(r["q"].rstrip("?").lower() for r in yes) + ".") if yes else "",
        ("Chưa đủ bằng chứng: " + "; ".join(r["q"].rstrip("?").lower() for r in no) + ".") if no else "",
        "Ý nghĩa: biến động của VN-Index ngày càng phụ thuộc vào một số ít mã vốn hóa lớn; việc khối ngoại mua hay bán ròng ở nhóm "
        "này không giải thích được độ vênh – nhà đầu tư nên tách 'chỉ số' khỏi 'thị trường số đông' khi đánh giá danh mục.",
    ])
    gh = ctx.get("groups_hist")
    e1 = pd.Timestamp(get("periods.announce", "2025-10-08"))
    if gh is not None and not gh.empty:
        pdf.figure(charts.groups_cum(gh, e1, _events(ctx)))
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
                  [[r["label"], fmt.num(r["coef"], 3, True), fmt.num(r["t"], 2, True), _p(r["p"]), dg.evidence_label(r["p"])]
                   for r in reg["rows"]], [76, 26, 18, 20, 42], aligns=["L", "R", "R", "R", "L"])
        pdf.para(f"D_t = a + b1·HHI tỷ trọng + b2·lợi suất 10 mã lớn + b3·nf 10 mã lớn + b4·|r VN-Index| + e_t; sai số HAC 5 trễ; "
                 f"{reg['n']} phiên từ {reg['from']:%d/%m/%Y}; R² = {fmt.num(reg['r2'], 2)}.", 7.6, "I")
    pdf.figures_row([charts.ftse_contrib_chart(ctx["extras"]), charts.codir_chart(ctx["extras"], 120)])


# ── 5. Chẩn đoán thị trường ──────────────────────────────────────────────────
def technical_chart(t: Dict):
    return charts.tech_chart(t)


def ch_diagnosis(pdf: FFRPdf, ctx: Dict) -> None:
    x, et, lead = ctx["day"], ctx["ex_today"], ctx["leaders"]
    v = ctx["stock"][ctx["stock"]["is_valid"]]
    g = ctx["groups"]
    vin = g[(g["group_type"] == "family") & (g["group_name"] == "VINGROUP")]
    from src.analytics import technical
    state = _state(ctx)
    pdf.h1("Chẩn đoán thị trường", "Phân tích kỹ thuật VN-Index, cấu trúc dòng vốn và kịch bản theo dõi – tổng hợp các chương trước.",
           concl=technical.headline(state))
    from src.analytics import technical
    t = technical.snapshot(ctx["hist"])
    tone = {"pos": "Tích cực", "neg": "Tiêu cực", "neu": "Trung tính"}
    for grp, title in (("Kỹ thuật", "1 · Phân tích kỹ thuật – xu hướng, động lượng, khối lượng"),
                       ("Cấu trúc & dòng vốn", "2 · Cấu trúc thị trường và dòng vốn")):
        rr = [r for r in state if r.get("group") == grp]
        if not rr:
            continue
        pdf.h2(title)
        pdf.table(["Khía cạnh", "Số liệu", "Đọc kết quả", "Đánh giá"],
                  [[r["name"], r["value"], r["reading"], tone[r["tone"]]] for r in rr],
                  [38, 56, 66, 22], aligns=["L", "L", "L", "L"], size=7.6)
        if grp == "Kỹ thuật":
            pdf.figure(technical_chart(t))
    pdf.h2("3 · Kịch bản theo dõi – ngưỡng hỗ trợ / kháng cự")
    pdf.table(["Kịch bản", "Điều kiện", "Ý nghĩa"],
              [[sc["case"], sc["cond"], sc["meaning"]] for sc in technical.scenarios(t, ctx.get("vol_range") or {})],
              [30, 66, 86], aligns=["L", "L", "L"], size=7.6)
    # Tóm tắt chẩn đoán phiên – đặt cuối chương, diễn giải sâu từng bước
    main = lead[lead["side"] == ("neg" if x["dI"] < 0 else "pos")].head(3)
    rho = v[["C", "net_flow"]].dropna().corr(method="spearman").iloc[0, 1] if len(v) > 10 else np.nan
    top10 = v[v["symbol"].isin(lead["symbol"])]
    stc = top10["absorb_state"].value_counts()
    steps = [
        f"Bước 1 – Lan tỏa: D = {fmt.num(x['D'], 2, True)} điểm % (phân vị {fmt.num(x['D_pct250'], 0)}% của 250 phiên), loại phiên "
        f"{session_label(x).lower()}, {fmt.num(x['pct_up'], 0)}% số mã tăng, IQR lợi suất {fmt.num(x['IQR_pct'], 1)}%. "
        + dg.representative(x)[:1].upper() + dg.representative(x)[1:] + ".",
        f"Bước 2 – Ai tạo biến động: CR5 = {fmt.frac_pct(x['CR5'], 0)}; dẫn đầu {', '.join(main['symbol'])} "
        f"({fmt.num(main['C'].sum(), 2, True)} điểm); 27 mã FTSE đóng góp {fmt.num(et.get('ftse_C'), 2, True)} điểm; số mã hiệu dụng "
        f"của chỉ số {fmt.num(et.get('eff_n'), 1)}. Bỏ họ Vingroup, VN-Index "
        f"{fmt.pct(vin['index_ex_group_ret_pct'].iloc[0]) if not vin.empty else '—'} (thực tế {fmt.pct(x['r_vni_pct'])}).",
        "Bước 3 – Khối ngoại đi cùng chiều đến đâu: " + dg.codir_sentence(et.get("codir"), et.get("codir_base"))
        + f" Tương quan hạng ρ(C, NF) = {fmt.num(rho, 2, True)}; NN ròng {fmt.bn(x['NF_total'])}.",
        "Bước 4 – Phản ứng giá ở 10 mã dẫn dắt: " + "; ".join(f"{ABSORB_LABELS[k].lower()} {int(n)}" for k, n in stc.items()
                                                                 if k != "neutral")
        + (f"; {int(stc.get('neutral', 0))} mã biến động nhỏ." if stc.get("neutral") else "."),
        "Bước 5 – Watchlist: " + (ctx["answers"][2]["a"] if len(ctx.get("answers", [])) > 2 else "danh mục trống."),
    ]
    pdf.h2("4 · Góc nhìn phiên – chẩn đoán 5 bước")
    pdf.callout("Chuỗi chẩn đoán phiên", steps)
    _fill(pdf, [(62, lambda: pdf.figures_row([charts.breadth_history(ctx["hist"]), charts.divergence_chart(ctx["hist"])])),
                (62, lambda: pdf.figures_row([charts.ftse_contrib_chart(ctx["extras"]), charts.codir_chart(ctx["extras"])]))])


# ── 6. Tác động lên watchlist ────────────────────────────────────────────────
def ch_watch_impact(pdf: FFRPdf, ctx: Dict) -> None:
    pf = ctx["watch"]
    syms = list(ctx.get("watch_symbols") or [])
    if pf is None or pf.empty:
        pdf.h1("Tác động lên watchlist", concl="Danh mục theo dõi trống.")
        return
    wl = ctx.get("wl_hist")
    e = dg.watch_exposure(syms, ctx["date"], pd.concat([wl, ctx["stock"]]).drop_duplicates(["trade_date", "symbol"]),
                          ctx["hist"], pf, market=ctx["stock"]) if wl is not None else {}
    w = pf[pf["has_data"].astype(bool)] if "has_data" in pf else pf
    concl = (f"{int((w['ER_M'] > 0).sum())}/{len(w)} mã hơn trung vị thị trường hôm nay; {len(e.get('lead', []))}/{e.get('n', len(syms))} mã "
             f"nằm trong nhóm dẫn dắt; khi độ vênh cao, watchlist thua trung vị {fmt.frac_pct(e.get('lose_hiD'), 0)} số phiên.")
    pdf.h1("Tác động lên watchlist", "Mức phơi nhiễm với nhóm dẫn dắt và phản ứng so với thị trường (ERᴹ = r − trung vị).", concl=concl)
    pdf.cards([("Trong nhóm dẫn dắt", f"{len(e.get('lead', []))}/{e.get('n', 0)}", ", ".join(e.get("lead", [])) or "không mã nào", None),
               ("Họ Vingroup", f"{len(e.get('vin', []))}/{e.get('n', 0)}", ", ".join(e.get("vin", [])) or "—", None),
               ("β Dimson bình quân", fmt.num(e.get("beta"), 2), ">1: dao động mạnh hơn thị trường", None),
               ("Thua trung vị khi D cao", fmt.frac_pct(e.get("lose_hiD"), 0), f"{e.get('n_hiD', 0)} phiên D ≥ phân vị 80", None)])
    best = w.sort_values("ER_M").iloc[-1] if not w.empty else None
    worst = w.sort_values("ER_M").iloc[0] if not w.empty else None
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


# ── 7. Kết luận và điều cần theo dõi ─────────────────────────────────────────
def market_recommendations(ctx: Dict) -> List[str]:
    """Điều cần theo dõi ở cấp THỊ TRƯỜNG, suy ra từ chỉ báo theo quy tắc cố định.

    Chỉ MÔ TẢ trạng thái và mốc cần theo dõi – không có câu hành động (mua/bán, tỷ trọng, đòn bẩy, thận trọng với nhóm…)."""
    x = ctx["day"]
    vni = ctx["idx_hist"]["VN-Index"]
    ma20, ma50 = vni.rolling(20).mean().iloc[-1], vni.rolling(50).mean().iloc[-1]
    last = float(vni.iloc[-1])
    reg = {r["name"]: r for r in _state(ctx)}
    vr = ctx.get("vol_range") or {}
    out = []
    if last < ma20 and last < ma50:
        out.append(f"Xu hướng: VN-Index ({fmt.num(last, 0)}) nằm dưới cả MA20 ({fmt.num(ma20, 0)}) và MA50 ({fmt.num(ma50, 0)}) – "
                   "xu hướng ngắn và trung hạn đang yếu. Mốc cần theo dõi: chỉ số đóng cửa trở lại trên MA20.")
    elif last > ma20 and last > ma50:
        out.append(f"Xu hướng: VN-Index ({fmt.num(last, 0)}) nằm trên cả MA20 ({fmt.num(ma20, 0)}) và MA50 ({fmt.num(ma50, 0)}) – "
                   "xu hướng ngắn và trung hạn đang tích cực. Mốc cần theo dõi: đóng cửa dưới MA20 là dấu hiệu suy yếu đầu tiên.")
    else:
        out.append(f"Xu hướng: VN-Index ({fmt.num(last, 0)}) nằm giữa MA20 ({fmt.num(ma20, 0)}) và MA50 ({fmt.num(ma50, 0)}) – "
                   "tín hiệu trái chiều. Mốc cần theo dõi: chỉ số đóng cửa cùng phía với cả hai đường.")
    pct = x.get("D_pct250")
    if x["pct_up"] <= 40 or (pd.notna(pct) and (pct >= 80 or pct <= 20)):
        out.append(f"Lan tỏa: {fmt.num(x['pct_up'], 0)}% số mã tăng, D = {fmt.num(x['D'], 2, True)} (phân vị {fmt.num(pct, 0)}%) – "
                   f"{dg.representative(x)}. So danh mục với cổ phiếu trung vị sẽ sát hơn so với VN-Index.")
    if (x.get("CR5_pct250") or 0) >= 80:
        out.append(f"Tập trung: CR5 ở phân vị {fmt.num(x['CR5_pct250'], 0)}% của 250 phiên – chỉ số đang phụ thuộc vài mã lớn.")
    nf5 = reg.get("Khối ngoại 5 phiên")
    if nf5:
        out.append(f"Khối ngoại 5 phiên: {nf5['value']} – {nf5['reading']}. Mốc cần theo dõi: lũy kế ròng 20 phiên có đổi chiều hay không.")
    if 5 in vr:
        r = vr[5]
        out.append(f"Biên dao động 5 phiên (90%): {fmt.num(r['lo90'], 0)} – {fmt.num(r['hi90'], 0)} điểm. Đóng cửa ngoài biên là tình "
                   "huống hiếm (≈ 1/10 lần) – dấu hiệu biến động tăng, không phải tín hiệu giao dịch.")
    tones = [r["tone"] for r in ctx.get("regime", [])]
    neg, pos = tones.count("neg"), tones.count("pos")
    lean = "nghiêng tiêu cực" if neg > pos else "nghiêng tích cực" if pos > neg else "cân bằng"
    out.insert(0, f"Bức tranh chỉ báo {lean}: {pos} khía cạnh tích cực, {neg} tiêu cực, {len(tones) - pos - neg} trung tính "
                  "(xem bảng trạng thái từng chỉ báo).")
    return out


def ch_conclusion(pdf: FFRPdf, ctx: Dict, db_path=None) -> None:
    sr = _stats(db_path)
    rows = dg.research_rows(sr)
    rec = market_recommendations(ctx)
    pdf.h1("Kết luận và điều cần theo dõi", "(a) kết luận phiên · (b) kết luận giai đoạn FTSE · (c) điều cần theo dõi, suy ra từ chỉ báo · "
                                            "(d) các ngưỡng cần theo dõi.", concl=session_conclusion(ctx))
    pdf.h2("(a) Kết luận phiên")
    pdf.bullets([f"{a['q']} {a['a']}" for a in ctx.get("answers", [])], 8.3)
    pdf.h2("(b) Kết luận giai đoạn FTSE")
    if rows:
        pdf.table(["Câu hỏi", "p Holm", "Mức bằng chứng"], [[r["q"], _p(r["p"]), r["label"]] for r in rows], [118, 24, 40],
                  aligns=["L", "R", "L"])
    pdf.h2("(c) Điều cần theo dõi – suy ra từ chỉ báo")
    pdf.callout("Trạng thái và mốc cần theo dõi (cấp thị trường)", rec, 8.3)
    pdf.bullets(ctx.get("implications", []), 8.0)
    pdf.h2("(d) Các ngưỡng cần theo dõi")
    vni = ctx["idx_hist"]["VN-Index"]
    vr = ctx["vol_range"]
    trows = [["VN-Index hiện tại", fmt.num(vni.iloc[-1], 2), "Đóng cửa phiên báo cáo"],
             ["MA20 / MA50", f"{fmt.num(vni.rolling(20).mean().iloc[-1], 0)} / {fmt.num(vni.rolling(50).mean().iloc[-1], 0)}",
              "Trung bình giá 20 / 50 phiên"]]
    for h in sorted(vr):
        r = vr[h]
        trows.append([f"Biên dao động {h} phiên", f"68%: {fmt.num(r['lo68'], 0)}–{fmt.num(r['hi68'], 0)} · 90%: "
                                                 f"{fmt.num(r['lo90'], 0)}–{fmt.num(r['hi90'], 0)}",
                      f"EWMA hiệu chỉnh đuôi dày; bao phủ thực tế 90%: {fmt.frac_pct(r.get('coverage90'), 0)}"])
    pdf.table(["Ngưỡng", "Giá trị", "Ghi chú"], trows, [44, 70, 68], aligns=["L", "L", "L"])
    pdf.para("Các nhận định chỉ mô tả trạng thái thị trường từ chỉ báo theo quy tắc cố định nêu ở Phụ lục; không xét yếu tố cơ bản "
             "doanh nghiệp, vĩ mô và không phải lời khuyên mua bán. " + get("app.disclaimer"), 7.6, "I")

    def _state():
        tone = {"pos": "Tích cực", "neg": "Tiêu cực", "neu": "Trung tính"}
        pdf.h2("Bảng căn cứ – trạng thái từng chỉ báo")
        pdf.table(["Nhóm", "Khía cạnh", "Đọc kết quả", "Đánh giá"],
                  [[r.get("group", ""), r["name"], r["reading"], tone[r["tone"]]] for r in ctx.get("regime", [])],
                  [34, 52, 72, 24], aligns=["L", "L", "L", "L"], size=7.6)
    _fill(pdf, [(80, _state),
                (62, lambda: pdf.figure(charts.outlook_fan(ctx["idx_hist"]["VN-Index"], ctx["vol_range"]))
                 if ctx.get("vol_range") else None)])


# ── 8. Phụ lục ───────────────────────────────────────────────────────────────
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
        ["FTSE", "Hồi quy gộp D", "D ~ HHI_w + r 10 mã lớn + nf 10 mã lớn + |r VN-Index|, HAC 5 trễ"],
        ["Kỹ thuật", "MA, Dow, RSI(14), MACD", "MA20/50/200; đỉnh/đáy 20 phiên so 20 phiên trước; RSI Wilder 14; MACD = EMA12 − EMA26, tín hiệu EMA9"],
        ["Kỹ thuật", "Khối lượng, hỗ trợ/kháng cự", "GTGD/TB20 cùng chiều giá; ngưỡng = đỉnh/đáy 20–250 phiên trước và MA"],
        ["Biên dao động", "EWMA hiệu chỉnh đuôi dày", "σ EWMA λ = 0,94; biên I·exp(±k·σ·√h), k = phân vị sai số quá khứ"],
        ["Điều cần theo dõi", "Quy tắc trạng thái", "MA20/MA50; ≥55%/≤40% mã tăng; CR5 phân vị ≥80; |nf5 z| ≥ 1 (≥ 2: mạnh); σ ≥1,5%/≤0,8%"],
        ["Watchlist", "ERᴹ, β Dimson, phơi nhiễm", "ER = r − trung vị; Kruskal–Wallis trên ERᴹ theo loại phiên"],
    ], [24, 44, 114], aligns=["L", "L", "L"], size=7.6)
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
        "Chỉ báo kỹ thuật mô tả trạng thái giá – khối lượng, không dự báo hướng đi và không xét yếu tố cơ bản doanh nghiệp.",
        get("app.disclaimer")], 8.0)


CHAPTERS = [
    ("Tổng quan thị trường", "market"),
    ("Dẫn dắt và độ vênh", "leaders"),
    ("Dòng vốn ngoại", "flow"),
    ("Bối cảnh nâng hạng FTSE", "ftse"),
    ("Chẩn đoán thị trường", "diag"),
    ("Tác động lên watchlist", "watch"),
    ("Kết luận và điều cần theo dõi", "concl"),
    ("Phụ lục", "appendix"),
]


def render_one(pdf: FFRPdf, ctx: Dict, key: str, db_path=None) -> None:
    fns = {"market": lambda: ch_market(pdf, ctx), "leaders": lambda: ch_leaders_div(pdf, ctx), "flow": lambda: ch_flow(pdf, ctx),
           "ftse": lambda: ch_ftse_context(pdf, ctx, db_path), "diag": lambda: ch_diagnosis(pdf, ctx),
           "watch": lambda: ch_watch_impact(pdf, ctx), "concl": lambda: ch_conclusion(pdf, ctx, db_path),
           "appendix": lambda: ch_appendix(pdf, ctx, db_path)}
    fns[key]()
