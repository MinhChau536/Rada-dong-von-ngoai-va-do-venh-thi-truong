"""Trang Backtest: gom mọi kiểm chứng trên dữ liệu lịch sử vào một chỗ.

1. Cảnh báo – chống trùng (alerts.backtest): chạy lại quy tắc trên N phiên, 4 lần/ngày, đo số tin thực sự gửi.
2. Cảnh báo – giá trị dự báo (alerts.predictive): VN-Index sau phiên có tín hiệu so với phiên thường.
3. Danh mục watchlist – walk-forward: tái cân bằng hàng tháng chỉ bằng dữ liệu quá khứ, so với VN-Index.
4. Biên dao động VN-Index (EWMA) – tỷ lệ phiên thực tế nằm trong biên 68%/90% đã công bố trước.
"""
from __future__ import annotations

import subprocess
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics import outlook
from src.analytics import portfolio as P
from src.analytics import watchlist_impact as wi
from src.app import data_access as da
from src.app.components import charts, status_bar
from src.app.components.states import empty
from src.app.components.ui import colored, esc, header, kpi, kpi_row, md, pal, plot, section, table_html
from src.app.views import p5_portfolio
from src.common import fmt
from src.common.config import ROOT, get

ALERT_NAMES = {"index_concentrated": "1 · Ít mã dẫn dắt", "high_divergence": "2 · Độ vênh cao",
               "foreign_market": "3 · Khối ngoại toàn sàn", "wl_foreign": "4 · WL dòng vốn bất thường",
               "wl_deviation": "5 · WL lệch thị trường", "wl_leader": "6 · WL trong nhóm dẫn dắt",
               "wl_room": "7 · Room sắp cạn", "system_failover": "8 · Sự cố nguồn"}


def _pc(v, d: int = 1) -> str:
    return fmt.pct(None if v is None or pd.isna(v) else v * 100, d, sign=False)


def _rerun(code: str, label: str) -> None:
    """Chạy lại trong tiến trình riêng (ghi vào kho DuckDB không xung đột kết nối đọc của giao diện)."""
    with st.spinner(f"Đang chạy lại {label}…"):
        r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, timeout=900,
                           encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode == 0:
        st.toast(f"Đã chạy lại {label}", icon="✅")
        da.clear_cache()
        st.rerun()
    else:
        busy = "lock" in r.stderr.lower() or "being used" in r.stderr.lower()
        st.error("Kho dữ liệu đang được cập nhật – thử lại sau ít phút." if busy else f"Lỗi: {r.stderr.strip()[-400:]}")


