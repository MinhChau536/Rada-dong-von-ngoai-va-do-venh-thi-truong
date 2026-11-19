"""
Nội dung tin nhắn bot (HTML của Telegram) + bố cục nút bấm – sinh từ CÙNG ngữ cảnh src/reports/context.py với PDF
(số liệu khớp giao diện, bước B12.5). Hàm thuần: trả (text, keyboard) với keyboard = [[(nhãn, callback_data), ...], ...]
để dùng chung cho bot tương tác (python-telegram-bot) và bản tin theo lịch (HTTP API). Không có lệnh đặt lệnh.
"""
from __future__ import annotations

from html import escape
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.analytics import watchlist_impact as wi
from src.common import fmt
from src.common.config import get
from src.data import database as db
from src.finance.breadth import session_type_label
from src.finance.domestic import ABSORB_LABELS
from src.reports import context

Keyboard = List[List[Tuple[str, str]]]
LINE = "━━━━━━━━━━━━━━━━━━"

HELP = ("🤖 <b>FTSE FLOW RADAR BOT</b>\n" + LINE + "\n"
        "Bấm <b>Menu</b> (góc trái ô chat) hoặc các nút bên dưới. Có thể gõ thẳng mã, ví dụ <code>FPT</code>.\n\n"
        "📊 /market – tổng quan thị trường\n"
        "🏁 /leaders – mã dẫn dắt VN-Index\n"
        "🌏 /foreign – dòng vốn khối ngoại\n"
        "🔮 /outlook – triển vọng thống kê 5 & 20 phiên\n"
        "📈 /stock &lt;mã&gt; – thẻ phân tích: giá, ngành, đánh giá tổng quát\n"
        "⏱ /intra &lt;mã&gt; – giá từng phút trong phiên (gọi SSI ngay)\n"
        "🏭 /sector &lt;mã&gt; – ngành của mã và các mã cùng ngành\n"
        "🖼 /chart &lt;mã&gt; – biểu đồ giá ngày\n"
        "🔔 /alerts – cảnh báo tự động (bot tự nhắn khi thị trường/mã theo dõi biến động)\n"
        "👁 /watch – danh mục đang theo dõi\n"
        "➕ /add &lt;mã&gt; · ➖ /remove &lt;mã&gt; – sửa danh mục\n"
        "🧭 /diag – chẩn đoán phiên: 3 câu trả lời chính\n"
        "📄 /report – PDF báo cáo gần nhất\n"
        "🛰 /status – tình trạng dữ liệu\n"
        "📖 /legend – giải thích ký hiệu và thuật ngữ\n"
        "🏠 /menu – mở menu chính")

LEGEND = ("📖 <b>GIẢI THÍCH KÝ HIỆU</b>\n" + LINE + "\n"
          "🎨 <b>MÀU</b> (so với giá tham chiếu, hoặc so với 0)\n"
          "🟢 tăng / dương / mua ròng / đạt tiêu chí\n"
          "🔴 giảm / âm / bán ròng / chưa đạt tiêu chí\n"
          "🟡 đứng giá (không đổi)\n"
          "⚪ không có số liệu hoặc mã không giao dịch\n"
          "▰▰▱▱ thanh độ lớn: càng nhiều ô đậm thì giá trị càng lớn so với mã lớn nhất trong danh sách\n\n"
          "🏷 <b>BIỂU TƯỢNG MỤC</b>\n"
          "📈 VN-Index · 🔷 VN30 · 🔶 HNX · 🔸 UPCoM\n"
          "🏆 mạnh nhất · 🐢 yếu nhất · 🥇 xếp hạng ngành\n"
          "🧩 đánh giá tổng quát (điểm 0–100 theo số tiêu chí đạt)\n"
          "🌏 khối ngoại · 🏭 ngành · 🔮 triển vọng thống kê · 🚨 tín hiệu cảnh báo\n\n"
          "📚 <b>THUẬT NGỮ</b>\n"
          "• <b>NN ròng</b>: giá trị khối ngoại mua − bán (tỷ đồng)\n"
          "• <b>GTGD</b>: giá trị giao dịch khớp lệnh · <b>KL</b>: khối lượng\n"
          "• <b>C</b>: điểm một mã đóng góp vào VN-Index · <b>ΔVN-Index</b>: thay đổi điểm cả phiên\n"
          "• <b>CR5</b>: tỷ trọng đóng góp của 5 mã ảnh hưởng mạnh nhất\n"
          "• <b>D (độ vênh)</b>: % VN-Index − % cổ phiếu trung vị; D lớn = chỉ số tăng nhờ ít mã\n"
          "• <b>AD</b>: (số mã tăng − giảm) / tổng số mã\n"
          "• <b>z60</b>: khối ngoại hôm nay lệch bao nhiêu độ lệch chuẩn so với 60 phiên trước; |z| ≥ 2 là bất thường\n"
          "• <b>HHI</b>: độ tập trung dòng vốn ngoại (gần 1 = dồn vào rất ít mã)\n"
          "• <b>FPR</b>: tỷ lệ khối ngoại tham gia trong tổng GTGD\n"
          "• <b>Room</b>: phần trăm giới hạn sở hữu nước ngoài đã dùng\n"
          "• <b>MA20/MA50</b>: giá trung bình 20/50 phiên · <b>RSI14</b>: &gt;70 quá mua, &lt;30 quá bán\n"
          "• <b>VWAP</b>: giá bình quân theo khối lượng trong phiên\n\n"
          "🤝 <b>TRẠNG THÁI KHỐI NGOẠI – KHỐI NỘI</b>\n"
          "• Giá tăng dù ngoại bán · Ngoại bán, giá giảm · Ngoại mua, giá tăng · Giá giảm dù ngoại mua\n"
          "  (chỉ gán khi |nf| ≥ 5% và |giá| ≥ 0,5%; ròng khối nội luôn = − ròng khối ngoại nên nhãn chỉ mô tả chiều giá)\n"
          "• Trung tính: dòng vốn hoặc biến động giá quá nhỏ để kết luận\n\n"
          "🧭 <b>LOẠI PHIÊN</b>\n"
          "• Tăng lan rộng / Giảm đồng thuận: đa số mã cùng chiều chỉ số\n"
          "• Tăng (Giảm) thiếu lan tỏa: chỉ số đi một chiều nhưng số đông cổ phiếu không theo")

