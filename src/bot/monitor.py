"""
Cảnh báo TỰ ĐỘNG qua bot Telegram – người dùng không cần hỏi, bot tự nhắn khi có biến động.

Chạy bên trong tiến trình bot (python -m src.bot.bot): mỗi 2 phút trong giờ giao dịch gọi SSI FastConnect V3
(nến 1 phút VN-Index + các mã watchlist, index_summary cho độ rộng & khối ngoại trong phiên); sau phiên, khi kho
có phiên mới, gửi tín hiệu xu hướng cuối ngày.

Loại cảnh báo (bật/tắt từng loại bằng /alerts):
  market – VN-Index vượt ngưỡng ±%, biến động mạnh 15 phút, vượt biên dao động dự báo EWMA 95%, cắt MA50,
           khối ngoại ròng trong phiên bất thường, độ rộng lệch mạnh
  watch  – mã đang theo dõi: vượt ngưỡng ±%, chạm trần/sàn, biến động mạnh 15 phút, khối lượng đột biến, phá đỉnh/đáy 20 phiên
  trend  – sau phiên: VN-Index đổi trạng thái xu hướng (MA50 / động lượng 20 phiên / khối ngoại 20 phiên) + xác suất
           tăng 5 & 20 phiên theo trạng thái tương tự; tín hiệu cuối ngày của mã theo dõi
Mỗi tín hiệu gửi tối đa 1 lần/ngày (khóa lưu trong data/bot_alerts.json, giữ được khi khởi động lại bot).
Đây là thông tin mô tả trạng thái, không phải khuyến nghị giao dịch.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from html import escape
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.common import fmt
from src.common.config import abs_path
from src.common.logging import get_logger
from src.common.timeutil import now_vn

log = get_logger(__name__)
STORE = abs_path("data/bot_alerts.json")
_LOCK = threading.Lock()
TYPES = {"market": "📊 Thị trường (VN-Index)", "watch": "👁 Mã đang theo dõi", "trend": "🔮 Xu hướng cuối phiên"}
LEVELS = {  # độ nhạy: ngưỡng VN-Index (%), ngưỡng mã (%), biến động 15 phút VN-Index / mã (%), bội số khối lượng
    "Thấp": {"idx": (1.5, 2.5), "stk": (5.0, 6.5), "idx15": 0.9, "stk15": 3.0, "volx": 2.0},
    "Vừa": {"idx": (1.0, 2.0), "stk": (3.0, 5.0), "idx15": 0.6, "stk15": 2.0, "volx": 1.5},
    "Cao": {"idx": (0.7, 1.5), "stk": (2.0, 4.0), "idx15": 0.4, "stk15": 1.5, "volx": 1.2},
}
Keyboard = List[List[Tuple[str, str]]]


# ── lưu trữ cài đặt + khóa chống trùng ────────────────────────────────────────
def _load() -> Dict:
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save(d: Dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(STORE)


def prefs(chat_id: str) -> Dict:
    p = _load().get("chats", {}).get(str(chat_id), {})
    return {"on": p.get("on", True), "types": {k: p.get("types", {}).get(k, True) for k in TYPES},
            "level": p.get("level", "Vừa") if p.get("level") in LEVELS else "Vừa"}


def set_pref(chat_id: str, **kw) -> Dict:
    with _LOCK:
        d = _load()
        cur = prefs(chat_id)
        if "type" in kw:
            cur["types"][kw.pop("type")] ^= True
        cur.update(kw)
        d.setdefault("chats", {})[str(chat_id)] = cur
        _save(d)
    return cur


def status() -> Dict:
    s = _load().get("state", {})
    return {"last_scan": s.get("last_scan"), "sent_today": len(s.get("keys", [])) if s.get("date") == str(now_vn().date()) else 0,
            "last_alert": s.get("last_alert")}


def _claim(keys: List[str], today: str) -> List[str]:
    """Trả về các khóa CHƯA gửi hôm nay và đánh dấu đã gửi."""
    with _LOCK:
        d = _load()
        st = d.get("state", {})
        if st.get("date") != today:
            st = {"date": today, "keys": [], "eod_date": st.get("eod_date")}
        new = [k for k in keys if k not in st["keys"]]
        st["keys"] += new
        st["last_scan"] = now_vn().strftime("%d/%m %H:%M:%S")
        if new:
            st["last_alert"] = st["last_scan"]
        d["state"] = st
        _save(d)
    return new


def _eod_done(date_str: Optional[str] = None) -> Optional[str]:
    with _LOCK:
        d = _load()
        st = d.setdefault("state", {})
        if date_str:
            st["eod_date"] = date_str
            _save(d)
        return st.get("eod_date")


# ── quy tắc (hàm thuần, kiểm thử được) ────────────────────────────────────────
def _pct(a, b) -> float:
    return (a / b - 1) * 100 if b else np.nan


def _move15(df: pd.DataFrame) -> float:
    """% thay đổi giá trong 15 phút gần nhất (theo dấu thời gian nến)."""
    t = df["ts"].iloc[-1] - pd.Timedelta(minutes=15)
    before = df[df["ts"] <= t]
    return _pct(df["close"].iloc[-1], before["close"].iloc[-1]) if len(before) else np.nan


def market_rules(df: pd.DataFrame, base: Dict, lv: Dict, summ: Optional[Dict] = None) -> List[Tuple[str, str]]:
    """[(khóa, dòng mô tả)] cho VN-Index. base: ref, sigma (σ ngày, %), ma50_prev (MA50 tính đến phiên trước), nf_sd."""
    out = []
    last, ref = float(df["close"].iloc[-1]), base["ref"]
    pct = _pct(last, ref)
    sign = "up" if pct > 0 else "dn"
    word = "tăng" if pct > 0 else "giảm"
    for th in lv["idx"]:
        if abs(pct) >= th:
            out.append((f"vni:{sign}:{th}", f"{'📈' if pct > 0 else '📉'} VN-Index {word} <b>{fmt.pct(pct)}</b> "
                                            f"({fmt.num(last, 2)} điểm) – vượt ngưỡng {fmt.num(th, 1)}%"))
    m15 = _move15(df)
    if pd.notna(m15) and abs(m15) >= lv["idx15"]:
        bucket = df["ts"].iloc[-1].strftime("%H") + ("a" if df["ts"].iloc[-1].minute < 30 else "b")
        out.append((f"vni15:{bucket}", f"⚡ Biến động mạnh: VN-Index {fmt.pct(m15)} chỉ trong 15 phút"))
    sig = base.get("sigma")
    if sig and abs(pct) >= 1.96 * sig:
        out.append((f"vniband:{sign}", f"🎯 Vượt <b>biên dao động dự báo 95%</b> của phiên (±{fmt.num(1.96 * sig, 2)}%) – "
                                       f"biến động lớn bất thường so với mô hình EWMA"))
    ma = base.get("ma50_prev")
    prev = base.get("prev_close")
    if ma and prev:
        if prev < ma <= last:
            out.append(("vnima50:up", f"🔀 VN-Index vượt lên <b>MA50</b> ({fmt.num(ma, 1)}) – trạng thái xu hướng ngắn hạn có thể chuyển sang tăng"))
        elif prev > ma >= last:
            out.append(("vnima50:dn", f"🔀 VN-Index thủng <b>MA50</b> ({fmt.num(ma, 1)}) – trạng thái xu hướng ngắn hạn có thể chuyển sang giảm"))
    if summ:
        nf = summ.get("nf")
        sd = base.get("nf_sd")
        if nf is not None and sd and abs(nf) >= 2 * sd:
            out.append((f"vninf:{'up' if nf > 0 else 'dn'}", f"🌏 Khối ngoại {'MUA' if nf > 0 else 'BÁN'} ròng <b>{fmt.bn(nf)}</b> "
                                                          f"trong phiên – gấp {abs(nf) / sd:.1f} lần độ lệch chuẩn 60 phiên"))
        up, dn = summ.get("up") or 0, summ.get("dn") or 0
        if up + dn >= 100 and max(up, dn) >= 4 * max(min(up, dn), 1):
            br = "tăng" if up > dn else "giảm"
            out.append((f"vnibreadth:{br}", f"🌊 Độ rộng lệch mạnh: 🟢 {up} mã tăng · 🔴 {dn} mã giảm – sắc {br} lan tỏa"))
    return out


def stock_rules(sym: str, df: pd.DataFrame, base: Dict, lv: Dict, now: datetime) -> List[Tuple[str, str]]:
    """base: ref, hi20, lo20, vol20 (KL trung bình 20 phiên)."""
    out = []
    last, ref = float(df["close"].iloc[-1]), base["ref"]
    pct = _pct(last, ref)
    sign, word = ("up", "tăng") if pct > 0 else ("dn", "giảm")
    for th in lv["stk"]:
        if abs(pct) >= th:
            out.append((f"{sym}:{sign}:{th}", f"{'📈' if pct > 0 else '📉'} {word} <b>{fmt.pct(pct)}</b> lên {fmt.price(last)} – vượt ngưỡng {fmt.num(th, 0)}%"))
    if pct >= 6.7:
        out.append((f"{sym}:ceil", "🟣 Chạm/sát giá <b>TRẦN</b>"))
    elif pct <= -6.7:
        out.append((f"{sym}:floor", "🔵 Chạm/sát giá <b>SÀN</b>"))
    m15 = _move15(df)
    if pd.notna(m15) and abs(m15) >= lv["stk15"]:
        bucket = df["ts"].iloc[-1].strftime("%H") + ("a" if df["ts"].iloc[-1].minute < 30 else "b")
        out.append((f"{sym}:m15:{bucket}", f"⚡ {fmt.pct(m15)} chỉ trong 15 phút"))
    vol, v20 = float(df["volume"].fillna(0).sum()), base.get("vol20")
    if v20 and vol >= lv["volx"] * v20 and (now.hour, now.minute) < (14, 30):
        out.append((f"{sym}:vol", f"🔊 Khối lượng đột biến: {fmt.num(vol / 1e6, 2)} tr cp, đã gấp {vol / v20:.1f} lần TB 20 phiên trước giờ ATC"))
    if base.get("hi20") and last > base["hi20"]:
        out.append((f"{sym}:hi20", f"↗ Vượt <b>đỉnh 20 phiên</b> ({fmt.price(base['hi20'])})"))
    if base.get("lo20") and last < base["lo20"]:
        out.append((f"{sym}:lo20", f"⚠️ Thủng <b>đáy 20 phiên</b> ({fmt.price(base['lo20'])})"))
    return out


# ── dữ liệu ───────────────────────────────────────────────────────────────────
_BASE: Dict = {}


def _bases(today) -> Dict:
    """Số liệu nền từ kho (tính 1 lần/ngày): tham chiếu, σ EWMA, MA50, độ lệch khối ngoại, đỉnh/đáy/KL 20 phiên."""
    if _BASE.get("date") == today:
        return _BASE
    from src.analytics import outlook
    from src.data import database as db
    v = db.query_df("SELECT trade_date, value FROM fact_daily_index WHERE index_code = 'VNINDEX' AND trade_date < ? "
                    "ORDER BY trade_date", [today])
    c = v.set_index(pd.to_datetime(v["trade_date"]))["value"].astype(float)
    sig = outlook.ewma_sigma(np.log(c / c.shift(1))).iloc[-1] * 100
    nf = db.query_df("SELECT NF_total FROM indicator_daily WHERE trade_date < ? ORDER BY trade_date DESC LIMIT 60", [today])
    _BASE.clear()
    _BASE.update(date=today, vni={"ref": float(c.iloc[-1]), "prev_close": float(c.iloc[-1]), "sigma": float(sig),
                                  "ma50_prev": float(c.tail(50).mean()), "nf_sd": float(nf["NF_total"].std())}, stocks={})
    return _BASE


def _stock_base(sym: str, today) -> Optional[Dict]:
    b = _BASE.setdefault("stocks", {})
    if sym not in b:
        from src.data import database as db
        h = db.query_df("SELECT close, vol FROM fact_daily_stock WHERE symbol = ? AND trade_date < ? AND close > 0 "
                        "ORDER BY trade_date DESC LIMIT 20", [sym, today])
        b[sym] = None if h.empty else {"ref": float(h["close"].iat[0]), "hi20": float(h["close"].max()),
                                       "lo20": float(h["close"].min()), "vol20": float(h["vol"].mean())}
    return b[sym]


def _summary_live(today) -> Optional[Dict]:
    try:
        from src.bot.intraday import _client
        r = _client().index_summary("VNINDEX", today)
        if not r:
            return None
        x = r[-1]
        f = lambda k: float(x[k]) if x.get(k) not in (None, "") else None  # noqa: E731
        return {"nf": f("netPurchasesForeignValue"), "up": int(f("totalAdvanceStock") or 0), "dn": int(f("totalDeclineStock") or 0)}
    except Exception as exc:  # noqa: BLE001
        log.warning("index_summary lỗi: %s", exc)
        return None


# ── quét ──────────────────────────────────────────────────────────────────────
def _targets(kind: str, allowed: List[str]) -> List[str]:
    return [c for c in allowed if prefs(c)["on"] and prefs(c)["types"][kind]]


def _level_for(chats: List[str]) -> Dict:
    """Nhiều người dùng: lấy độ nhạy cao nhất trong số chat nhận (đơn giản – đồ án thường chỉ 1 chat)."""
    order = ["Thấp", "Vừa", "Cao"]
    lv = max((prefs(c)["level"] for c in chats), key=order.index, default="Vừa")
    return LEVELS[lv]


def scan_intraday(allowed: List[str], now: Optional[datetime] = None) -> List[Tuple[List[str], str, Keyboard]]:
    from src.bot import intraday
    from src.analytics import watchlist_impact as wi
    now = now or now_vn()
    today = now.date()
    out = []
    mk, wt = _targets("market", allowed), _targets("watch", allowed)
    if not (mk or wt):
        return out
    base = _bases(today)
    hhmm = now.strftime("%H:%M")
    if mk:
        df, d = intraday.fetch("VNINDEX")
        if not df.empty and d == today:
            hits = market_rules(df, base["vni"], _level_for(mk), _summary_live(today))
            new = set(_claim([k for k, _ in hits], str(today)))
            lines = [t for k, t in hits if k in new]
            if lines:
                pct = _pct(float(df["close"].iloc[-1]), base["vni"]["ref"])
                txt = (f"🚨 <b>CẢNH BÁO THỊ TRƯỜNG</b> · {hhmm}\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines)
                       + f"\n\n• VN-Index hiện {fmt.num(float(df['close'].iloc[-1]), 2)} ({fmt.pct(pct)} so tham chiếu)"
                       + f"\n• Biên dao động bình thường 1 phiên (95%): ±{fmt.num(1.96 * base['vni']['sigma'], 2)}%")
                out.append((mk, txt, [[("📊 Thị trường", "market"), ("🔮 Triển vọng", "outlook")],
                                      [("📈 Biểu đồ VN-Index", "chart:VNINDEX"), ("🔔 Cài đặt cảnh báo", "alerts")]]))
    if wt:
        lv = _level_for(wt)
        for sym in wi.get_watchlist():
            b = _stock_base(sym, today)
            if not b:
                continue
            try:
                df, d = intraday.fetch(sym)
            except Exception as exc:  # noqa: BLE001
                log.warning("Không lấy được nến %s: %s", sym, exc)
                continue
            if df.empty or d != today:
                continue
            hits = stock_rules(sym, df, b, lv, now)
            new = set(_claim([k for k, _ in hits], str(today)))
            lines = [t for k, t in hits if k in new]
            if lines:
                last = float(df["close"].iloc[-1])
                txt = (f"👁 <b>{escape(sym)} – MÃ BẠN ĐANG THEO DÕI</b> · {hhmm}\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines)
                       + f"\n\n• Giá {fmt.price(last)} ({fmt.pct(_pct(last, b['ref']))} so tham chiếu) · "
                         f"KL {fmt.num(float(df['volume'].sum()) / 1e6, 2)} tr")
                out.append((wt, txt, [[("⏱ Trong phiên", f"intra:{sym}"), ("📈 Thẻ phân tích", f"stock:{sym}")],
                                      [("🏭 Ngành", f"sec:{sym}"), ("🔔 Cài đặt cảnh báo", "alerts")]]))
    if not out:
        _claim([], str(today))          # ghi thời điểm quét
    return out


def scan_eod(allowed: List[str]) -> List[Tuple[List[str], str, Keyboard]]:
    """Sau khi kho có phiên mới: đổi trạng thái xu hướng VN-Index + tín hiệu cuối ngày của mã theo dõi."""
    from src.analytics import outlook
    from src.analytics import watchlist_impact as wi
    from src.data import database as db
    from src.reports.context import latest_date
    tg = _targets("trend", allowed)
    d = latest_date()
    if not tg or d is None or _eod_done() == str(d.date()):
        return []
    _eod_done(str(d.date()))
    v = db.query_df("SELECT trade_date, value FROM fact_daily_index WHERE index_code = 'VNINDEX' ORDER BY trade_date")
    c = v.set_index(pd.to_datetime(v["trade_date"]))["value"].astype(float)
    nfh = db.query_df("SELECT trade_date, NF_total FROM indicator_daily ORDER BY trade_date")
    nf = nfh.set_index(pd.to_datetime(nfh["trade_date"]))["NF_total"]
    st = outlook.states(c, nf).dropna()
    lines = []
    if len(st) >= 2:
        a, b = st.iloc[-2], st.iloc[-1]
        lab = outlook.STATE_LABELS
        for k, name in (("trend", "Xu hướng"), ("mom", "Động lượng"), ("flow", "Dòng vốn ngoại")):
            if a[k] != b[k]:
                arrow = "🟢" if b[k] > a[k] else "🔴"
                lines.append(f"{arrow} {name}: {lab[k].get(int(a[k]), '?')} → <b>{lab[k].get(int(b[k]), '?')}</b>")
    wl_lines = []
    wl = wi.get_watchlist()
    if wl:
        s = db.query_df("SELECT symbol, ret, z_nf, net_flow, new_high20, new_low20, above_ma20 FROM indicator_stock_daily "
                        f"WHERE trade_date = ? AND symbol IN ({','.join('?' * len(wl))})", [d] + wl)
        prev = db.query_df("SELECT symbol, above_ma20 FROM indicator_stock_daily WHERE trade_date = "
                           "(SELECT MAX(trade_date) FROM indicator_stock_daily WHERE trade_date < ?) "
                           f"AND symbol IN ({','.join('?' * len(wl))})", [d] + wl).set_index("symbol")["above_ma20"]
        for r in s.itertuples():
            sig = []
            if r.new_high20:
                sig.append("đỉnh 20 phiên mới")
            if r.new_low20:
                sig.append("đáy 20 phiên mới ⚠️")
            if pd.notna(r.z_nf) and abs(r.z_nf) >= 2:
                sig.append(f"khối ngoại {'mua' if r.net_flow > 0 else 'bán'} ròng bất thường {fmt.bn(r.net_flow, 1)} (z = {fmt.num(r.z_nf, 1, True)})")
            pv = prev.get(r.symbol)
            if pd.notna(pv) and pd.notna(r.above_ma20) and bool(pv) != bool(r.above_ma20):
                sig.append("vượt lên MA20 🟢" if r.above_ma20 else "thủng MA20 🔴")
            if sig:
                wl_lines.append(f"• <b>{r.symbol}</b> ({fmt.pct(r.ret * 100)}): " + "; ".join(sig))
    if not lines and not wl_lines:
        return []
    txt = [f"🔮 <b>TÍN HIỆU XU HƯỚNG CUỐI PHIÊN</b> · {d:%d/%m/%Y}\n━━━━━━━━━━━━━━━━━━"]
    if lines:
        txt += ["<b>VN-Index đổi trạng thái:</b>"] + lines
    if wl_lines:
        txt += ["\n👁 <b>Mã bạn đang theo dõi:</b>"] + wl_lines
    txt.append("\n<i>Mô tả thay đổi trạng thái, không phải tín hiệu mua/bán.</i>")
    return [(tg, "\n".join(txt), [[("🧭 Chẩn đoán phiên", "diag"), ("👁 Watchlist", "watch")], [("🔔 Cài đặt cảnh báo", "alerts")]])]


def scan(allowed: List[str], now: Optional[datetime] = None) -> List[Tuple[List[str], str, Keyboard]]:
    from src.bot.intraday import in_session
    now = now or now_vn()
    out = []
    if in_session(now):
        out += scan_intraday(allowed, now)
    elif (now.hour, now.minute) >= (15, 10) or now.hour < 8:
        out += scan_eod(allowed)
    return out


def interval(now: Optional[datetime] = None) -> int:
    from src.bot.intraday import in_session
    return 120 if in_session(now) else 300


def preview(chat_id: str) -> Tuple[str, Keyboard]:
    """Nút "Quét thử": trong giờ giao dịch = quét thật; ngoài giờ = chạy quy tắc trên phiên gần nhất (không đánh dấu đã gửi)."""
    from src.bot import intraday
    from src.analytics import watchlist_impact as wi
    p = prefs(chat_id)
    lv = LEVELS[p["level"]]
    df, d = intraday.fetch("VNINDEX")
    if df.empty:
        return "⏱ SSI chưa trả dữ liệu trong phiên.", [[("🔔 Cài đặt cảnh báo", "alerts")]]
    live = intraday.in_session() and d == now_vn().date()
    base = _bases(d)
    at = df["ts"].iloc[-1].to_pydatetime()
    lines = [f"🔍 <b>QUÉT {'TRỰC TIẾP' if live else 'THỬ TRÊN PHIÊN ' + d.strftime('%d/%m/%Y')}</b> · độ nhạy {p['level']}",
             "━━━━━━━━━━━━━━━━━━"]
    hits = market_rules(df, base["vni"], lv, _summary_live(d))
    lines.append(f"📊 <b>VN-Index</b> {fmt.num(float(df['close'].iloc[-1]), 2)} ({fmt.pct(_pct(float(df['close'].iloc[-1]), base['vni']['ref']))})")
    lines += [f"  {t}" for _, t in hits] or ["  ✅ Không có tín hiệu bất thường"]
    for sym in wi.get_watchlist():
        b = _stock_base(sym, d)
        if not b:
            continue
        sdf, sd = intraday.fetch(sym)
        if sdf.empty or sd != d:
            continue
        h = stock_rules(sym, sdf, b, lv, at)
        last = float(sdf["close"].iloc[-1])
        lines.append(f"\n👁 <b>{sym}</b> {fmt.price(last)} ({fmt.pct(_pct(last, b['ref']))})")
        lines += [f"  {t}" for _, t in h] or ["  ✅ Không có tín hiệu bất thường"]
    if not live:
        lines.append("\n<i>Ngoài giờ giao dịch: đây là các cảnh báo bot SẼ gửi nếu tình huống này xảy ra trong phiên.</i>")
    return "\n".join(lines), [[("🔔 Cài đặt cảnh báo", "alerts"), ("🏠 Menu", "menu")]]


# ── giao diện /alerts ─────────────────────────────────────────────────────────
def settings_view(chat_id: str) -> Tuple[str, Keyboard]:
    p, s = prefs(chat_id), status()
    lv = LEVELS[p["level"]]
    lines = ["🔔 <b>CẢNH BÁO TỰ ĐỘNG</b>\n━━━━━━━━━━━━━━━━━━",
             f"Trạng thái: <b>{'🟢 ĐANG BẬT' if p['on'] else '🔴 ĐANG TẮT'}</b> · độ nhạy <b>{p['level']}</b>",
             "Bot tự nhắn khi có biến động – bạn không cần hỏi. Quét mỗi 2 phút trong giờ giao dịch (SSI trực tiếp).", ""]
    for k, name in TYPES.items():
        lines.append(f"{'✅' if p['types'][k] else '⬜'} {name}")
    lines += ["", f"<b>Ngưỡng ({p['level']})</b>",
              f"• VN-Index: ±{fmt.num(lv['idx'][0], 1)}% / ±{fmt.num(lv['idx'][1], 1)}% · 15 phút ±{fmt.num(lv['idx15'], 1)}% · "
              "vượt biên dự báo 95% · cắt MA50 · khối ngoại ròng |z| ≥ 2 · độ rộng lệch ≥ 4 lần",
              f"• Mã theo dõi: ±{fmt.num(lv['stk'][0], 1)}% / ±{fmt.num(lv['stk'][1], 1)}% · 15 phút ±{fmt.num(lv['stk15'], 1)}% · "
              f"trần/sàn · KL ≥ {fmt.num(lv['volx'], 1)}× TB20 · phá đỉnh/đáy 20 phiên",
              "• Cuối phiên: đổi trạng thái xu hướng + xác suất tăng 5/20 phiên",
              "", f"Lần quét gần nhất: {s['last_scan'] or '—'} · đã gửi hôm nay: {s['sent_today']} tín hiệu"]
    kb = [[("🔕 Tắt tất cả" if p["on"] else "🔔 Bật cảnh báo", "al:off" if p["on"] else "al:on")],
          [(("✅ " if p["types"][k] else "⬜ ") + n.split(" ", 1)[1], f"al:t:{k}") for k, n in list(TYPES.items())[:2]],
          [(("✅ " if p["types"]["trend"] else "⬜ ") + TYPES["trend"].split(" ", 1)[1], "al:t:trend")],
          [((("● " if p["level"] == x else "") + f"Nhạy {x.lower()}"), f"al:lv:{x}") for x in LEVELS],
          [("🔍 Quét thử ngay", "al:scan"), ("🏠 Menu", "menu")]]
    return "\n".join(lines), kb