# ── 1. chống trùng ────────────────────────────────────────────────────────────
def _tab_dedup(p) -> None:
    al = da.table("alert_log")
    bt = al[al["mode"] == "backtest"] if not al.empty else al
    c1, c2 = st.columns([3, 1])
    c1.caption(f"Mỗi phiên đánh giá quy tắc 4 lần (10:00, 10:15, 11:00, 14:45) như khi chạy thật; cooldown "
               f"{get('alerts.cooldown_min')} phút, tối đa {get('alerts.max_market_per_day')} cảnh báo thị trường/ngày.")
    if c2.button("▶ Chạy lại", key="bt_dedup", width="stretch",
                 help=f"Chạy lại {get('alerts.backtest_sessions', 60)} phiên gần nhất với ngưỡng hiện tại trong settings.yaml"):
        _rerun("from src.analytics import alerts; alerts.backtest()", "backtest cảnh báo")
    if bt.empty:
        empty("Chưa có kết quả – bấm “Chạy lại”.")
        return
    kept = bt[bt["status"] == "simulated"]
    days = sorted(bt["trade_date"].unique())
    mkt = kept[kept["priority"] != "system"]
    per_day = mkt.groupby("trade_date").size().reindex(days, fill_value=0)
    lim = int(get("alerts.max_market_per_day", 3))
    kpi_row([kpi("Số phiên", str(len(days)), None, f"{pd.Timestamp(days[0]):%d/%m/%Y} → {pd.Timestamp(days[-1]):%d/%m/%Y}"),
             kpi("Lượt kích hoạt thô", fmt.num(len(bt), 0), None, "trước chống trùng"),
             kpi("Thực sự gửi", fmt.num(len(kept), 0), p["accent"], f"giữ {_pc(len(kept) / len(bt), 0)}"),
             kpi("Chặn do trùng", fmt.num(int((bt['status'] == 'suppressed_duplicate').sum()), 0), None, "cooldown"),
             kpi("Chặn do giới hạn", fmt.num(int((bt['status'] == 'suppressed_limit').sum()), 0), None, f"≤ {lim}/ngày"),
             kpi("Trung bình/ngày", fmt.num(per_day.mean(), 2), p["up"] if per_day.max() <= lim else p["down"],
                 f"tối đa {int(per_day.max())}/ngày")])
    g1, g2 = st.columns([1.6, 1], gap="medium")
    with g1:
        k = kept.assign(name=kept["alert_type"].map(ALERT_NAMES).fillna(kept["alert_type"]))
        tab = k.groupby(["trade_date", "name"]).size().unstack(fill_value=0).reindex(days, fill_value=0)
        fig = go.Figure([go.Bar(x=tab.index, y=tab[c], name=c) for c in tab.columns])
        fig.add_hline(y=lim, line_dash="dot", line_color="#DC2626", annotation_text=f"giới hạn thị trường {lim}/ngày")
        fig.update_layout(barmode="stack", title="Cảnh báo được gửi mỗi phiên, theo loại")
        plot(charts._lay(fig, p, 340), "bt_dedup_bar")
    with g2:
        s = bt.assign(name=bt["alert_type"].map(ALERT_NAMES).fillna(bt["alert_type"])).groupby(["name", "status"]).size().unstack(fill_value=0)
        rows = [[esc(n), str(int(r.get("simulated", 0))), str(int(r.get("suppressed_duplicate", 0))),
                 str(int(r.get("suppressed_limit", 0)))] for n, r in s.iterrows()]
        md(table_html(["Loại", "Gửi", "Chặn trùng", "Chặn giới hạn"], rows, left=(0,)))
    with st.expander("Nhật ký chi tiết (40 dòng gần nhất)"):
        a = bt.sort_values("ts", ascending=False).head(40)
        md(table_html(["Thời điểm", "Quy tắc", "Mã", "Ưu tiên", "Trạng thái", "Nội dung"],
                      [[pd.Timestamp(r.ts).strftime("%d/%m %H:%M"), str(r.rule_no), r.symbol or "—", r.priority, r.status,
                        esc(r.message)] for r in a.itertuples()], left=(0, 1, 2, 3, 4, 5)))