MENU: Keyboard = [[("📊 Thị trường", "market"), ("🏁 Dẫn dắt", "leaders")],
                  [("🌏 Khối ngoại", "foreign"), ("🔮 Triển vọng", "outlook")],
                  [("🧭 Chẩn đoán phiên", "diag"), ("👁 Watchlist", "watch")],
                  [("📄 Báo cáo PDF", "report"), ("🛰 Trạng thái", "status")],
                  [("🔔 Cảnh báo tự động", "alerts"), ("📖 Ký hiệu", "legend")]]
BACK: Keyboard = [[("🏠 Menu chính", "menu")]]


def dot(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "⚪"
    return "🟢" if v > 1e-9 else "🔴" if v < -1e-9 else "🟡"


def bar(v: float, vmax: float, n: int = 8) -> str:
    k = 0 if not vmax else int(round(abs(v) / vmax * n))
    return "▰" * max(k, 1 if v else 0) + "▱" * (n - max(k, 1 if v else 0))


def _ctx(ctx: Optional[Dict]) -> Optional[Dict]:
    return ctx or context.build()


def _head(icon: str, title: str, d) -> str:
    return f"{icon} <b>{escape(title.upper())}</b> · phiên {pd.Timestamp(d):%d/%m/%Y}\n{LINE}\n"


# ── thị trường ────────────────────────────────────────────────────────────────
def market(ctx: Optional[Dict] = None, with_buttons: bool = False):
    ctx = _ctx(ctx)
    if not ctx:
        return ("Chưa có dữ liệu phiên.", BACK) if with_buttons else "Chưa có dữ liệu phiên."
    x, idx = ctx["day"], ctx["index"].set_index("index_code")
    lines = [_head("📊", "Tổng quan thị trường", ctx["date"])]
    for code, name, ic in (("VNINDEX", "VN-Index", "📈"), ("VN30", "VN30", "🔷"), ("HNXINDEX", "HNX", "🔶"), ("UPCOMINDEX", "UPCoM", "🔸")):
        if code in idx.index:
            r = idx.loc[code]
            lines.append(f"{ic} {name}: <b>{fmt.num(r['value'])}</b>  {dot(r['change'])} {fmt.num(r['change'], 2, True)} "
                         f"({fmt.pct(r['ratio_change'])})")
    lines.append("\n🧭 <b>CHẤT LƯỢNG XU HƯỚNG</b>")
    lines.append(f"• Loại phiên: <b>{session_type_label(x['session_type'])}</b>")
    lines.append(f"• Tăng / Đứng / Giảm: 🟢 {int(x['n_up'])} · 🟡 {int(x['n_unch'])} · 🔴 {int(x['n_down'])} "
                 f"(trần {int(x['n_ceiling'])}, sàn {int(x['n_floor'])}) · AD = {fmt.num(x['AD'], 2, True)}")
    lines.append(f"• Trung vị cổ phiếu HOSE: {fmt.pct(x['median_ret_pct'])} · độ vênh D = {fmt.num(x['D'], 2, True)} đ.%")
    lines.append(f"• Top 5 mã tạo {fmt.frac_pct(x['CR5'], 0)} tổng đóng góp điểm (CR5)")
    lines.append(f"• GTGD khớp: {fmt.bn(x['tv_total'], 0, False)}")
    lines.append(f"\n🌏 <b>KHỐI NGOẠI</b>: {dot(x['NF_total'])} ròng <b>{fmt.bn(x['NF_total'])}</b> "
                 f"(z60 = {fmt.num(x['z_NF_total'], 2, True)})")
    lines.append(f"\n🧠 <b>NHẬN ĐỊNH</b>\n<i>{escape(ctx['summary'])}</i>")
    text = "\n".join(lines)
    kb = [[("🏁 Dẫn dắt", "leaders"), ("🌏 Khối ngoại", "foreign")],
          [("🔮 Triển vọng", "outlook"), ("📈 Biểu đồ VN-Index", "chart:VNINDEX")],
          [("📄 Báo cáo PDF", "report"), ("🏠 Menu", "menu")]]
    return (text, kb) if with_buttons else text


def leaders(ctx: Optional[Dict] = None, with_buttons: bool = False):
    ctx = _ctx(ctx)
    if not ctx:
        return ("Chưa có dữ liệu phiên.", BACK) if with_buttons else "Chưa có dữ liệu phiên."
    x, lead = ctx["day"], ctx["leaders"]
    pos, neg = lead[lead["side"] == "pos"].head(5), lead[lead["side"] == "neg"].head(5)
    vmax = max(lead["C"].abs().max() if not lead.empty else 1, 1e-9)
    lines = [_head("🏁", "Mã dẫn dắt VN-Index", ctx["date"]),
             f"ΔVN-Index = <b>{fmt.num(x['dI'], 2, True)} điểm</b> · CR5 = {fmt.frac_pct(x['CR5'], 0)}\n",
             "🟢 <b>KÉO LÊN</b>"]
    lines += [f"<code>{r.symbol:<4}</code> {bar(r.C, vmax)} {fmt.num(r.C, 2, True)}" for r in pos.itertuples()] or ["—"]
    lines.append("\n🔴 <b>KÉO XUỐNG</b>")
    lines += [f"<code>{r.symbol:<4}</code> {bar(r.C, vmax)} {fmt.num(r.C, 2, True)}" for r in neg.itertuples()] or ["—"]
    g = ctx["groups"]
    fam = g[g["group_type"] == "family"]
    vin = fam[fam["group_name"] == "VINGROUP"]
    if not vin.empty:
        lines.append(f"\n🏢 Nhóm Vingroup: {fmt.num(vin['C'].iloc[0], 2, True)} điểm · VN-Index loại trừ nhóm: "
                     f"{fmt.pct(vin['index_ex_group_ret_pct'].iloc[0])} (thực tế {fmt.pct(x['r_vni_pct'])})")
    lead20 = ctx.get("lead20")
    if lead20 is not None and not lead20.empty:
        top = lead20.reindex(lead20["C"].abs().sort_values(ascending=False).index).head(4)
        lines.append("\n📅 20 phiên (ΣC): " + " · ".join(f"{r.symbol} {fmt.num(r.C, 1, True)}" for r in top.itertuples()))
    kb = [[(f"📈 {r.symbol}", f"stock:{r.symbol}") for r in pd.concat([pos.head(2), neg.head(2)]).itertuples()],
          [("📊 Thị trường", "market"), ("🏠 Menu", "menu")]]
    text = "\n".join(lines)
    return (text, kb) if with_buttons else text


def foreign(ctx: Optional[Dict] = None, with_buttons: bool = False):
    ctx = _ctx(ctx)
    if not ctx:
        return ("Chưa có dữ liệu phiên.", BACK) if with_buttons else "Chưa có dữ liệu phiên."
    x = ctx["day"]
    lines = [_head("🌏", "Dòng vốn khối ngoại", ctx["date"])]
    if pd.isna(x["NF_total"]):
        lines.append("⚠️ SSI chưa công bố số liệu khối ngoại cho phiên này.")
    else:
        lines.append(f"Ròng HOSE: {dot(x['NF_total'])} <b>{fmt.bn(x['NF_total'])}</b> · z60 = {fmt.num(x['z_NF_total'], 2, True)}")
        lines.append(f"Mua {fmt.bn(x['FB_total'], 0, False)} · Bán {fmt.bn(x['FS_total'], 0, False)} · "
                     f"tham gia {fmt.frac_pct(x['FPR_total'], 1)} GTGD · HHI {fmt.num(x['HHI'], 3)}")
        tb, ts = ctx["top_buy"], ctx["top_sell"]
        vmax = max(tb["net_flow"].abs().max() if not tb.empty else 0, ts["net_flow"].abs().max() if not ts.empty else 0, 1)
        lines.append("\n🟢 <b>MUA RÒNG</b>")
        lines += [f"<code>{r.symbol:<4}</code> {bar(r.net_flow, vmax)} {fmt.bn(r.net_flow)}" for r in tb.itertuples() if r.net_flow > 0]
        lines.append("\n🔴 <b>BÁN RÒNG</b>")
        lines += [f"<code>{r.symbol:<4}</code> {bar(r.net_flow, vmax)} {fmt.bn(r.net_flow)}" for r in ts.itertuples() if r.net_flow < 0]
    g = ctx["groups"]
    uni = g[g["group_type"] == "universe"].set_index("group_name")
    rows = [(n, l) for n, l in (("FTSE", "Nhóm FTSE"), ("CONTROL", "Đối chứng"), ("VN30", "VN30")) if n in uni.index]
    if rows:
        lines.append("\n🎯 <b>THEO NHÓM</b>")
        for n, l in rows:
            r = uni.loc[n]
            lines.append(f"• {l}: {dot(r['net_flow'])} {fmt.bn(r['net_flow'])} · {ABSORB_LABELS.get(r['absorb_state'], '')}")
    rc = ctx.get("recap") or {}
    if rc:
        lines.append(f"\n📅 Lũy kế: 5 phiên {fmt.bn(rc[5]['nf_cum'])} · 20 phiên {fmt.bn(rc[20]['nf_cum'])} "
                     f"({rc[20]['nf_buy_days']}/20 phiên mua ròng)")
    kb = [[("📊 Thị trường", "market"), ("🔮 Triển vọng", "outlook")], [("🏠 Menu", "menu")]]
    text = "\n".join(lines)
    return (text, kb) if with_buttons else text


def outlook(ctx: Optional[Dict] = None, with_buttons: bool = False):
    ctx = _ctx(ctx)
    if not ctx:
        return ("Chưa có dữ liệu phiên.", BACK) if with_buttons else "Chưa có dữ liệu phiên."
    vr = ctx["vol_range"]
    last = float(ctx["idx_hist"]["VN-Index"].iloc[-1])
    lines = [_head("📏", "Biên dao động VN-Index", ctx["date"]), f"VN-Index hiện tại: <b>{fmt.num(last)}</b>\n"]
    for h in (5, 20):
        r = vr.get(h)
        if r:
            lines.append(f"📏 <b>{h} phiên tới</b> – biên dao động")
            lines.append(f"   • 68%: {fmt.num(r['lo68'], 0)} – {fmt.num(r['hi68'], 0)}")
            lines.append(f"   • 90%: {fmt.num(r['lo90'], 0)} – {fmt.num(r['hi90'], 0)}")
    sig = ctx.get("signals") or []
    lines.append("🚨 Tín hiệu hôm nay: " + (", ".join(escape(s["rule"]) for s in sig) if sig else "không có"))
    if 5 in vr:
        lines.append(f"\n📐 Mức dao động bình thường của VN-Index: khoảng <b>±{fmt.num(vr[5]['sigma_d'] * 100, 2)}% mỗi phiên</b>\n"
                     f"<i>(độ lệch chuẩn lợi suất ngày, phiên gần đây được tính trọng số cao hơn)</i>\n"
                     f"✅ Kiểm chứng từ 2019: VN-Index thực tế nằm trong biên 90% ở "
                     f"<b>{fmt.frac_pct(vr[5]['coverage90'], 0)}</b> số lần")
    lines.append("<i>Biên mô tả mức dao động bình thường (EWMA, hiệu chỉnh đuôi dày), không phải dự báo hướng đi.</i>")
    kb = [[("📊 Thị trường", "market"), ("📈 Biểu đồ VN-Index", "chart:VNINDEX")], [("🏠 Menu", "menu")]]
    text = "\n".join(lines)
    return (text, kb) if with_buttons else text


# ── cổ phiếu & watchlist ─────────────────────────────────────────────────────
def _vni_ret(d, n: int) -> float:
    v = db.query_df("SELECT value FROM fact_daily_index WHERE index_code = 'VNINDEX' AND trade_date <= ? "
                    "ORDER BY trade_date DESC LIMIT ?", [d, n + 1])["value"]
    return float(v.iat[0] / v.iat[-1] - 1) * 100 if len(v) > n else np.nan


def _sector_stats(sector: str, d) -> Dict:
    """Sức mạnh ngành: lợi suất bình quân đều 1/5/20 phiên, hạng giữa các ngành, khối ngoại ngành."""
    g = db.query_df("SELECT trade_date, group_name, ret_eq, net_flow FROM indicator_group_daily WHERE group_type = 'sector' "
                    "AND trade_date <= ? AND trade_date > ? - INTERVAL 60 DAY ORDER BY trade_date", [d, d])
    if g.empty or sector not in set(g["group_name"]):
        return {}
    r = g.pivot_table(index="trade_date", columns="group_name", values="ret_eq").sort_index()
    nf = g.pivot_table(index="trade_date", columns="group_name", values="net_flow").sort_index()
    cum = lambda n: ((1 + r.tail(n).fillna(0)).prod() - 1) * 100  # noqa: E731
    r20 = cum(20)
    rank = r20.rank(ascending=False, method="min").astype(int)
    return {"r1": float(r[sector].iloc[-1] * 100), "r5": float(cum(5)[sector]), "r20": float(r20[sector]),
            "rank": int(rank[sector]), "n_sec": int(len(r20)), "nf1": float(nf[sector].iloc[-1]),
            "nf20": float(nf[sector].tail(20).sum()), "top": r20.sort_values(ascending=False)}


def _peers(sector: str, d) -> pd.DataFrame:
    return db.query_df("SELECT symbol, close, ret, ret_5d, ret_20d, net_flow, tv, C FROM indicator_stock_daily "
                       "WHERE trade_date = ? AND sector = ? AND is_valid ORDER BY tv DESC", [d, sector])


def _live(symbol: str) -> Optional[Dict]:
    """Giá trong phiên hôm nay (gọi SSI ngay) – chỉ trong giờ giao dịch, lỗi thì bỏ qua."""
    try:
        from src.bot import intraday
        if not intraday.in_session():
            return None
        df, d = intraday.fetch(symbol)
        if df.empty or d != intraday.now_vn().date():
            return None
        ref, lbl = intraday.reference(symbol, d)
        return {**intraday.summary(df, ref), "ref_lbl": lbl}
    except Exception:  # noqa: BLE001
        return None


def stock_card(symbol: str, ctx: Optional[Dict] = None):
    """Thẻ phân tích một mã: giá, hiệu suất so VN-Index, kỹ thuật, khối ngoại, NGÀNH của mã, đánh giá tổng quát /100."""
    from src.analytics.health import rsi
    s = symbol.upper().strip()
    ctx = _ctx(ctx)
    h = db.query_df("SELECT * FROM indicator_stock_daily WHERE symbol = ? ORDER BY trade_date", [s])
    if h.empty or ctx is None:
        return f"❓ Không tìm thấy dữ liệu cho <b>{escape(s)}</b> (chỉ hỗ trợ cổ phiếu HOSE).", BACK
    h = h[pd.to_datetime(h["trade_date"]) <= ctx["date"]]
    r = h.iloc[-1]
    d = pd.Timestamp(r["trade_date"])
    c = h["close"].astype(float)
    ma20, ma50 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1]
    rsi14 = float(rsi(c).iloc[-1]) if len(c) > 15 else np.nan
    nf5, nf20 = h["net_flow"].tail(5).sum(), h["net_flow"].tail(20).sum()
    tv20 = h["tv"].tail(20).mean()
    ret = lambda n: (c.iloc[-1] / c.iloc[-n - 1] - 1) * 100 if len(c) > n else np.nan  # noqa: E731
    perf = {n: (ret(n), _vni_ret(d, n)) for n in (5, 20, 60, 250)}
    hi52, lo52 = c.tail(250).max(), c.tail(250).min()
    pos52 = (c.iloc[-1] - lo52) / (hi52 - lo52) * 100 if hi52 > lo52 else np.nan
    sector = str(r.get("sector") or "")
    sec = _sector_stats(sector, d) if sector else {}
    peers = _peers(sector, d) if sector else pd.DataFrame()
    wl = wi.get_watchlist()
    cap = r["close"] * r["listed_share"] if pd.notna(r.get("listed_share")) else np.nan
    U = r["U"] if pd.notna(r["U"]) else 0

    checks = [("Xu hướng tăng (giá > MA20 > MA50)", bool(c.iloc[-1] > ma20 > ma50)),
              ("Động lượng lành mạnh (RSI14 từ 40 đến 70)", bool(40 <= rsi14 <= 70)),
              ("Mạnh hơn VN-Index 20 phiên", bool(perf[20][0] > perf[20][1])),
              ("Khối ngoại mua ròng 20 phiên", bool(nf20 > 0)),
              ("Thanh khoản ≥ 10 tỷ/phiên", bool(tv20 >= 10e9)),
              ("Ngành mạnh hơn VN-Index 20 phiên", bool(sec and sec["r20"] > perf[20][1])),
              ("Room ngoại chưa cạn (đã dùng dưới 95%)", bool(U < 0.95))]
    n_ok = sum(ok for _, ok in checks)
    score = round(n_ok / len(checks) * 100)
    verdict = "🟢 TÍCH CỰC" if score >= 70 else "🟡 TRUNG TÍNH" if score >= 45 else "🔴 TIÊU CỰC"

    lines = [f"📈 <b>{s}</b> · {escape(sector or '—')} · HOSE", f"📅 Phiên {d:%d/%m/%Y}\n{LINE}"]
    lv = _live(s)
    if lv:
        lines.append(f"⚡ <b>TRONG PHIÊN {lv['last_t']:%H:%M}</b>: <b>{fmt.price(lv['last'])}</b> {dot(lv['chg'])} "
                     f"{fmt.pct(lv['pct'])} so {lv['ref_lbl']} · KL {fmt.num(lv['vol'] / 1e6, 2)} tr\n")
    lines += [f"💰 <b>GIÁ</b>: <b>{fmt.price(r['close'])}</b>  {dot(r['ret'])} {fmt.pct(r['ret'] * 100)}",
              f"• Mở {fmt.price(r['open'])} · Cao {fmt.price(r['high'])} · Thấp {fmt.price(r['low'])}",
              f"• TC {fmt.price(r['ref'])} · Trần {fmt.price(r['ceiling'])} · Sàn {fmt.price(r['floor'])}",
              f"• KL {fmt.num(r['vol'] / 1e6, 2)} tr · GTGD {fmt.bn(r['tv'], 1, False)} · vốn hóa {fmt.bn(cap, 0, False)}",
              f"• Vùng 52 tuần: {fmt.price(lo52)} – {fmt.price(hi52)} (đang ở {fmt.num(pos52, 0)}% biên độ)",
              "\n📆 <b>HIỆU SUẤT</b> (mã | VN-Index)"]
    for n, lbl in ((5, "1 tuần"), (20, "1 tháng"), (60, "3 tháng"), (250, "1 năm")):
        a, b = perf[n]
        lines.append(f"• {lbl}: {dot(a)} {fmt.pct(a, 1)} | {fmt.pct(b, 1)}")
    lines += ["\n📐 <b>KỸ THUẬT</b>",
              f"• MA20 {fmt.price(ma20)} · MA50 {fmt.price(ma50)} · RSI14 {fmt.num(rsi14, 1)}",
              f"• KL so TB20: {fmt.num(r.get('vol_ratio'), 2, False, '×')} · GTGD TB20: {fmt.bn(tv20, 1, False)}",
              f"• Đóng góp VN-Index hôm nay: {fmt.num(r['C'], 2, True)} điểm",
              "\n🌏 <b>KHỐI NGOẠI</b>",
              f"• Hôm nay {dot(r['net_flow'])} {fmt.bn(r['net_flow'], 1)} · 5 phiên {fmt.bn(nf5, 1)} · 20 phiên {fmt.bn(nf20, 1)}",
              f"• Room đã dùng {fmt.frac_pct(U, 1)} · {escape(ABSORB_LABELS.get(r['absorb_state'], '—'))}"]
    if sec:
        strong = "mạnh hơn" if sec["r20"] > perf[20][1] else "yếu hơn"
        lines += [f"\n🏭 <b>NGÀNH {escape(sector.upper())}</b>",
                  f"• Hôm nay {dot(sec['r1'])} {fmt.pct(sec['r1'])} · 5 phiên {fmt.pct(sec['r5'], 1)} · "
                  f"20 phiên {fmt.pct(sec['r20'], 1)}",
                  f"• Xếp hạng 20 phiên: <b>{sec['rank']}/{sec['n_sec']}</b> ngành · {strong} VN-Index",
                  f"• Khối ngoại ngành: hôm nay {fmt.bn(sec['nf1'], 0)} · 20 phiên {fmt.bn(sec['nf20'], 0)}"]
        if not peers.empty and s in set(peers["symbol"]):
            pr = peers.sort_values("ret_20d", ascending=False).reset_index(drop=True)
            k = int(pr.index[pr["symbol"] == s][0]) + 1
            lines.append(f"• {s} đứng <b>{k}/{len(pr)}</b> mã trong ngành theo lợi suất 20 phiên")
    lines.append(f"\n🧩 <b>ĐÁNH GIÁ TỔNG QUÁT: {score}/100 – {verdict}</b> ({n_ok}/{len(checks)} tiêu chí)")
    lines += [f"{'🟢' if ok else '🔴'} {escape(lbl)}" for lbl, ok in checks]
    lines.append("<i>Tiêu chí mô tả trạng thái hiện tại, không phải tín hiệu mua/bán.</i>")
    kb = [[("📈 Biểu đồ ngày", f"chart:{s}"), ("⏱ Trong phiên (1 phút)", f"intra:{s}")],
          [("🏭 Ngành", f"sec:{s}"), ("🔄 Làm mới", f"stock:{s}")],
          [("➖ Bỏ theo dõi", f"rm:{s}") if s in wl else ("➕ Theo dõi", f"add:{s}"), ("👁 Watchlist", "watch")],
          [("🏠 Menu", "menu")]]
    return "\n".join(lines), kb


