"""Trang 2 – Dẫn dắt & độ vênh (bước B4.6): thác nước C theo mã và ngành, chuỗi D có dải phân vị,
chỉ số loại trừ họ cổ phiếu, phân phối CR5, lịch loại phiên. Bộ lọc khoảng phiên."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from src.app import data_access as da
from src.analytics import narrative
from src.app.components import charts, status_bar
from src.app.components import widgets as W
from src.app.components.states import empty, safe_block
from src.app.components.ui import colored, esc, header, kpi, md, pal, plot, table_html
from src.common import fmt
from src.common.config import get
from src.finance.breadth import SESSION_TYPES


def _range_filter(key: str):
    sess = da.sessions()
    lo, hi = st.select_slider("Khoảng phiên", options=sess, value=(sess[max(0, len(sess) - 250)], sess[-1]),
                              format_func=lambda d: f"{d:%d/%m/%Y}", key=key)
    return lo, hi


@safe_block("thác nước đóng góp")
def waterfalls(date) -> None:
    p = pal()
    st_day = da.stock_day(date)
    st_day = st_day[st_day["is_valid"]].copy()
    day = da.daily().set_index("trade_date").loc[date]
    top = st_day.reindex(st_day["C"].abs().sort_values(ascending=False).index).head(10)
    rest = st_day["C"].sum() - top["C"].sum()
    t1, t2 = st.tabs(["Theo mã", "Theo ngành"])
    with t1:
        names = top["symbol"].tolist() + ["Còn lại", "ε"]
        vals = top["C"].tolist() + [rest, day["eps"]]
        plot(charts.waterfall(names, vals, p), "p2_wf_stock")
        st.caption(f"Top 10 mã theo |C| + phần còn lại + sai số tái lập ε = ΔVN-Index {fmt.num(day['dI'], 2, True)} điểm.")
    with t2:
        sec = st_day.groupby("sector")["C"].sum().sort_values(key=abs, ascending=False)
        plot(charts.waterfall(sec.index.tolist() + ["ε"], sec.tolist() + [day["eps"]], p), "p2_wf_sector")
        st.caption("Đóng góp theo ngành (cộng C của các mã trong ngành).")


@safe_block("chỉ số loại trừ họ cổ phiếu")
def ex_family(lo, hi) -> None:
    p = pal()
    fams = sorted(da.groups(None, "family")["group_name"].unique())
    fam = st.selectbox("Họ cổ phiếu cần loại trừ", fams, index=fams.index("VINGROUP") if "VINGROUP" in fams else 0, key="p2_fam")
    g = da.groups(None, "family")
    g = g[(g["group_name"] == fam) & g["trade_date"].between(lo, hi)].set_index("trade_date")
    d = da.daily().set_index("trade_date").loc[lo:hi]
    actual = (1 + d["r_vni_pct"] / 100).cumprod() * 100
    ex = (1 + g["index_ex_group_ret_pct"].reindex(d.index).fillna(0) / 100).cumprod() * 100
    df = pd.DataFrame({"trade_date": d.index, "VN-Index": actual.values, f"VN-Index loại trừ {fam}": ex.values})
    plot(charts.line(df, "trade_date", {"VN-Index": "VN-Index (chuẩn hóa 100)", f"VN-Index loại trừ {fam}": f"Loại trừ {fam}"}, p),
         "p2_exfam")
    a, b = actual.iloc[-1] - 100, ex.iloc[-1] - 100
    md(f'<div class="ffr-insight">Trong khoảng đã chọn, VN-Index {fmt.pct(a)}; nếu loại trừ nhóm {fam}, chỉ số {fmt.pct(b)}. '
       f'Nhóm {fam} đóng góp {fmt.num(g["C"].sum(), 1, True)} điểm. Chỉ số loại trừ nhóm g = I(t−1) + Σ_(i∉g) C_i,t.</div>')


@safe_block("bảng đóng góp chi tiết")
def contrib_table(date) -> None:
    s = da.stock_day(date)
    s = s[s["is_valid"]]
    tot = s["C"].abs().sum() or 1
    top = s.reindex(s["C"].abs().sort_values(ascending=False).index).head(15)
    rows = [[f'<span class="ffr-sym">{r.symbol}</span>', f'<span style="white-space:nowrap">{esc(r.sector)}</span>', fmt.price(r.close), colored(r.ret, fmt.pct(r.ret * 100)),
             fmt.num(r.w * 100, 2, False, "%"), colored(r.C, fmt.num(r.C, 2, True)), fmt.num(abs(r.C) / tot * 100, 1, False, "%"),
             colored(r.net_flow, fmt.num(r.net_flow / 1e9, 1, True))] for r in top.itertuples()]
    md(table_html(["Mã", "Ngành", "Giá", "%", "Tỷ trọng VNI", "Đóng góp (điểm)", "% tổng |C|", "NN ròng (tỷ)"], rows, left=(0, 1)))
    st.caption("Tỷ trọng VNI = vốn hóa đầu phiên / tổng vốn hóa rổ VN-Index. % tổng |C| = mức ảnh hưởng của mã trong tổng "
               "đóng góp tuyệt đối của phiên.")


@safe_block("đóng góp theo họ và ngành")
def group_table(date) -> None:
    p = pal()
    g = da.groups(date)
    x = da.daily().set_index("trade_date").loc[date]
    fam = g[g["group_type"] == "family"].sort_values("C", ascending=False)
    sec = g[g["group_type"] == "sector"]
    sec = sec.reindex(sec["C"].abs().sort_values(ascending=False).index).head(8)
    names = {"VINGROUP": "Nhóm Vingroup", "MASAN": "Nhóm Masan", "GELEX": "Nhóm Gelex", "HOAPHAT": "Hòa Phát"}
    rows = []
    for kind, df in (("Họ", fam), ("Ngành", sec)):
        for r in df.itertuples():
            ex = (colored(r.index_ex_group_ret_pct, fmt.pct(r.index_ex_group_ret_pct))
                  if pd.notna(r.index_ex_group_ret_pct) else "—")              # có cho cả họ cổ phiếu và ngành
            rows.append([f"<b>{esc(names.get(r.group_name, r.group_name))}</b>", kind, str(int(r.n)),
                         colored(r.C, fmt.num(r.C, 2, True)), colored(r.ret_eq, fmt.pct(r.ret_eq * 100)), ex])
    md(table_html(["Nhóm", "Loại", "Số mã", "Đóng góp (điểm)", "Lợi suất bình quân", "VN-Index nếu loại trừ"], rows, left=(0, 1)))
    st.caption(f"VN-Index thực tế phiên này {fmt.pct(x['r_vni_pct'])}. Lợi suất bình quân = trung bình đồng trọng số các mã trong nhóm. "
               "VN-Index nếu loại trừ = mức thay đổi của chỉ số khi bỏ đóng góp điểm của nhóm (ΣC các mã còn lại / VN-Index phiên trước); "
               "càng xa mức thực tế thì nhóm càng chi phối chỉ số.")


@safe_block("thống kê độ vênh theo kỳ")
def div_stats(date) -> None:
    d = da.daily()
    h = d[d["trade_date"] <= date]
    from src.app.views.p_chan_doan import _extras
    ex = _extras(date).set_index("trade_date")
    rows = []
    for n in (5, 20, 60, 250):
        x = h.tail(n)
        hw = ex["hhi_w"].reindex(pd.to_datetime(x["trade_date"])).mean()
        narrow = x["session_type"].isin(["narrow_up", "narrow_down"]).mean() * 100
        rows.append([f"<b>{n} phiên</b>", fmt.num(x["D"].mean(), 3, True), fmt.num(x["D"].median(), 3, True),
                     fmt.num((x["D"] > 0).mean() * 100, 0, False, "%"), str(int(x["high_divergence"].sum())),
                     fmt.num(x["CR5"].mean() * 100, 0, False, "%"), fmt.num(x["pct_up"].mean(), 0, False, "%"),
                     fmt.num(narrow, 0, False, "%"), f"{fmt.num(hw, 3)} (~{fmt.num(1 / hw if hw else np.nan, 0)} mã)",
                     fmt.num(x["eps"].abs().median(), 3)])
    md(table_html(["Kỳ", "D trung bình (đ.%)", "D trung vị", "% phiên D > 0", "Phiên độ vênh cao", "CR5 TB",
                   "% mã tăng TB", "% phiên thiếu lan tỏa", "HHI tỷ trọng chỉ số", "Trung vị |ε|"], rows, left=(0,)))
    st.caption("HHI tỷ trọng = Σw² của rổ VN-Index (~N mã = số mã hiệu dụng 1/HHI). CR5 tăng cùng lúc HHI tỷ trọng tăng "
               "nghĩa là sự tập trung đến từ việc vài mã phình tỷ trọng, không nhất thiết do hành vi thị trường thay đổi.")
    st.caption("D > 0: VN-Index tăng nhiều hơn (hoặc giảm ít hơn) cổ phiếu trung vị – chỉ số được kéo bởi nhóm vốn hóa lớn.")


def render() -> None:
    header("Dẫn dắt & độ vênh", "Ai đang kéo VN-Index, và chỉ số có phản ánh số đông cổ phiếu không")
    status_bar.render()
    p = pal()
    sess = da.sessions()
    c1, c2 = st.columns([1, 3])
    with c1:
        date = st.selectbox("Phiên phân rã", sess[::-1], format_func=lambda d: f"{d:%d/%m/%Y}", key="p2_date")
    with c2:
        lo, hi = _range_filter("p2_range")
    D = W.load(date)
    c1, c2 = st.columns([1.25, 1], gap="small")
    with c1, W.card("p2_wf"):
        W.title("Thác nước đóng góp điểm", f"Phiên {date:%d/%m/%Y} · ΣC + ε = ΔVN-Index")
        waterfalls(date)
    with c2, W.card("p2_lead"):
        W.w_leaders(D)
        md(f'<div class="ffr-insight" style="margin-top:8px"><b>Nhận định theo quy tắc</b><br>'
           f'{esc(narrative.market_summary(D["day"], D["leaders"]))}</div>')
    c1, c2 = st.columns([1.35, 1], gap="small")
    with c1, W.card("p2_ctab"):
        W.title("Bảng đóng góp điểm chi tiết", f"Top 15 mã theo |đóng góp| · phiên {date:%d/%m/%Y}")
        contrib_table(date)
    with c2, W.card("p2_gtab"):
        W.title("Đóng góp theo họ cổ phiếu và ngành", f"Phiên {date:%d/%m/%Y}")
        group_table(date)
    d = da.daily()
    rng = d[d["trade_date"].between(lo, hi)]
    if rng.empty:
        empty("Khoảng phiên không có dữ liệu.")
        return
    c1, c2 = st.columns([2, 1], gap="small")
    with c1, W.card("p2_d"):
        W.title("Chuỗi điểm vênh D", "D = %VN-Index − % cổ phiếu trung vị · dải phân vị 10–90 của 250 phiên trước · chấm đỏ = độ vênh cao")
        plot(charts.d_series(d[d["trade_date"] <= hi].tail(len(rng) + 250).pipe(lambda x: x[x["trade_date"] >= lo]), p), "p2_d")
        meta = da.table("pipeline_meta")
        k = st.columns(4)
        for c, h in zip(k, [kpi("D trung bình", fmt.num(rng["D"].mean(), 3, True, " đ.%")),
                            kpi("Số phiên độ vênh cao", str(int(rng["high_divergence"].sum()))),
                            kpi("Trung vị |ε|", fmt.num(rng["eps"].abs().median(), 3, False, " điểm"),
                                p["up"] if rng["eps"].abs().median() < get("contribution.eps_median_target") else p["down"]),
                            kpi("Hệ số hiệu chỉnh k", fmt.num(meta["scale_k"].iloc[0] if not meta.empty else 1, 4))]):
            with c:
                md(h)
    with c2, W.card("p2_br"):
        W.w_breadth(D)
    from src.app.views.p_chan_doan import link_series
    link_series(date)                                        # nối sang khối ngoại và nhóm FTSE
    with W.card("p2_dstat"):
        W.title("Thống kê độ vênh và lan tỏa theo kỳ", f"Tính đến phiên {date:%d/%m/%Y}")
        div_stats(date)
    with W.card("p2_ex"):
        W.title("Chỉ số loại trừ một họ cổ phiếu", "Nếu bỏ nhóm này thì chỉ số tăng hay giảm")
        ex_family(lo, hi)
    c1, c2 = st.columns(2, gap="small")
    with c1, W.card("p2_cr5"):
        W.title("Phân phối CR5", "Tỷ trọng 5 mã dẫn đầu trong tổng |đóng góp|")
        big = st.toggle(f"Chỉ phiên |ΔI| ≥ {get('events.h1b_dI_min')} điểm", key="p2_big")
        x = rng[rng["dI"].abs() >= get("events.h1b_dI_min")] if big else rng
        plot(charts.hist(x["CR5"] * 100, p, f"CR5 (%) · {len(x)} phiên", vline=50), "p2_cr5")
    with c2, W.card("p2_types"):
        W.title("Loại phiên", "Quy tắc mục 8.2: dấu lợi suất VN-Index × dấu AD")
        t1, t2 = st.tabs(["Tần suất", "Lịch theo phiên"])
        with t1:
            cnt = rng["session_type"].value_counts()
            md(table_html(["Loại phiên", "Số phiên", "Tỷ lệ"],
                          [[SESSION_TYPES[k], str(int(cnt.get(k, 0))), fmt.frac_pct(cnt.get(k, 0) / len(rng), 1)] for k in SESSION_TYPES],
                          left=(0,)))
        with t2:
            plot(charts.session_calendar(rng, p), "p2_cal")
    lead = da.table("leaders_daily")
    lead = lead[lead["trade_date"].between(lo, hi)]
    with W.card("p2_freq"):
        W.title("Mã xuất hiện nhiều nhất trong Top 5 dẫn dắt", f"{lo:%d/%m/%Y} – {hi:%d/%m/%Y}")
        freq = lead.groupby(["symbol", "side"]).agg(n=("C", "size"), C=("C", "sum")).reset_index().sort_values("n", ascending=False).head(12)
        md(table_html(["Mã", "Chiều", "Số phiên trong Top 5", "Tổng đóng góp (điểm)"],
                      [[f'<span class="ffr-sym">{r.symbol}</span>', "Kéo lên" if r.side == "pos" else "Kéo xuống", str(r.n),
                        colored(r.C, fmt.num(r.C, 1, True))] for r in freq.itertuples()], left=(0, 1)))