# ── 2. giá trị dự báo ─────────────────────────────────────────────────────────
def _tab_predictive(p) -> None:
    pr = da.table("alert_predictive")
    c1, c2 = st.columns([3, 1])
    c1.caption("Tín hiệu phiên t chỉ dùng dữ liệu tới t (không nhìn trước). Lợi suất sau tín hiệu nhân với hướng tín hiệu "
               "(+1 khi chỉ số tăng / khối ngoại mua ròng) rồi so với các phiên không có tín hiệu.")
    if c2.button("▶ Chạy lại", key="bt_pred", width="stretch"):
        _rerun("from src.analytics import alerts; alerts.predictive()", "đánh giá dự báo")
    if pr.empty:
        empty("Chưa có kết quả – bấm “Chạy lại”.")
        return
    st.caption(f"Toàn bộ lịch sử: {int(pr['sessions'].iat[0])} phiên ({pr['from'].iat[0]} → {pr['to'].iat[0]}).")
    main = pr[pr["horizon"].isin(["t+1", "t+1…t+5"]) & pr["mean_base_pct"].notna()]
    if not main.empty:
        fig = go.Figure()
        for h, col in (("t+1", p["accent"]), ("t+1…t+5", "#F59E0B")):
            x = main[main["horizon"] == h]
            fig.add_trace(go.Bar(y=x["rule"], x=x["mean_signal_pct"], name=f"Sau tín hiệu {h}", orientation="h", marker_color=col))
            fig.add_trace(go.Scatter(y=x["rule"], x=x["mean_base_pct"], name=f"Phiên thường {h}", mode="markers",
                                     marker=dict(symbol="line-ns-open", size=18, color=col, line=dict(width=3))))
        fig.update_layout(barmode="group", title="Lợi suất VN-Index trung bình sau tín hiệu (%, đã nhân hướng) – vạch = phiên thường",
                          yaxis=dict(autorange="reversed"))
        plot(charts._lay(fig, p, 380), "bt_pred_bar")

    def _p(v):
        if v is None or pd.isna(v):
            return "–"
        s = "<0,001" if v < 0.001 else f"{v:.3f}".replace(".", ",")
        return f"<b style='color:{p['up']}'>{s}</b>" if v < 0.05 else s

    rows = [[esc(r.rule), esc(r.horizon), str(int(r.n_signal)),
             "–" if pd.isna(r.mean_signal_pct) else colored(r.mean_signal_pct, fmt.num(r.mean_signal_pct, 3, True)),
             "–" if pd.isna(r.mean_base_pct) else fmt.num(r.mean_base_pct, 3, True),
             "–" if pd.isna(r.hit_rate) else f"{_pc(r.hit_rate, 0)}", "–" if pd.isna(r.base_up_rate) else f"{_pc(r.base_up_rate, 0)}",
             _p(r.welch_p), _p(r.mw_p)] for r in pr.itertuples()]
    md(table_html(["Quy tắc", "Kỳ", "n tín hiệu", "TB sau tín hiệu (%)", "TB phiên thường (%)", "Cùng hướng", "Tăng (thường)",
                   "p Welch", "p Mann–Whitney"], rows, left=(0, 1)))
    st.caption("p < 0,05 tô đậm. Lũy kế 5 phiên chồng lấp nên p chỉ mang tính tham khảo. Với 'ΔD phiên t+1', "
               "'Cùng hướng' = tỷ lệ độ vênh thu hẹp phiên sau. Đây là đánh giá mô tả, không phải chiến lược giao dịch.")


# ── 3. danh mục ───────────────────────────────────────────────────────────────
def _tab_portfolio(p, date) -> None:
    wl = wi.get_watchlist()
    if len(wl) < 2:
        empty("Cần ít nhất 2 mã trong Watchlist để kiểm chứng danh mục.")
        return
    profs = P.profiles()
    c1, c2, c3 = st.columns([2, 1.2, 2.5])
    choice = c1.segmented_control("Khẩu vị rủi ro", list(profs), default="Cân bằng", key="bt_prof") or "Cân bằng"
    lb = c2.selectbox("Dữ liệu ước lượng", list(p5_portfolio.LOOKBACKS), index=1, key="bt_lb")
    pf = profs[choice]
    c3.caption(f"Danh mục: **{', '.join(wl)}** · biến động mục tiêu ≤ {_pc(pf.target_vol, 0)}/năm · trần {_pc(pf.max_weight, 0)}/mã · "
               f"{get('portfolio.backtest_months', 24)} tháng gần nhất. Đầu mỗi tháng tối ưu lại chỉ bằng dữ liệu trước đó, "
               f"giữ số cổ phiếu tới tháng sau; **đã trừ chi phí {_pc(float(get('portfolio.cost_per_turnover', 0.0025)), 2)} "
               "trên doanh số tái cân bằng**."
               + (f" Trần thực dùng {_pc(P.effective_cap(pf.max_weight, len(wl)), 0)}/mã vì danh mục chỉ có {len(wl)} mã "
                  "(trần thấp hơn chỉ còn nghiệm chia đều)." if P.effective_cap(pf.max_weight, len(wl)) > pf.max_weight else ""))
    p5_portfolio.backtest_block(wl, date, p5_portfolio.LOOKBACKS[lb], pf.max_weight, pf.target_vol, key="bt_pf")