def sector_card(symbol: str, ctx: Optional[Dict] = None):
    """Ngành của một mã: sức mạnh so VN-Index, hạng giữa các ngành, khối ngoại, bảng các mã cùng ngành."""
    s = symbol.upper().strip()
    ctx = _ctx(ctx)
    row = db.query_df("SELECT sector FROM indicator_stock_daily WHERE symbol = ? AND sector IS NOT NULL "
                      "ORDER BY trade_date DESC LIMIT 1", [s])
    if row.empty or ctx is None:
        return f"❓ Chưa có thông tin ngành của <b>{escape(s)}</b>.", BACK
    sector, d = str(row["sector"].iat[0]), ctx["date"]
    sec, peers = _sector_stats(sector, d), _peers(sector, d)
    if not sec or peers.empty:
        return f"❓ Chưa có số liệu ngành {escape(sector)}.", [[("📈 " + s, f"stock:{s}"), ("🏠 Menu", "menu")]]
    v1, v5, v20 = _vni_ret(d, 1), _vni_ret(d, 5), _vni_ret(d, 20)
    n_up, n_dn = int((peers["ret"] > 0).sum()), int((peers["ret"] < 0).sum())
    lines = [_head("🏭", f"Ngành {sector}", d),
             f"🔢 {len(peers)} mã HOSE · tăng 🟢 {n_up} · giảm 🔴 {n_dn} · đứng 🟡 {len(peers) - n_up - n_dn}",
             "\n📆 <b>NGÀNH | VN-INDEX</b>",
             f"• Hôm nay: {dot(sec['r1'])} {fmt.pct(sec['r1'])} | {fmt.pct(v1)}",
             f"• 5 phiên: {dot(sec['r5'])} {fmt.pct(sec['r5'], 1)} | {fmt.pct(v5, 1)}",
             f"• 20 phiên: {dot(sec['r20'])} {fmt.pct(sec['r20'], 1)} | {fmt.pct(v20, 1)}",
             f"• Xếp hạng 20 phiên: <b>{sec['rank']}/{sec['n_sec']}</b> ngành · "
             f"{'🟢 mạnh hơn' if sec['r20'] > v20 else '🔴 yếu hơn'} thị trường",
             f"\n🌏 <b>KHỐI NGOẠI NGÀNH</b>: hôm nay {dot(sec['nf1'])} {fmt.bn(sec['nf1'], 1)} · 20 phiên {fmt.bn(sec['nf20'], 0)}",
             "\n📋 <b>CÁC MÃ TRONG NGÀNH</b> (theo GTGD)",
             "<code>   Mã   Hôm nay 20 phiên   NN ròng</code>"]
    for p_ in peers.head(12).itertuples():
        lines.append(f"{dot(p_.ret)}<code>{p_.symbol:<4} {fmt.pct(p_.ret * 100, 1):>8} {fmt.pct(p_.ret_20d, 1):>8} "
                     f"{fmt.bn(p_.net_flow, 0):>9}</code>")
    lines.append("<i>🟢 tăng · 🔴 giảm · 🟡 đứng giá hôm nay · NN ròng = khối ngoại mua − bán hôm nay "
                 "(dương: mua ròng, âm: bán ròng). Bảng xếp theo giá trị giao dịch, lớn nhất ở trên.</i>")
    best = peers.dropna(subset=["ret_20d"]).sort_values("ret_20d", ascending=False)
    lines.append("\n🏆 Mạnh nhất 20 phiên: " + " · ".join(f"<b>{x.symbol}</b> {fmt.pct(x.ret_20d, 1)}"
                                                       for x in best.head(3).itertuples()))
    lines.append("🐢 Yếu nhất 20 phiên: " + " · ".join(f"<b>{x.symbol}</b> {fmt.pct(x.ret_20d, 1)}"
                                                     for x in best.tail(3)[::-1].itertuples()))
    lines.append("\n🥇 <b>TOP NGÀNH 20 PHIÊN</b>")
    for i, (name, v) in enumerate(sec["top"].head(5).items(), 1):
        nm = f"<b>{escape(name)}</b>" if name == sector else escape(name)
        lines.append(f"{i}. {nm}: {fmt.pct(v, 1)}")
    if sec["rank"] > 5:
        lines.append(f"…{sec['rank']}. <b>{escape(sector)}</b>: {fmt.pct(sec['r20'], 1)}")
    others = [x for x in peers["symbol"].head(5) if x != s][:4]
    kb = [[(f"📈 {x}", f"stock:{x}") for x in others[:2]], [(f"📈 {x}", f"stock:{x}") for x in others[2:4]],
          [(f"↩️ Thẻ {s}", f"stock:{s}"), ("📖 Ký hiệu", "legend"), ("🏠 Menu", "menu")]]
    return "\n".join(lines), [k for k in kb if k]


