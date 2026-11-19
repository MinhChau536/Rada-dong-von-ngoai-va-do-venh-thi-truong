"""Trang 7 – Chất lượng dữ liệu (bước B11.1, B12.7): trạng thái nguồn SSI; nhật ký sự cố; độ đầy đủ theo phiên;
biểu đồ ε; đối chiếu độ rộng; luồng WebSocket SSI lưu trữ; đối chiếu luồng ↔ REST cuối phiên; nhật ký lỗi; xuất CSV."""
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


def stream_vs_rest() -> pd.DataFrame:
    """B12.7 – so tin cuối phiên của luồng WebSocket SSI (giá khớp cuối, khối ngoại lũy kế kênh room) với số liệu REST
    securitiesSummary cuối phiên, cho các mã có cả hai."""
    raw = da.table("raw_stream")
    if raw.empty:
        return pd.DataFrame()
    raw = raw[raw["channel"].isin(["trade", "room"])].sort_values("recv_ts")
    last = raw.groupby(["session_date", "symbol", "channel"]).tail(1)
    rows = {}
    for r in last.itertuples():
        try:
            pl = json.loads(r.payload)
        except ValueError:
            continue
        k = (pd.Timestamp(r.session_date), r.symbol)
        d = rows.setdefault(k, {"trade_date": k[0], "symbol": k[1]})
        if r.channel == "trade":
            d["ws_close"] = pl.get("price")
        else:
            d["ws_fb"], d["ws_fs"] = pl.get("buy_value"), pl.get("sell_value")
    n = pd.DataFrame(list(rows.values()))
    if n.empty:
        return n
    have = {pd.Timestamp(x) for x in da.sessions()}
    days = [pd.Timestamp(d) for d in n["trade_date"].unique() if pd.Timestamp(d) in have]
    if not days:
        return pd.DataFrame()
    s = pd.concat([da.stock_day(d)[["trade_date", "symbol", "close", "fb", "fs"]] for d in days])
    m = n.merge(s, on=["trade_date", "symbol"], how="inner")
    for c in ("ws_close", "ws_fb", "ws_fs"):
        if c not in m:
            m[c] = None
        m[c] = pd.to_numeric(m[c], errors="coerce")

    def cls(r):
        if pd.isna(r["close"]) or (pd.isna(r["ws_close"]) and pd.isna(r["ws_fb"])):
            return "Thiếu dữ liệu"
        price_ok = pd.isna(r["ws_close"]) or abs(r["ws_close"] - r["close"]) < 1e-6
        fb_ok = pd.isna(r["ws_fb"]) or abs(r["ws_fb"] - (r["fb"] or 0)) <= 0.02 * max(r["fb"] or 1, 1)
        if price_ok and fb_ok:
            return "Khớp"
        return "Lệch thời điểm (luồng dừng trước ATC / thỏa thuận cuối ngày)" if price_ok else "Lệch giá"
    m["kết quả"] = m.apply(cls, axis=1)
    return m