# ── 4. biên dao động ──────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _band_history(lam: float, start: str):
    ih = da.index_hist("VNINDEX")
    c = ih.assign(trade_date=pd.to_datetime(ih["trade_date"])).set_index("trade_date")["value"].astype(float).dropna()
    r = np.log(c / c.shift(1))
    sig = outlook.ewma_sigma(r, lam)
    out = {}
    for h in (5, 20):
        fwd = sum(r.shift(-k) for k in range(1, h + 1))
        km = outlook.band_multipliers(r, sig, h)              # hệ số hiệu chỉnh đuôi dày, chỉ dùng dữ liệu quá khứ
        df = pd.DataFrame({"fwd": fwd, "b68": km["k68"] * sig * np.sqrt(h), "b90": km["k90"] * sig * np.sqrt(h)})
        out[h] = df[(df.index >= pd.Timestamp(start))].dropna()
    return out


def _tab_band(p) -> None:
    lam = float(get("outlook.ewma_lambda", 0.94))
    start = str(get("outlook.history_start", "2019-01-02"))
    st.caption(f"Mỗi phiên t ước lượng σ bằng EWMA (λ = {lam}) chỉ từ dữ liệu tới t, công bố biên ±k·σ√h cho h phiên tới; "
               "k = phân vị 68% / 90% thực nghiệm của sai số các dự báo ĐÃ BIẾT KẾT QUẢ trước t (hiệu chỉnh đuôi dày, thay "
               "z = 1 / 1,645 của phân phối chuẩn vốn làm biên 20 phiên chỉ bao phủ ~83%). Biên tốt khi bao phủ gần 68% / 90%.")
    hist = _band_history(lam, start)
    h = st.segmented_control("Kỳ hạn", [5, 20], default=5, format_func=lambda x: f"{x} phiên", key="bt_h") or 5
    df = hist[h]
    if df.empty:
        empty("Chưa đủ dữ liệu.")
        return
    in68, in90 = (df["fwd"].abs() <= df["b68"]), (df["fwd"].abs() <= df["b90"])
    kpi_row([kpi("Số phiên kiểm chứng", fmt.num(len(df), 0), None, f"từ {df.index[0]:%d/%m/%Y}"),
             kpi("Bao phủ biên 68%", f"{_pc(in68.mean(), 1)}", p["up"] if abs(in68.mean() - .68) < .05 else p["down"], "lý thuyết 68%"),
             kpi("Bao phủ biên 90%", f"{_pc(in90.mean(), 1)}", p["up"] if abs(in90.mean() - .90) < .04 else p["down"], "lý thuyết 90%"),
             kpi("Vượt biên dưới 90%", f"{_pc((df['fwd'] < -df['b90']).mean(), 1)}", p["down"], "giảm mạnh hơn dự kiến"),
             kpi("Vượt biên trên 90%", f"{_pc((df['fwd'] > df['b90']).mean(), 1)}", p["up"], "tăng mạnh hơn dự kiến")])
    x = df.index
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=df["b90"] * 100, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=-df["b90"] * 100, fill="tonexty", fillcolor="rgba(15,118,110,.15)", line=dict(width=0),
                             name="Biên 90%"))
    fig.add_trace(go.Scatter(x=x, y=df["b68"] * 100, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=-df["b68"] * 100, fill="tonexty", fillcolor="rgba(15,118,110,.28)", line=dict(width=0),
                             name="Biên 68%"))
    out = ~in90
    fig.add_trace(go.Scatter(x=x, y=df["fwd"] * 100, mode="lines", name=f"Lợi suất thực tế {h} phiên",
                             line=dict(color=p["text"], width=1)))
    fig.add_trace(go.Scatter(x=x[out], y=df["fwd"][out] * 100, mode="markers", name="Ngoài biên 90%",
                             marker=dict(color="#DC2626", size=5)))
    fig.update_layout(title=f"VN-Index: lợi suất {h} phiên tới (log, %) so với biên công bố trước", yaxis_title="%")
    plot(charts._lay(fig, p, 380), f"bt_band_{h}")
    yr = pd.DataFrame({"y": x.year, "in68": in68.values, "in90": in90.values})
    g = yr.groupby("y").agg(n=("in68", "size"), c68=("in68", "mean"), c90=("in90", "mean"))
    md(table_html(["Năm", "Số phiên", "Bao phủ 68%", "Bao phủ 90%"],
                  [[str(y), str(int(r.n)), f"{_pc(r.c68, 1)}", f"{_pc(r.c90, 1)}"] for y, r in g.iterrows()], left=(0,)))
    st.caption("Bao phủ thấp hơn lý thuyết ở năm biến động mạnh (đuôi dày); các năm ổn định thường bao phủ cao hơn. "
               "Lợi suất h phiên chồng lấp nên các phiên không độc lập.")


