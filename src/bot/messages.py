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
        "📈 /stock &lt;mã&gt; – thẻ phân tích một mã (kèm biểu đồ)\n"
        "👁 /watch – danh mục đang theo dõi\n"
        "➕ /add &lt;mã&gt; · ➖ /remove &lt;mã&gt; – sửa danh mục\n"
        "💼 /portfolio – tối ưu danh mục theo khẩu vị rủi ro\n"
        "📄 /report – PDF báo cáo gần nhất\n"
        "🛰 /status – tình trạng dữ liệu\n"
        "🏠 /menu – mở menu chính")

MENU: Keyboard = [[("📊 Thị trường", "market"), ("🏁 Dẫn dắt", "leaders")],
                  [("🌏 Khối ngoại", "foreign"), ("🔮 Triển vọng", "outlook")],
                  [("👁 Watchlist", "watch"), ("💼 Danh mục", "pf:Cân bằng")],
                  [("📄 Báo cáo PDF", "report"), ("🛰 Trạng thái", "status")]]
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
    h = ctx.get("health") or {}
    if h.get("available"):
        lines.append(f"\n🌡 <b>SỨC KHỎE THỊ TRƯỜNG</b>: <b>{fmt.num(h['score'], 0)}/100</b> – {h['label']}")
        for v in h["components"].values():
            lines.append(f"• {v['label']}: {escape(v['detail'])}")
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
    vr, an = ctx["vol_range"], ctx["analog"]
    last = float(ctx["idx_hist"]["VN-Index"].iloc[-1])
    lines = [_head("🔮", "Triển vọng thống kê VN-Index", ctx["date"]), f"VN-Index hiện tại: <b>{fmt.num(last)}</b>\n"]
    for h in (5, 20):
        r = vr.get(h)
        if r:
            lines.append(f"📏 <b>{h} phiên tới</b> – biên dao động")
            lines.append(f"   • 68%: {fmt.num(r['lo68'], 0)} – {fmt.num(r['hi68'], 0)}")
            lines.append(f"   • 90%: {fmt.num(r['lo90'], 0)} – {fmt.num(r['hi90'], 0)}")
        a = an.get("horizons", {}).get(h) if an.get("available") else None
        if a and a["n"]:
            lines.append(f"   • Xác suất cao hơn hiện tại: <b>{fmt.frac_pct(a['p_up'], 0)}</b> {dot(a['p_up'] - a['base_p_up'])} "
                         f"(nền {fmt.frac_pct(a['base_p_up'], 0)}, {a['n']} phiên tương tự)")
            lines.append(f"   • Trung vị {fmt.pct(a['median'], 1)} · 10–90%: {fmt.pct(a['p10'], 1)} → {fmt.pct(a['p90'], 1)}\n")
    if an.get("available"):
        lines.append(f"🧩 Trạng thái hiện tại: {escape(an['state'])}")
    sig = ctx.get("signals") or []
    lines.append("🚨 Tín hiệu hôm nay: " + (", ".join(escape(s["rule"]) for s in sig) if sig else "không có"))
    if 5 in vr:
        lines.append(f"\n📐 σ ngày (EWMA λ=0,94) ≈ {fmt.num(vr[5]['sigma_d'] * 100, 2)}% · biên 90% bao trùm thực tế "
                     f"{fmt.frac_pct(vr[5]['coverage90'], 0)} số lần từ 2019")
    lines.append("<i>Ước lượng thống kê từ dữ liệu quá khứ, không phải dự báo chắc chắn.</i>")
    kb = [[("📊 Thị trường", "market"), ("📈 Biểu đồ VN-Index", "chart:VNINDEX")], [("🏠 Menu", "menu")]]
    text = "\n".join(lines)
    return (text, kb) if with_buttons else text