def render(embedded: bool = False) -> None:
    if not embedded:
        header("Chất lượng dữ liệu", "Minh bạch nguồn SSI FastConnect V3, độ đầy đủ, sai số tái lập và đối chiếu luồng ↔ REST")
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
    section("Trạng thái nguồn & nhật ký sự cố")
    c1, c2 = st.columns(2)
    with c1:
        ss = da.source_status()
        md(table_html(["Nguồn", "Trạng thái", "Lần ổn gần nhất", "Ghi chú"],
                      [[r.source, r.status, str(r.last_ok)[:19], r.message] for r in ss.itertuples()], left=(0, 1, 2, 3)))
    with c2:
        ev = da.table("source_events")
        if ev.empty:
            st.caption(f"Chưa có sự cố (quy tắc: luồng WebSocket SSI im lặng > {get('stream.silence_sec', 120)} giây trong phiên → ghi sự cố, báo Telegram).")
        else:
            md(table_html(["Thời điểm", "Nguồn", "Sự cố"], [[str(r.ts)[:19], r.from_source, r.reason]
                                                                  for r in ev.sort_values("ts", ascending=False).head(10).itertuples()],
                          left=(0, 1, 2)))
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        section("Độ đầy đủ theo phiên")
        if not comp.empty:
            plot(charts.line(comp.sort_values("trade_date").assign(v=lambda x: x["value"] * 100), "trade_date",
                             {"v": "Tỷ lệ đầy đủ (%)"}, p), "p7_comp")
    with c2:
        section("Sai số tái lập ε theo phiên (điểm)", "ε = ΔI − ΣC")
        plot(charts.line(d, "trade_date", {"eps": "ε"}, p), "p7_eps")
    section("Đối chiếu độ rộng với SSI", "Tự đếm − totalAdvanceStock/totalDeclineStock/totalNoChangeStock của indexSummary")
    if not br.empty:
        bad = br[br["status"] != "ok"].sort_values("trade_date", ascending=False)
        diff_basket = bad["detail"].fillna("").str.contains("khác rổ")
        comparable = br[~br.index.isin(bad[diff_basket].index)]
        ok_cmp = (comparable["status"] == "ok").mean() if len(comparable) else float("nan")
        st.caption(f"{len(br) - len(bad)}/{len(br)} phiên lệch ≤ {get('cleaning.breadth_tolerance')} mã "
                   f"({fmt.frac_pct((len(br) - len(bad)) / len(br), 1)}). Nguyên nhân chính của phần lệch: SSI đếm cả chứng chỉ quỹ, ETF và mã "
                   f"mới niêm yết, còn dự án chỉ đếm cổ phiếu thường có khớp lệnh – {int(diff_basket.sum())} phiên lệch do SSI đếm khác rổ "
                   f"(tổng số mã SSI khác tổng tự đếm). Chỉ xét {len(comparable)} phiên cùng rổ, tỷ lệ khớp là "
                   f"**{fmt.frac_pct(ok_cmp, 1)}**.")
        md(table_html(["Phiên", "Lệch lớn nhất", "Chi tiết"],
                      [[f"{pd.Timestamp(r.trade_date):%d/%m/%Y}", str(int(r.value)), r.detail] for r in br.sort_values("value", ascending=False).head(8).itertuples()],
                      left=(0, 2)))
    section("Luồng WebSocket SSI V3 có lưu trữ", "Chuẩn tối thiểu của đề: ≥ 1 luồng WebSocket có lưu trữ · mục tiêu ≥ 10 phiên, mất kết nối < 5 phút/phiên")
    ns, gaps = da.stream_stats(), da.stream_gaps()
    if ns.empty:
        empty("Chưa có tin luồng WebSocket nào được lưu. Bộ ghi chỉ nhận tin trong giờ giao dịch 08:55–15:05 (thứ Hai – thứ Sáu): "
              "từ nay app và bot tự bật bộ ghi khi được mở trong khung giờ này; hoặc chạy tay `python -m src.data.recorder_ssi`, "
              "hoặc để `python -m src.data.scheduler` chạy nền. Kết nối đã kiểm tra: đăng nhập và mở WebSocket SSI V3 thành công.")
    else:
        m = ns.merge(gaps, on="session_date", how="left") if not gaps.empty else ns
        md(table_html(["Phiên", "Nguồn", "Số tin", "Tin đầu", "Tin cuối", "Mất kết nối (phút)"],
                      [[f"{pd.Timestamp(r.session_date):%d/%m/%Y}", r.source, f"{r.n_msg:,}".replace(",", "."), str(r.first_ts)[11:19],
                        str(r.last_ts)[11:19], fmt.num(getattr(r, "gap_minutes", None), 1)] for r in m.itertuples()], left=(0, 1)))
    section("Đối chiếu luồng WebSocket ↔ REST cuối phiên", "Giá khớp cuối & khối ngoại mua lũy kế (kênh room) so với securitiesSummary")
    cmp_ = stream_vs_rest()
    if cmp_.empty:
        empty("Chưa có phiên nào có cả luồng WebSocket và số liệu REST cuối phiên.")
    else:
        st.dataframe(cmp_["kết quả"].value_counts().rename("số quan sát"))
        with st.expander("Chi tiết"):
            st.dataframe(cmp_, width="stretch")
    section("Nhật ký tải dữ liệu & lỗi")
    il = da.table("ingest_log")
    if il.empty:
        st.caption("Chưa có lần gọi API SSI nào được ghi.")
    else:
        st.dataframe(il.sort_values("ts", ascending=False).head(50), width="stretch")
    st.download_button("⬇️ Xuất bảng chất lượng (CSV)", q.to_csv(index=False).encode("utf-8-sig"),
                       file_name="data_quality_log.csv", mime="text/csv")