# ── 5. giá trị kinh tế: tín hiệu có tạo lợi nhuận sau chi phí không? ─────────
@st.cache_data(ttl=600, show_spinner=False)
def _econ(hold: int, cost: float) -> pd.DataFrame:
    d = da.daily()[["trade_date", "vni", "high_divergence"]].sort_values("trade_date").reset_index(drop=True)
    r = d["vni"].pct_change().fillna(0).to_numpy()
    sig = d["high_divergence"].fillna(False).astype(bool).to_numpy()
    n = len(d)
    pos = np.zeros(n)
    i = 0
    while i < n - 1:                                     # vào lệnh cuối phiên có tín hiệu, giữ `hold` phiên, không chồng lệnh
        if sig[i]:
            pos[i + 1:min(i + 1 + hold, n)] = 1
            i += hold
        else:
            i += 1
    strat = pos * r
    entries = np.where(np.diff(np.r_[0, pos]) > 0)[0]
    strat[entries] -= cost                               # chi phí khứ hồi tính một lần ở phiên vào lệnh
    return pd.DataFrame({"trade_date": d["trade_date"], "Chiến lược theo tín hiệu": strat, "Mua và nắm giữ VN-Index": r, "pos": pos})


def _stats(x: np.ndarray) -> dict:
    yrs = len(x) / 250
    tot = float(np.prod(1 + x) - 1)
    cum = np.cumprod(1 + x)
    return {"ann": (1 + tot) ** (1 / yrs) - 1 if yrs > 0 else np.nan,
            "sharpe": float(x.mean() / x.std() * np.sqrt(250)) if x.std() > 0 else np.nan,
            "mdd": float((cum / np.maximum.accumulate(cum) - 1).min()), "tot": tot}


