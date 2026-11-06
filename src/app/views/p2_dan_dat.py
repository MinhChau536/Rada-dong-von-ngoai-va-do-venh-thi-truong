"""Trang 2 – Dẫn dắt & độ vênh (bước B4.6): thác nước C theo mã và ngành, chuỗi D có dải phân vị,
chỉ số loại trừ họ cổ phiếu, phân phối CR5, lịch loại phiên. Bộ lọc khoảng phiên."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import data_access as da
from src.app.components import charts, status_bar
from src.app.components.states import empty, safe_block
from src.app.components.ui import colored, header, kpi, md, pal, plot, section, table_html
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
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        names = top["symbol"].tolist() + ["Còn lại", "ε"]
        vals = top["C"].tolist() + [rest, day["eps"]]
        plot(charts.waterfall(names, vals, p), "p2_wf_stock")
        st.caption(f"Top 10 mã theo |C| + phần còn lại + sai số tái lập ε = ΔVN-Index {fmt.num(day['dI'], 2, True)} điểm.")
    with c2:
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
    section("Thác nước đóng góp điểm", f"Phiên {date:%d/%m/%Y}")
    waterfalls(date)
    d = da.daily()
    rng = d[d["trade_date"].between(lo, hi)]
    if rng.empty:
        empty("Khoảng phiên không có dữ liệu.")
        return
    section("Chuỗi điểm vênh D", "Dải phân vị 10–90 của 250 phiên TRƯỚC mỗi phiên · chấm đỏ = độ vênh cao")
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
    section("Chỉ số loại trừ một họ cổ phiếu", "Trả lời câu hỏi “nếu bỏ nhóm này thì chỉ số tăng hay giảm”")
    ex_family(lo, hi)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        section("Phân phối CR5", "Tỷ trọng 5 mã dẫn đầu trong tổng |đóng góp|")
        big = st.toggle(f"Chỉ phiên |ΔI| ≥ {get('events.h1b_dI_min')} điểm", key="p2_big")
        x = rng[rng["dI"].abs() >= get("events.h1b_dI_min")] if big else rng
        plot(charts.hist(x["CR5"] * 100, p, f"CR5 (%) · {len(x)} phiên", vline=50), "p2_cr5")
    with c2:
        section("Tần suất loại phiên", "Quy tắc mục 8.2")
        cnt = rng["session_type"].value_counts()
        md(table_html(["Loại phiên", "Số phiên", "Tỷ lệ"],
                      [[SESSION_TYPES[k], str(int(cnt.get(k, 0))), fmt.frac_pct(cnt.get(k, 0) / len(rng), 1)] for k in SESSION_TYPES],
                      left=(0,)))
    section("Lịch loại phiên", "Mỗi ô một phiên · màu theo loại")
    plot(charts.session_calendar(rng, p), "p2_cal")
    lead = da.table("leaders_daily")
    lead = lead[lead["trade_date"].between(lo, hi)]
    section("Mã xuất hiện nhiều nhất trong Top 5 dẫn dắt", "Trong khoảng phiên đã chọn")
    freq = lead.groupby(["symbol", "side"]).agg(n=("C", "size"), C=("C", "sum")).reset_index().sort_values("n", ascending=False).head(12)
    md(table_html(["Mã", "Chiều", "Số phiên trong Top 5", "Tổng đóng góp (điểm)"],
                  [[f'<span class="ffr-sym">{r.symbol}</span>', "Kéo lên" if r.side == "pos" else "Kéo xuống", str(r.n),
                    colored(r.C, fmt.num(r.C, 1, True))] for r in freq.itertuples()], left=(0, 1)))