def intraday_caption(symbol: str, sm: Dict, d) -> str:
    return (f"⏱ <b>{escape(symbol)}</b> · nến 1 phút · phiên {d:%d/%m/%Y} · cập nhật {sm['last_t']:%H:%M}\n"
            f"💰 Giá cuối <b>{fmt.price(sm['last'])}</b> {dot(sm['chg'])} {fmt.num(sm['chg'], 0, True)} ({fmt.pct(sm['pct'])}) "
            f"so {sm.get('ref_lbl', 'TC')} {fmt.price(sm.get('ref'))}\n"
            f"• Mở {fmt.price(sm['open'])} · Cao {fmt.price(sm['high'])} lúc {sm['high_t']:%H:%M} · "
            f"Thấp {fmt.price(sm['low'])} lúc {sm['low_t']:%H:%M}\n"
            f"• VWAP {fmt.price(sm['vwap'])} · giá cuối {'trên' if sm['last'] >= sm['vwap'] else 'dưới'} giá bình quân phiên\n"
            f"• KL {fmt.num(sm['vol'] / 1e6, 2)} tr (sáng {fmt.num(sm['vol_am'] / 1e6, 2)} · chiều "
            f"{fmt.num(sm['vol_pm'] / 1e6, 2)}) · GTGD {fmt.bn(sm['value'], 1, False)}\n"
            f"<i>Nguồn SSI FastConnect V3, gọi trực tiếp lúc bấm nút · {sm['bars']} nến.</i>")


