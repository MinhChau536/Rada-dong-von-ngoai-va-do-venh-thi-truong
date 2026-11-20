"""
Trang "Chẩn đoán thị trường" – chẩn đoán VN-Index từ dữ liệu SSI FastConnect V3:

  Kết luận + khuyến nghị cấp thị trường (quy tắc cố định, src/reports/chapters.market_recommendations)
  1 · Phân tích kỹ thuật: MA20/50/200, cấu trúc đỉnh – đáy (Dow), RSI(14), MACD, khối lượng xác nhận (src/analytics/technical.py)
  2 · Cấu trúc thị trường & dòng vốn: lan tỏa, CR5, khối ngoại 5 phiên, σ EWMA + chuỗi % biến động có ngoại cùng chiều
  3 · Kịch bản theo dõi (hỗ trợ/kháng cự, biên dao động EWMA) · 4 · Góc nhìn phiên 5 bước · kết luận nghiên cứu giai đoạn FTSE
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics import diagnosis as dg
from src.analytics.watchlist_impact import get_watchlist
from src.app import data_access as da
from src.app.components import charts, status_bar
from src.app.components import widgets as W
from src.app.components.states import empty, safe_block
from src.app.components.ui import colored, esc, header, md, pal, plot, table_html
from src.app.theme import color_for
from src.common import fmt
from src.finance.breadth import session_type_label
from src.finance.domestic import ABSORB_LABELS


def _extras(date) -> pd.DataFrame:
    return _extras_v(pd.Timestamp(date), da._lv())


@st.cache_data(ttl=600, show_spinner=False)
def _extras_v(date, v: str) -> pd.DataFrame:
    from src.data import database as db
    cols = ["trade_date", "symbol", "is_valid", "w", "C", "net_flow", "tv"]
    st_ = db.query_df(f"SELECT {', '.join(cols)} FROM indicator_stock_daily WHERE trade_date <= ?", [date])
    ld = da._live_date()
    if ld is not None and ld <= date:                    # phiên tạm tính hôm nay (kho phụ)
        st_ = pd.concat([st_, da.stock_day(ld)[cols]], ignore_index=True)
    return dg.daily_extras(st_, da.daily())


def _regression(date):
    return _regression_v(pd.Timestamp(date), da._lv())


@st.cache_data(ttl=600, show_spinner=False)
def _regression_v(date, v: str):
    d = da.daily()
    return dg.d_regression(d[pd.to_datetime(d["trade_date"]) <= pd.Timestamp(date)], _extras(date))


def _step(no: int, title: str, value_html: str, sentence: str) -> str:
    return (f'<div class="dx-step"><div class="dx-no">{no}</div><div class="dx-body"><div class="dx-q">{esc(title)}</div>'
            f'<div class="dx-v">{value_html}</div><div class="dx-a">{sentence}</div></div></div>')


DX_CSS = """<style>
.dx-step { display:flex; gap:14px; border:1px solid rgba(148,163,184,.18); border-radius:14px; padding:12px 14px; margin-bottom:10px;
  background:rgba(255,255,255,.025); }
.dx-no { flex:0 0 34px; height:34px; border-radius:50%; background:#F5B341; color:#1A1206; font-weight:800; display:flex;
  align-items:center; justify-content:center; font-size:16px; }
.dx-q { font-weight:700; font-size:15px; }
.dx-v { display:flex; gap:18px; flex-wrap:wrap; margin:4px 0; font-size:13px; opacity:.9; }
.dx-v b { font-size:18px; font-variant-numeric:tabular-nums; }
.dx-a { font-size:13.5px; line-height:1.55; }
.dx-ev { display:inline-block; padding:2px 9px; border-radius:999px; font-size:12px; font-weight:700; white-space:nowrap; }
.dx-concl { border:1px solid rgba(245,179,65,.45); border-left:4px solid #F5B341; border-radius:12px; padding:12px 16px;
  font-size:14.5px; line-height:1.6; margin:6px 0 12px; background:rgba(245,179,65,.07); }
