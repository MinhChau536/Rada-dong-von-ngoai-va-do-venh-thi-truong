"""Trang 7 – Chất lượng dữ liệu (bước B11.1, B12.7): trạng thái SSI/NEO; lịch sử chuyển nguồn; độ đầy đủ theo phiên;
biểu đồ ε; đối chiếu độ rộng; đối chiếu SSI–NEO; luồng NEO lưu trữ; nhật ký lỗi; xuất CSV."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.app import data_access as da
from src.app.components import charts, status_bar
from src.app.components.states import empty
from src.app.components.ui import header, kpi, md, pal, plot, section, table_html
from src.common import fmt
from src.common.config import get


def ssi_neo_compare() -> pd.DataFrame:
    """B12.7 – so giá đóng cửa (tin stockInfo cuối phiên của NEO) với SSI cho các phiên có cả hai nguồn."""
    neo = da.table("raw_stream_neo")
    if neo.empty:
        return pd.DataFrame()
    neo = neo[neo["channel"] == "stockInfo"].sort_values("recv_ts").groupby(["session_date", "symbol"]).tail(1)
    rows = []
    for r in neo.itertuples():
        try:
            pl = json.loads(r.payload)
        except ValueError:
            continue
        rows.append({"trade_date": pd.Timestamp(r.session_date), "symbol": r.symbol, "neo_close": pl.get("closePrice"),
                     "neo_fb": pl.get("foreignBuyValue"), "neo_ts": pd.Timestamp(r.recv_ts)})
    n = pd.DataFrame(rows)
    if n.empty:
        return n
    s = pd.concat([da.stock_day(d)[["trade_date", "symbol", "close", "fb"]] for d in n["trade_date"].unique()])
    m = n.merge(s, on=["trade_date", "symbol"], how="left")

    def cls(r):
        if pd.isna(r["close"]) or pd.isna(r["neo_close"]):
            return "Thiếu dữ liệu"
        if abs(r["neo_close"] - r["close"]) < 1e-6:
            return "Khớp" if abs((r["neo_fb"] or 0) - (r["fb"] or 0)) <= 0.02 * max(r["fb"] or 1, 1) else "Lệch thời điểm"
        return "Khác phạm vi / lệch"
    m["kết quả"] = m.apply(cls, axis=1)
    return m


def render() -> None:
    header("Chất lượng dữ liệu", "Minh bạch nguồn, độ đầy đủ, sai số tái lập và đối chiếu chéo SSI–NEO")
    status_bar.render()
    p = pal()
    q = da.table("data_quality_log")
    d = da.daily()
    meta = da.table("pipeline_meta")
    comp = q[q["check_name"] == "completeness"]
    br = q[q["check_name"] == "breadth_check"]
    k = st.columns(5)
    eps_med = d["eps"].abs().median()
    br_ok = (br["status"] == "ok").mean() if not br.empty else float("nan")
    for c, h in zip(k, [kpi("Số phiên trong kho", str(len(d))),
                        kpi("Tỷ lệ đầy đủ toàn mẫu", fmt.frac_pct(comp["value"].mean() if not comp.empty else None, 2),
                            p["up"] if not comp.empty and comp["value"].mean() >= 0.98 else p["down"], "mục tiêu ≥ 98%"),
                        kpi("Trung vị |ε|", fmt.num(eps_med, 3, False, " điểm"), p["up"] if eps_med < 0.5 else p["down"],
                            "mục tiêu < 0,5 điểm"),
                        kpi("Độ rộng khớp SSI (≤ 2 mã)", fmt.frac_pct(br_ok, 1), p["up"] if br_ok >= .95 else p["down"], "mục tiêu ≥ 95% phiên"),
                        kpi("Mẫu số nf", str(meta["denominator"].iloc[0]) if not meta.empty else "—", None,
                            "khớp lệnh" if not meta.empty and meta["denominator"].iloc[0] == "match" else "khớp + thỏa thuận")]):
        with c:
            md(h)
    section("Trạng thái nguồn & lịch sử chuyển nguồn")
    c1, c2 = st.columns(2)
    with c1:
        ss = da.source_status()
        md(table_html(["Nguồn", "Trạng thái", "Lần ổn gần nhất", "Ghi chú"],
                      [[r.source, r.status, str(r.last_ok)[:19], r.message] for r in ss.itertuples()], left=(0, 1, 2, 3)))
    with c2:
        ev = da.table("source_events")
        if ev.empty:
            st.caption("Chưa có sự kiện chuyển nguồn (quy tắc: SSI lỗi 3 lần hoặc im lặng > 120 giây → NEO; SSI ổn định 5 phút → quay lại).")
        else:
            md(table_html(["Thời điểm", "Từ", "Sang", "Lý do"], [[str(r.ts)[:19], r.from_source, r.to_source, r.reason]
                                                                  for r in ev.sort_values("ts", ascending=False).head(10).itertuples()],
                          left=(0, 1, 2, 3)))
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        section("Độ đầy đủ theo phiên")
        if not comp.empty:
            plot(charts.line(comp.sort_values("trade_date").assign(v=lambda x: x["value"] * 100), "trade_date",
                             {"v": "Tỷ lệ đầy đủ (%)"}, p), "p7_comp")
    with c2:
        section("Sai số tái lập ε theo phiên (điểm)", "ε = ΔI − ΣC")
        plot(charts.line(d, "trade_date", {"eps": "ε"}, p), "p7_eps")
    section("Đối chiếu độ rộng với SSI", "Tự đếm − Advances/Declines/NoChanges của DailyIndex")
    if not br.empty:
        bad = br[br["status"] != "ok"].sort_values("trade_date", ascending=False)
        st.caption(f"{len(br) - len(bad)}/{len(br)} phiên lệch ≤ {get('cleaning.breadth_tolerance')} mã.")
        md(table_html(["Phiên", "Lệch lớn nhất", "Chi tiết"],
                      [[f"{pd.Timestamp(r.trade_date):%d/%m/%Y}", str(int(r.value)), r.detail] for r in br.sort_values("value", ascending=False).head(8).itertuples()],
                      left=(0, 2)))
    section("Luồng NEO WebSocket có lưu trữ", "Chuẩn tối thiểu của đề: ≥ 1 luồng WebSocket có lưu trữ · mục tiêu ≥ 10 phiên, mất kết nối < 5 phút/phiên")
    ns, gaps = da.neo_stream_stats(), da.neo_gaps()
    if ns.empty:
        empty("Chưa có tin NEO – chạy `python -m src.data.recorder_neo` trong giờ giao dịch.")
    else:
        m = ns.merge(gaps, on="session_date", how="left") if not gaps.empty else ns
        md(table_html(["Phiên", "Nguồn", "Số tin", "Tin đầu", "Tin cuối", "Mất kết nối (phút)"],
                      [[f"{pd.Timestamp(r.session_date):%d/%m/%Y}", r.source, f"{r.n_msg:,}".replace(",", "."), str(r.first_ts)[11:19],
                        str(r.last_ts)[11:19], fmt.num(getattr(r, "gap_minutes", None), 1)] for r in m.itertuples()], left=(0, 1)))
    section("Đối chiếu SSI–NEO", "Giá đóng cửa & khối ngoại mua của mã có cả hai nguồn – phân loại khớp / lệch thời điểm / khác phạm vi / thiếu")
    cmp_ = ssi_neo_compare()
    if cmp_.empty:
        empty("Chưa có phiên nào có cả hai nguồn.")
    else:
        st.dataframe(cmp_["kết quả"].value_counts().rename("số quan sát"))
        with st.expander("Chi tiết"):
            st.dataframe(cmp_, width="stretch")
    section("Nhật ký tải dữ liệu & lỗi")
    il = da.table("ingest_log")
    if il.empty:
        st.caption("Chưa có lần gọi API (chế độ dữ liệu mẫu không gọi SSI/NEO).")
    else:
        st.dataframe(il.sort_values("ts", ascending=False).head(50), width="stretch")
    st.download_button("⬇️ Xuất bảng chất lượng (CSV)", q.to_csv(index=False).encode("utf-8-sig"),
                       file_name="data_quality_log.csv", mime="text/csv")