def watch(symbol: Optional[str] = None, ctx: Optional[Dict] = None, with_buttons: bool = False):
    if symbol:
        t, kb = stock_card(symbol, ctx)
        return (t, kb) if with_buttons else t
    ctx = _ctx(ctx)
    wl = wi.get_watchlist()
    if not ctx:
        return ("Chưa có dữ liệu phiên.", BACK) if with_buttons else "Chưa có dữ liệu phiên."
    lines = [_head("👁", f"Watchlist ({len(wl)} mã)", ctx["date"])]
    if not wl:
        lines.append("Danh mục trống – gõ /add FPT hoặc gõ thẳng một mã để thêm.")
    pf = ctx.get("watch")
    st = ctx["stock"].set_index("symbol")
    for s in wl:
        if s in st.index and bool(st.loc[s, "is_valid"]):
            r = st.loc[s]
            lines.append(f"{dot(r['ret'])} <b>{s}</b> {fmt.price(r['close'])} ({fmt.pct(r['ret'] * 100)}) · NN {fmt.bn(r['net_flow'], 1)} · "
                         f"{ABSORB_LABELS.get(r['absorb_state'], '')}")
        else:
            lines.append(f"⚪ <b>{s}</b> – không giao dịch phiên này")
    if pf is not None and not pf.empty:
        lines.append("\n🧠 <b>NHẬN ĐỊNH</b>")
        lines += [f"• {escape(x)}" for x in pf["sentence"].tolist() if x]
    kb = [[(f"📈 {s}", f"stock:{s}") for s in wl[i:i + 3]] for i in range(0, min(len(wl), 9), 3)]
    kb += [[("🧭 Chẩn đoán phiên", "diag"), ("🏠 Menu", "menu")]]
    text = "\n".join(lines)
    return (text, kb) if with_buttons else text