# ── cổ phiếu & watchlist ─────────────────────────────────────────────────────
def stock_card(symbol: str, ctx: Optional[Dict] = None):
    """Thẻ phân tích một mã: giá, xu hướng, động lượng, dòng vốn ngoại, rủi ro + kiểm tra 5 tiêu chí (tham khảo)."""
    from src.analytics.health import rsi
    s = symbol.upper().strip()
    ctx = _ctx(ctx)
    h = db.query_df("SELECT * FROM indicator_stock_daily WHERE symbol = ? ORDER BY trade_date", [s])
    if h.empty or ctx is None:
        return f"❓ Không tìm thấy dữ liệu cho <b>{escape(s)}</b> (chỉ hỗ trợ cổ phiếu HOSE).", BACK
    h = h[pd.to_datetime(h["trade_date"]) <= ctx["date"]]
    r = h.iloc[-1]
    c = h["close"].astype(float)
    ma20, ma50 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1]
    rsi14 = float(rsi(c).iloc[-1]) if len(c) > 15 else np.nan
    nf5, nf20 = h["net_flow"].tail(5).sum(), h["net_flow"].tail(20).sum()
    tv20 = h["tv"].tail(20).mean()
    r5 = (c.iloc[-1] / c.iloc[-6] - 1) * 100 if len(c) > 6 else np.nan
    r20 = (c.iloc[-1] / c.iloc[-21] - 1) * 100 if len(c) > 21 else np.nan
    wl = wi.get_watchlist()
    checks = [("Xu hướng (giá > MA20 > MA50)", bool(c.iloc[-1] > ma20 > ma50)),
              ("Động lượng (RSI14 trong 40–70)", bool(40 <= rsi14 <= 70)),
              ("Khối ngoại mua ròng 20 phiên", bool(nf20 > 0)),
              ("Thanh khoản ≥ 10 tỷ/phiên", bool(tv20 >= 10e9)),
              ("Room ngoại còn (< 95%)", bool((r["U"] if pd.notna(r["U"]) else 0) < 0.95))]
    n_ok = sum(ok for _, ok in checks)
    lines = [f"📈 <b>{s}</b> · {escape(str(r.get('sector') or ''))}",
             f"📅 Phiên {pd.Timestamp(r['trade_date']):%d/%m/%Y}\n{LINE}",
             f"💰 Giá đóng cửa: <b>{fmt.price(r['close'])}</b>  {dot(r['ret'])} {fmt.pct(r['ret'] * 100)}",
             f"📆 5 phiên {fmt.pct(r5, 1)} · 20 phiên {fmt.pct(r20, 1)} · so VN-Index hôm nay "
             f"{fmt.num((r['ER_I'] or 0) * 100, 2, True)} đ.%",
             "\n📐 <b>CHỈ BÁO</b>",
             f"• MA20: {fmt.price(ma20)} · MA50: {fmt.price(ma50)}",
             f"• RSI14: {fmt.num(rsi14, 1)} · KL/TB20: {fmt.num(r.get('vol_ratio'), 2, False, '×')}",
             f"• GTGD TB 20 phiên: {fmt.bn(tv20, 1, False)}",
             f"• Đóng góp VN-Index hôm nay: {fmt.num(r['C'], 2, True)} điểm",
             "\n🌏 <b>KHỐI NGOẠI</b>",
             f"• Hôm nay {dot(r['net_flow'])} {fmt.bn(r['net_flow'], 1)} · 5 phiên {fmt.bn(nf5, 1)} · 20 phiên {fmt.bn(nf20, 1)}",
             f"• Room đã dùng: {fmt.frac_pct(r['U'], 1)} · trạng thái: {ABSORB_LABELS.get(r['absorb_state'], '—')}",
             f"\n🧩 <b>KIỂM TRA 5 TIÊU CHÍ</b> ({n_ok}/5)"]
    lines += [f"{'🟢' if ok else '🔴'} {lbl}" for lbl, ok in checks]
    verdict = ("🟢 Nhiều tiêu chí tích cực" if n_ok >= 4 else "🟡 Trung tính – cần theo dõi thêm" if n_ok >= 2
               else "🔴 Đa số tiêu chí chưa đạt")
    lines.append(f"\n🏁 <b>TÓM TẮT</b>: {verdict}")
    lines.append("<i>Tiêu chí kỹ thuật mô tả trạng thái, không phải tín hiệu mua/bán.</i>")
    kb = [[("📈 Biểu đồ", f"chart:{s}"), ("🔄 Làm mới", f"stock:{s}")],
          [("➖ Bỏ theo dõi", f"rm:{s}") if s in wl else ("➕ Theo dõi", f"add:{s}"), ("👁 Watchlist", "watch")],
          [("🏠 Menu", "menu")]]
    return "\n".join(lines), kb


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
    kb += [[("💼 Tối ưu danh mục", "pf:Cân bằng"), ("🏠 Menu", "menu")]]
    text = "\n".join(lines)
    return (text, kb) if with_buttons else text


def portfolio(profile: str = "Cân bằng"):
    from src.analytics import portfolio as P
    wl = wi.get_watchlist()
    profs = P.profiles()
    profile = profile if profile in profs else "Cân bằng"
    a = P.analyze(wl, profile)
    kb = [[(("✅ " if k == profile else "") + k, f"pf:{k}") for k in profs], [("👁 Watchlist", "watch"), ("🏠 Menu", "menu")]]
    if not a["ok"]:
        return f"💼 <b>TỐI ƯU DANH MỤC</b>\n{LINE}\n{escape(a['reason'])}", kb
    prof, t = a["profile"], a["results"]["target"]
    w = t["w"].sort_values(ascending=False)
    lines = [f"💼 <b>TỐI ƯU DANH MỤC · {prof.name.upper()}</b>", f"{a['d0']:%d/%m/%Y} – {a['d1']:%d/%m/%Y} · {a['lookback']} phiên\n{LINE}",
             f"🎚 Biến động mục tiêu ≤ {prof.target_vol:.0%}/năm · tối đa {a['max_w']:.0%}/mã\n", "📊 <b>TỶ TRỌNG GỢI Ý</b>"]
    lines += [f"<code>{s:<4}</code> {bar(v, w.max(), 10)} {v:.0%}" for s, v in w.items() if v >= 0.005]
    lines += ["\n📐 <b>CHỈ SỐ RỦI RO – LỢI SUẤT</b>",
              f"• Lợi suất kỳ vọng: {dot(t['ret'])} {t['ret']:+.1%}/năm".replace(".", ","),
              f"• Biến động: {t['vol']:.1%}/năm · Sharpe {t['sharpe']:.2f}".replace(".", ","),
              f"• Beta: {t['beta']:.2f} · sụt giảm tối đa {t['mdd']:.0%}".replace(".", ","),
              f"• VaR 95% 1 ngày: {t['var95']:.2%}".replace(".", ","),
              "\n💡 <b>GỢI Ý</b>"]
    lines += [escape(x) for x in a["suggest"][:5]]
    lines.append("\n<i>Tối ưu trên dữ liệu quá khứ (Ledoit–Wolf, long-only) – tham khảo, không phải khuyến nghị.</i>")
    return "\n".join(lines), kb


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