</style>"""

EV_COLORS = {"Có bằng chứng": "#16A34A", "Bằng chứng yếu": "#D97706", "Chưa đủ bằng chứng": "#64748B", "Chưa đủ dữ liệu": "#64748B"}


def _ev(label: str) -> str:
    c = EV_COLORS.get(label, "#64748B")
    return f'<span class="dx-ev" style="background:{c}22;color:{c};border:1px solid {c}66">{label}</span>'


@safe_block("chẩn đoán phiên")
def session_block(date) -> None:
    p = pal()
    x = da.daily().set_index("trade_date").loc[date]
    ex = _extras(date)
    et = ex[ex["trade_date"] == pd.Timestamp(date)].iloc[0]
    sd = da.stock_day(date)
    v = sd[sd["is_valid"]]
    lead = da.leaders(date)
    g = da.groups(date)
    vin = g[(g["group_type"] == "family") & (g["group_name"] == "VINGROUP")]
    # bước 1
    pct = x.get("D_pct250")
    s1 = ("VN-Index phản ánh khá sát số đông cổ phiếu." if abs(x["D"]) < 0.3 else
          f"VN-Index {'tăng' if x['D'] > 0 else 'giảm'} mạnh hơn cổ phiếu điển hình {fmt.num(abs(x['D']), 2)} điểm % – "
          "biến động chỉ số không đại diện cho số đông.")
    v1 = (f"<span>D <b style='color:{color_for(x['D'], p)}'>{fmt.num(x['D'], 2, True)}</b> đ.%</span>"
          f"<span>Phân vị 250 phiên <b>{fmt.num(pct, 0)}%</b></span><span>Loại phiên <b>{session_type_label(x['session_type'])}</b></span>")
    # bước 2
    main = lead[lead["side"] == ("neg" if x["dI"] < 0 else "pos")].head(3)
    ex_vin = vin["index_ex_group_ret_pct"].iloc[0] if not vin.empty else np.nan
    s2 = (f"Năm mã tạo {fmt.frac_pct(x['CR5'], 0)} tổng đóng góp tuyệt đối; dẫn đầu <b>{', '.join(main['symbol'])}</b>. "
          f"Nếu bỏ họ Vingroup, VN-Index {fmt.pct(ex_vin)} (thực tế {fmt.pct(x['r_vni_pct'])}).")
    v2 = (f"<span>CR5 <b>{fmt.frac_pct(x['CR5'], 0)}</b></span><span>Số mã hiệu dụng của chỉ số <b>{fmt.num(et['eff_n'], 1)}</b></span>"
          f"<span>Nhóm FTSE <b style='color:{color_for(et['ftse_C'], p)}'>{fmt.num(et['ftse_C'], 2, True)}</b> điểm</span>")
    # bước 3
    rho = v[["C", "net_flow"]].dropna().corr(method="spearman").iloc[0, 1] if len(v) > 10 else np.nan
    cod = et["codir"]
    s3 = (f"{fmt.frac_pct(cod, 0)} biến động điểm đến từ các mã khối ngoại giao dịch <b>cùng chiều</b> giá; tương quan hạng "
          f"giữa đóng góp điểm và khối ngoại ròng ρ = {fmt.num(rho, 2, True)}. "
          + ("Khối ngoại đứng sau phần lớn biến động hôm nay." if cod >= 0.6 else
             "Khối ngoại chỉ đứng sau một phần biến động – phần còn lại do khối nội." if cod >= 0.4 else
             "Biến động chủ yếu không đến từ khối ngoại."))
    v3 = (f"<span>Đóng góp có ngoại cùng chiều <b>{fmt.frac_pct(cod, 0)}</b></span><span>ρ(C, NF) <b>{fmt.num(rho, 2, True)}</b></span>"
          f"<span>NN ròng <b style='color:{color_for(x['NF_total'], p)}'>{fmt.bn(x['NF_total'])}</b></span>")
    # bước 4
    top10 = set(lead["symbol"])
    st_ = v[v["symbol"].isin(top10)]["absorb_state"].value_counts()
    s4 = "Trong 10 mã dẫn dắt: " + "; ".join(f"{ABSORB_LABELS[k].lower()} {int(n)} mã" for k, n in st_.items() if k != "neutral") \
         + (f"; {int(st_.get('neutral', 0))} mã biến động/dòng vốn quá nhỏ để phân loại." if st_.get("neutral") else ".")
    v4 = f"<span>Tỷ lệ mã tăng toàn sàn <b>{fmt.num(x['pct_up'], 0)}%</b></span><span>Trung vị lợi suất <b>{fmt.pct(x['median_ret_pct'])}</b></span>"
    # bước 5
    wl = get_watchlist()
    if wl:
        hist = pd.concat([da.stock_hist(s) for s in wl], ignore_index=True)
        e = dg.watch_exposure(wl, date, hist, da.daily())
        tw = v[v["symbol"].isin(wl)]
        er = float(tw["ER_M"].mean() * 100) if not tw.empty else np.nan
        s5 = (f"{len(e['lead'])}/{e['n']} mã watchlist nằm trong nhóm dẫn dắt"
              + (f" ({', '.join(e['lead'])})" if e["lead"] else "") + f"; hôm nay watchlist {'hơn' if er > 0 else 'kém'} "
              f"trung vị thị trường {fmt.num(abs(er), 2)} điểm %. Trong {e['n_hiD']} phiên độ vênh cao gần đây, watchlist thua trung vị "
              f"{fmt.frac_pct(e['lose_hiD'], 0)} số phiên.")
        v5 = (f"<span>ERᴹ hôm nay <b style='color:{color_for(er, p)}'>{fmt.num(er, 2, True)}</b> đ.%</span>"
              f"<span>Trong nhóm dẫn dắt <b>{len(e['lead'])}/{e['n']}</b></span>")
    else:
        s5, v5 = "Danh mục theo dõi trống.", ""
    md(_step(1, "Chỉ số có lan tỏa không?", v1, s1) + _step(2, "Ai tạo ra biến động?", v2, s2)
       + _step(3, "Khối ngoại có đứng sau không?", v3, s3) + _step(4, "Phần còn lại của thị trường phản ứng ra sao?", v4, s4)
       + _step(5, "Watchlist bị ảnh hưởng thế nào?", v5, s5))


@safe_block("chuỗi chỉ báo nối")
def link_series(date) -> None:
    p = pal()
    ex = _extras(date).tail(120)
    c1, c2 = st.columns(2, gap="small")
    with c1, W.card("dx_cod"):
        W.title("Khối ngoại có đứng sau biến động chỉ số không?",
                "Mỗi cột = % điểm biến động VN-Index đến từ các mã mà khối ngoại MUA khi giá tăng hoặc BÁN khi giá giảm · "
                "trên vạch 50% = khối ngoại đi cùng chiều phần lớn biến động · 120 phiên")
        fig = go.Figure()
        fig.add_bar(x=ex["trade_date"], y=ex["codir"] * 100, marker_color="rgba(56,189,248,.45)", name="% biến động có khối ngoại cùng chiều")
        fig.add_scatter(x=ex["trade_date"], y=(ex["codir"] * 100).rolling(10).mean(), name="Trung bình 10 phiên",
                        line=dict(color="#F5B341", width=2))
        fig.add_hline(y=50, line=dict(color=p["muted"], dash="dot"))
        plot(charts._lay(fig, p, 300, legend=dict(orientation="h", y=-0.18, x=0), margin=dict(l=8, r=8, t=8, b=8)), "dx_cod_fig")
    with c2, W.card("dx_ftse"):
        W.title("27 mã FTSE đóng góp bao nhiêu điểm vào VN-Index mỗi phiên?",
                "Cột vàng = điểm do 27 mã vào rổ FTSE tạo ra · cột xám = các mã còn lại · cộng hai cột = mức tăng/giảm của VN-Index")
        rest = ex["dI"] - ex["ftse_C"]
        fig = go.Figure()
        fig.add_bar(x=ex["trade_date"], y=ex["ftse_C"], name="27 mã FTSE (điểm)", marker_color="#F5B341")
        fig.add_bar(x=ex["trade_date"], y=rest, name="Các mã còn lại (điểm)", marker_color="rgba(148,163,184,.55)")
        plot(charts._lay(fig, p, 300, barmode="relative", legend=dict(orientation="h", y=-0.18, x=0),
                         margin=dict(l=8, r=8, t=8, b=8)), "dx_ftse_fig")


@safe_block("kết luận nghiên cứu")
def research_block(date) -> None:
    sr = da.table("stats_results")
    rows, concl = [], {}
    if not sr.empty:
        h4 = sr[(sr["hypothesis"] == "H4") & sr["test"].str.startswith("OLS")]
        want = [("CR5 – tập trung đóng góp", "Tập trung đóng góp (CR5) tăng sau công bố FTSE?", "base"),
                ("CR5 – tập trung đóng góp · kiểm soát HHI tỷ trọng", "… vẫn tăng khi đã kiểm soát tỷ trọng phình to?", "control_hhi_w"),
                ("Tỷ lệ phiên thiếu lan tỏa", "Phiên thiếu lan tỏa nhiều hơn sau công bố?", "base"),
                ("FPR – tỷ trọng GD khối ngoại", "Khối ngoại tham gia giao dịch nhiều hơn?", "base"),
                ("nf toàn sàn – cường độ ròng", "Khối ngoại mua ròng mạnh hơn?", "base"),
                ("D – độ vênh (điểm %)", "Độ vênh bình quân thay đổi?", "base")]
        for metric, q, var in want:
            r = h4[(h4["metric"] == metric) & (h4["window"] == "E1 → hiệu lực") & (h4["variant"] == var)]
            if r.empty:
                continue
            r = r.iloc[0]
            ph = r.get("p_holm") if pd.notna(r.get("p_holm")) else r["p_value"]
            lab = dg.evidence_label(ph)
            concl[metric] = (lab, r["estimate"])
            rows.append([esc(q), fmt.num(r["estimate"], 3, True), fmt.num(ph, 3), _ev(lab)])
        h2c = sr[(sr["hypothesis"] == "H2c") & sr["test"].str.startswith("OLS")]
        if not h2c.empty:
            r = h2c.iloc[0]
            lab = dg.evidence_label(r["p_value"])
            concl["H2c"] = (lab, r["estimate"])
            rows.append(["Dòng vốn ngoại vào nhóm vốn hóa lớn giải thích được D?", fmt.num(r["estimate"], 3, True),
                         fmt.num(r["p_value"], 3), _ev(lab)])
    md(table_html(["Câu hỏi: sau khi FTSE công bố nâng hạng (08/10/2025), so với 1 năm trước đó…", "Thay đổi", "p (Holm)", "Kết luận"],
                  rows, left=(0, 3)) if rows else "")
    reg = _regression(date)
    if reg.get("ok"):
        md('<div style="height:8px"></div>')
        rr = [[esc(x["label"]), colored(x["coef"], fmt.num(x["coef"], 3, True)), fmt.num(x["t"], 2, True), fmt.num(x["p"], 4),
               _ev(dg.evidence_label(x["p"]))] for x in reg["rows"]]
        md('<div style="font-weight:700;margin:6px 0 2px">Điều gì giải thích độ vênh giữa VN-Index và cổ phiếu điển hình?</div>')
        md(table_html(["Yếu tố", "Mức ảnh hưởng (điểm % D khi yếu tố tăng 1 độ lệch chuẩn)", "t", "p", "Kết luận"], rr, left=(0, 4)))
        st.caption(f"Hồi quy trên {reg['n']} phiên ({reg['from']:%d/%m/%Y} – {reg['to']:%d/%m/%Y}), sai số Newey–West, "
                   f"R² = {fmt.num(reg['r2'], 2)} (giải thích {fmt.num(reg['r2'] * 100, 0)}% biến động của D). "
                   "p < 0,05 → yếu tố có ảnh hưởng thật; p lớn → không có bằng chứng.")
        b = {x["var"]: x for x in reg["rows"]}
        big_ok = b["big_ret"]["p"] < 0.05
        nf_ok = b["big_nf"]["p"] < 0.05
        md(f'<div class="dx-concl"><b>Kết luận:</b> độ vênh D gắn với '
           + ("<b>diễn biến của nhóm vốn hóa lớn</b>" if big_ok else "các yếu tố khác")
           + (", <b>không phải</b> với việc khối ngoại mua/bán ròng ở nhóm này" if not nf_ok else " và cả dòng vốn ngoại ở nhóm này")
           + f" (p khối ngoại = {fmt.num(b['big_nf']['p'], 2)}). "
           + ("Sau công bố FTSE, mức tập trung đóng góp (CR5) tăng và vẫn có ý nghĩa khi đã kiểm soát độ tập trung tỷ trọng chỉ số. "
              if concl.get("CR5 – tập trung đóng góp · kiểm soát HHI tỷ trọng", ("",))[0] == "Có bằng chứng" else
              "Mức tập trung đóng góp sau công bố FTSE chưa có bằng chứng tăng khi đã kiểm soát độ tập trung tỷ trọng. ")
           + "Mô tả thống kê, không khẳng định quan hệ nhân quả.</div>")


TONE = {"pos": ("Tích cực", "#16A34A"), "neg": ("Tiêu cực", "#DC2626"), "neu": ("Trung tính", "#64748B")}


def _badge(lab: str, color: str) -> str:
    return f'<span class="dx-ev" style="background:{color}22;color:{color};border:1px solid {color}66">{esc(lab)}</span>'


def _tone(t: str) -> str:
    lab, c = TONE.get(t, TONE["neu"])
    return _badge(lab, c)


def _hist(date) -> pd.DataFrame:
    d = da.daily()
    return d[pd.to_datetime(d["trade_date"]) <= pd.Timestamp(date)].reset_index(drop=True)


def _diag_ctx(date) -> dict:
    from src.analytics import outlook, technical
    h = _hist(date)
    vni = h.set_index(pd.to_datetime(h["trade_date"]))["vni"].astype(float)
    return {"day": h.iloc[-1], "hist": h, "idx_hist": {"VN-Index": vni}, "vol_range": outlook.vol_range(vni),
            "regime": technical.market_state(h)}


def _rows_table(rows) -> str:
    return table_html(["Khía cạnh", "Số liệu", "Đọc kết quả", "Đánh giá", "Quy tắc"],
                      [[esc(r["name"]), esc(r["value"]), esc(r["reading"]), _tone(r["tone"]), esc(r["rule"])] for r in rows],
                      left=(0, 1, 2, 3, 4))


@safe_block("kết luận chẩn đoán")
def summary_block(ctx) -> None:
    from src.reports.chapters import market_recommendations
    rec = market_recommendations(ctx)
    md(f'<div class="dx-concl"><b>{esc(rec[0])}</b></div>')
    md("".join(f'<div style="font-size:14px;margin:6px 0;line-height:1.55">• {esc(t)}</div>' for t in rec[1:]))
    st.caption("Khuyến nghị ở cấp THỊ TRƯỜNG, suy ra từ chỉ báo theo quy tắc cố định (xem trang Phương pháp) – không chọn cổ phiếu, "
               "không phải khuyến nghị mua/bán.")


@safe_block("phân tích kỹ thuật")
def technical_block(ctx) -> None:
    from plotly.subplots import make_subplots
    from src.analytics import technical
    p = pal()
    t = technical.snapshot(ctx["hist"])
    md(_rows_table([r for r in ctx["regime"] if r.get("group") == "Kỹ thuật"]))
    c = t["close_series"].tail(160)
    m = t["macd_df"].reindex(c.index)
    r = t["rsi_series"].reindex(c.index)
    full = t["close_series"]
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.56, 0.22, 0.22], vertical_spacing=0.05,
                        subplot_titles=("VN-Index · MA20 · MA50 · hỗ trợ / kháng cự", "RSI(14) – vùng quá bán 30 / quá mua 70",
                                        "MACD(12, 26, 9) – histogram = MACD − tín hiệu"))
    fig.add_scatter(x=c.index, y=c, name="VN-Index", line=dict(color="#E2E8F0" if p["dark"] else "#0F1E33", width=1.8), row=1, col=1)
    fig.add_scatter(x=c.index, y=full.rolling(20).mean().reindex(c.index), name="MA20", line=dict(color="#F5B341", width=1.2),
                    row=1, col=1)
    fig.add_scatter(x=c.index, y=full.rolling(50).mean().reindex(c.index), name="MA50", line=dict(color="#818CF8", width=1.2),
                    row=1, col=1)
    for lv in t["supports"][:2]:
        fig.add_hline(y=lv, line=dict(color="#16A34A", dash="dash", width=1), annotation_text=f"hỗ trợ {fmt.num(lv, 0)}",
                      annotation_position="bottom left", row=1, col=1)
    for lv in t["resists"][:2]:
        fig.add_hline(y=lv, line=dict(color="#DC2626", dash="dash", width=1), annotation_text=f"kháng cự {fmt.num(lv, 0)}",
                      annotation_position="top left", row=1, col=1)
    fig.add_scatter(x=r.index, y=r, name="RSI(14)", line=dict(color="#38BDF8", width=1.3), row=2, col=1)
    for y in (30, 70):
        fig.add_hline(y=y, line=dict(color=p["muted"], dash="dot", width=1), row=2, col=1)
    fig.add_bar(x=m.index, y=m["hist"], name="Histogram MACD", opacity=0.55,
                marker_color=["#16A34A" if v >= 0 else "#DC2626" for v in m["hist"]], row=3, col=1)
    fig.add_scatter(x=m.index, y=m["macd"], name="MACD", line=dict(color="#F5B341", width=1.2), row=3, col=1)
    fig.add_scatter(x=m.index, y=m["signal"], name="Đường tín hiệu", line=dict(color="#818CF8", width=1.2), row=3, col=1)
    plot(charts._lay(fig, p, 600, legend=dict(orientation="h", y=-0.07, x=0), margin=dict(l=8, r=8, t=30, b=8)), "dx_tech_fig")


@safe_block("kịch bản")
def scenario_block(ctx) -> None:
    from src.analytics import technical
    t = technical.snapshot(ctx["hist"])
    md(table_html(["Kịch bản", "Điều kiện", "Ý nghĩa"],
                  [[f"<b>{esc(s['case'])}</b>", esc(s["cond"]), esc(s["meaning"])]
                   for s in technical.scenarios(t, ctx["vol_range"])], left=(0, 1, 2)))


def render() -> None:
    header("Chẩn đoán thị trường", "Phân tích kỹ thuật, cấu trúc dòng vốn và kịch bản theo dõi cho VN-Index")
    status_bar.render()
    st.markdown(DX_CSS, unsafe_allow_html=True)
    md('<div class="ffr-insight"><b>Chẩn đoán thị trường là gì?</b> Đánh giá sức khỏe, xu hướng và dòng tiền của thị trường. Trang '
       'đi theo thứ tự: <b>(1) phân tích kỹ thuật</b> – xu hướng, cấu trúc đỉnh/đáy, RSI, MACD, khối lượng; <b>(2) cấu trúc thị '
       'trường và dòng vốn</b> – lan tỏa, mức tập trung, khối ngoại; <b>(3) kịch bản theo dõi</b> với ngưỡng hỗ trợ/kháng cự; '
       'cuối trang là <b>góc nhìn phiên</b> chi tiết 5 bước. Toàn bộ tính từ dữ liệu SSI FastConnect V3.</div>')
    sess = da.sessions()
    date = st.selectbox("Phiên", sess[::-1], format_func=lambda d: f"📅 Phiên {d:%d/%m/%Y}", key="dx_date")
    ctx = _diag_ctx(date)
    with W.card("dx_sum"):
        W.title("Kết luận chẩn đoán và khuyến nghị cho thị trường", f"Phiên {date:%d/%m/%Y} · tổng hợp từ các khối bên dưới")
        summary_block(ctx)
    with W.card("dx_tech"):
        W.title("1 · Phân tích kỹ thuật", "Xu hướng (MA, cấu trúc đỉnh – đáy kiểu Dow) · động lượng (RSI, MACD) · khối lượng xác nhận")
        technical_block(ctx)
    with W.card("dx_struct"):
        W.title("2 · Cấu trúc thị trường và dòng vốn", "Lan tỏa · tập trung đóng góp · khối ngoại · biến động")
        md(_rows_table([r for r in ctx["regime"] if r.get("group") != "Kỹ thuật"]))
    link_series(date)
    with W.card("dx_sc"):
        W.title("3 · Kịch bản theo dõi", "Ngưỡng hỗ trợ/kháng cự từ đỉnh/đáy 20–250 phiên, MA và biên dao động EWMA")
        scenario_block(ctx)
    with W.card("dx_s"):
        W.title("4 · Góc nhìn phiên – chẩn đoán 5 bước",
                f"Phiên {date:%d/%m/%Y}: lan tỏa → ai tạo biến động → khối ngoại → phản ứng giá → watchlist")
        session_block(date)
        x = da.daily().set_index("trade_date").loc[date]
        md("".join(f'<div style="font-size:14px;margin:6px 0">• {esc(t)}</div>' for t in dg.implications(x)))
    with W.card("dx_r"):
        W.title("Giai đoạn FTSE đã thay đổi thị trường thế nào?",
                "Mỗi dòng một câu hỏi · Kết luận: Có bằng chứng (p < 0,05) / Bằng chứng yếu (p < 0,10) / Chưa đủ bằng chứng")
        research_block(date)