def diagnosis(ctx: Optional[Dict] = None, with_buttons: bool = True):
    """Tin chính của phiên: 3 câu trả lời bằng lời thường (cùng nguồn với trang Chẩn đoán thị trường và PDF)."""
    ctx = _ctx(ctx)
    if not ctx or not ctx.get("answers"):
        return ("Chưa có dữ liệu phiên.", BACK) if with_buttons else "Chưa có dữ liệu phiên."
    lines = [_head("🧭", "Chẩn đoán phiên", ctx["date"])]
    for i, a in enumerate(ctx["answers"], 1):
        lines.append(f"\n<b>{i}. {escape(a['q'])}</b>\n{escape(a['a'])}")
    lines.append("\n💡 <b>CÁCH ĐỌC</b>")
    lines += [f"• {escape(t)}" for t in ctx.get("implications", [])[:2]]
    kb = [[("📊 Thị trường", "market"), ("🏁 Dẫn dắt", "leaders")], [("🌏 Khối ngoại", "foreign"), ("👁 Watchlist", "watch")],
          [("🏠 Menu", "menu")]]
    text = "\n".join(lines)
    return (text, kb) if with_buttons else text


def status() -> str:
    from src.data import updater
    st = db.query_df("SELECT * FROM source_status")
    q = db.query_df("SELECT trade_date, value FROM data_quality_log WHERE check_name = 'completeness' "
                    "ORDER BY trade_date DESC LIMIT 1")
    cov, last = updater.coverage(), updater.last_status()
    lines = [f"🛰 <b>TÌNH TRẠNG DỮ LIỆU</b>\n{LINE}", "Nguồn: SSI FastConnect V3 (REST + WebSocket)"]
    for r in st.itertuples():
        lines.append(f"{'🟢' if r.status == 'ok' else '🔴'} {r.source}: {r.status} · {pd.Timestamp(r.updated_at):%H:%M %d/%m}")
    lines.append(f"📅 Dữ liệu tới phiên: <b>{cov['indicators']}</b> (phiên đã đóng gần nhất {cov['expected_last_session']})")
    if last:
        lines.append(f"🔄 Cập nhật gần nhất: {last.get('started')} – {last.get('status')}")
    if not q.empty:
        lines.append(f"✅ Độ đầy đủ phiên {pd.Timestamp(q['trade_date'].iloc[0]):%d/%m/%Y}: {fmt.frac_pct(q['value'].iloc[0], 1)}")
    return "\n".join(lines)


def latest_report() -> Optional[str]:
    r = db.query_df("SELECT path FROM reports_log WHERE status = 'ok' AND path IS NOT NULL ORDER BY created_at DESC LIMIT 1")
    return None if r.empty else str(r["path"].iloc[0])


def menu_text() -> str:
    from src.reports.context import latest_date
    d = latest_date()
    return ("🏠 <b>MENU CHÍNH – FTSE FLOW RADAR</b>\n" + LINE + "\n"
            f"Dữ liệu tới phiên <b>{d:%d/%m/%Y}</b>. Chọn mục bên dưới, hoặc gõ một mã (vd. <code>FPT</code>)."
            if d is not None else "🏠 <b>MENU CHÍNH</b>")