def _tab_econ(p) -> None:
    st.caption("Kiểm tra tín hiệu duy nhất còn ý nghĩa thống kê sau hiệu chỉnh nhiều kiểm định (quy tắc 2 – độ vênh cao, "
               "p Holm < 0,05) có tạo LỢI NHUẬN THỰC không: vào lệnh mua VN-Index (qua ETF) cuối phiên có tín hiệu, giữ H phiên, "
               "trừ chi phí khứ hồi; thị trường cơ sở Việt Nam không cho bán khống nên chỉ có chiều mua.")
    c1, c2 = st.columns(2)
    hold = c1.select_slider("Số phiên nắm giữ H", [1, 3, 5, 10, 20], value=5, key="ec_h")
    cost = c2.select_slider("Chi phí khứ hồi", [0.0, 0.002, 0.003, 0.004, 0.005], value=0.004, key="ec_c",
                            format_func=lambda v: f"{v * 100:.1f}%".replace(".", ","))
    df = _econ(hold, cost)
    n = len(df)
    rows = []
    for lbl, lo, hi in (("Toàn kỳ", 0, n), ("Nửa đầu", 0, n // 2), ("Nửa sau", n // 2, n)):
        seg = df.iloc[lo:hi]
        a, b = _stats(seg["Chiến lược theo tín hiệu"].to_numpy()), _stats(seg["Mua và nắm giữ VN-Index"].to_numpy())
        rows.append([f"<b>{lbl}</b>", f"{seg['trade_date'].iloc[0]:%m/%Y}–{seg['trade_date'].iloc[-1]:%m/%Y}",
                     _pc(seg["pos"].mean(), 0), colored(a["ann"], _pc(a["ann"])), fmt.num(a["sharpe"], 2), _pc(a["mdd"]),
                     colored(b["ann"], _pc(b["ann"])), fmt.num(b["sharpe"], 2), colored(a["ann"] - b["ann"], _pc(a["ann"] - b["ann"]))])
    md(table_html(["Giai đoạn", "Thời gian", "Thời gian nắm giữ", "LS năm – tín hiệu", "Sharpe", "Sụt giảm tối đa",
                   "LS năm – nắm giữ", "Sharpe", "Chênh lệch"], rows, left=(0, 1)))
    cum = (1 + df[["Chiến lược theo tín hiệu", "Mua và nắm giữ VN-Index"]]).cumprod() * 100
    fig = go.Figure()
    for c, col in zip(cum.columns, (p["accent"], "#94A3B8")):
        fig.add_trace(go.Scatter(x=df["trade_date"], y=cum[c], name=c, line=dict(color=col, width=2)))
    fig.update_layout(title=f"Giá trị 100 đồng đầu tư · giữ {hold} phiên · chi phí {cost * 100:.1f}%".replace(".", ",", 1))
    plot(charts._lay(fig, p, 340), "ec_cum")
    full = _stats(df["Chiến lược theo tín hiệu"].to_numpy())
    bh = _stats(df["Mua và nắm giữ VN-Index"].to_numpy())
    verdict = ("có" if full["ann"] > bh["ann"] and full["sharpe"] > bh["sharpe"] else "KHÔNG")
    md(f'<div class="ffr-insight"><b>Kết luận:</b> với chi phí {cost * 100:.1f}%, chiến lược theo tín hiệu {verdict} vượt '
       f'mua-và-nắm-giữ (lợi suất năm {_pc(full["ann"])} so với {_pc(bh["ann"])}, Sharpe {fmt.num(full["sharpe"], 2)} so với '
       f'{fmt.num(bh["sharpe"], 2)}). Tín hiệu có ý nghĩa thống kê ở mức trung bình nhưng mức chênh nhỏ hơn chi phí giao dịch '
       'và không ổn định giữa hai nửa giai đoạn → hệ thống là công cụ <b>mô tả và theo dõi thị trường</b>, không phải chiến '
       'lược sinh lời.</div>'.replace("0.", "0,"))


def render() -> None:
    header("Backtest", "Kiểm chứng trên dữ liệu lịch sử: cảnh báo, giá trị dự báo, danh mục và biên dao động",
           pills=["chỉ dùng dữ liệu quá khứ tại mỗi thời điểm", "SSI FastConnect V3"])
    status_bar.render()
    p = pal()
    date = da.sessions()[-1]
    t1, t2, t3, t4, t5 = st.tabs(["🔔 Cảnh báo – chống trùng", "🎯 Cảnh báo – giá trị dự báo", "💼 Danh mục watchlist",
                                  "🔮 Biên dao động VN-Index", "💰 Giá trị kinh tế"])
    with t1:
        section("Chạy lại cảnh báo trên lịch sử", "Đo số tin thực sự gửi sau chống trùng và giới hạn ngày")
        _tab_dedup(p)
    with t2:
        section("Tín hiệu cảnh báo có giá trị dự báo không?", "VN-Index phiên t+1 và 5 phiên sau tín hiệu, so với phiên thường")
        _tab_predictive(p)
    with t3:
        section("Kiểm chứng ngoài mẫu danh mục (walk-forward)", "Tối ưu theo khẩu vị · so với chia đều, rủi ro thấp nhất và VN-Index")
        _tab_portfolio(p, date)
    with t4:
        section("Kiểm chứng biên dao động triển vọng", "Biên EWMA dùng trong báo cáo và bot (/outlook)")
        _tab_band(p)
    with t5:
        section("Hệ thống có tạo lợi nhuận sau chi phí không?", "Mô phỏng giao dịch theo tín hiệu, trừ phí và thuế, so với nắm giữ")
        _tab_econ(p)
