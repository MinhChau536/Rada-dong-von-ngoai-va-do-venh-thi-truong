"""
Banner đầu trang có hình minh họa (SVG nội tuyến – không phụ thuộc ảnh ngoài, chạy được khi offline) và các kiểu nền
có thể đổi ở thanh bên (gồm ảnh nền tự tải lên). Màu lấy từ theme.py.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Dict, Optional

from src.common.config import abs_path

W = "rgba(255,255,255,{a})"


def _w(a: float) -> str:
    return W.format(a=a)


# ── hình minh họa theo trang (viewBox 0 0 320 140) ────────────────────────────
def _candles() -> str:
    data = [(20, 90, 70, 100, 60), (45, 80, 62, 92, 55), (70, 64, 74, 82, 50), (95, 70, 52, 76, 45), (120, 54, 40, 62, 32),
            (145, 42, 50, 58, 36), (170, 50, 36, 56, 28), (195, 38, 26, 44, 20), (220, 30, 40, 48, 24), (245, 40, 22, 46, 16)]
    out = []
    for x, o, c, lo, hi in data:
        up = c < o
        col = "#4ADE80" if up else "#F87171"
        out.append(f'<line x1="{x}" y1="{hi}" x2="{x}" y2="{lo + 10}" stroke="{_w(.7)}" stroke-width="1.5"/>'
                   f'<rect x="{x - 6}" y="{min(o, c)}" width="12" height="{max(abs(o - c), 3)}" rx="2" fill="{col}"/>')
    line = " ".join(f"{x},{(o + c) / 2 - 4}" for x, o, c, _, _ in data)
    return ("".join(out) + f'<polyline points="{line}" fill="none" stroke="#FDE68A" stroke-width="2.5" stroke-linecap="round"/>'
            + "".join(f'<rect x="{x - 6}" y="{126 - h}" width="12" height="{h}" fill="{_w(.25)}"/>'
                      for x, h in zip(range(20, 260, 25), (10, 14, 8, 18, 12, 20, 9, 16, 22, 13))))


def _waterfall() -> str:
    bars = [(30, 70, 30, "#4ADE80"), (70, 50, 20, "#4ADE80"), (110, 40, 10, "#4ADE80"), (150, 40, 18, "#F87171"),
            (190, 30, 22, "#4ADE80"), (230, 30, 0, "")]
    out = []
    for x, y, h, c in bars[:-1]:
        out.append(f'<rect x="{x}" y="{y}" width="28" height="{h}" rx="3" fill="{c}"/>')
    out.append(f'<rect x="230" y="30" width="28" height="70" rx="3" fill="#FDE68A"/>')
    out.append(f'<line x1="20" y1="100" x2="270" y2="100" stroke="{_w(.6)}" stroke-width="1.5"/>')
    out.append(f'<path d="M30 105 Q140 135 260 105" fill="none" stroke="{_w(.35)}" stroke-dasharray="4 4"/>')
    return "".join(out)


def _radar() -> str:
    rings = "".join(f'<circle cx="160" cy="72" r="{r}" fill="none" stroke="{_w(.35)}" stroke-width="1.2"/>' for r in (18, 36, 54, 70))
    sweep = (f'<path d="M160 72 L160 2 A70 70 0 0 1 226 50 Z" fill="{_w(.18)}"/>'
             f'<line x1="160" y1="72" x2="226" y2="50" stroke="#FDE68A" stroke-width="2.5"/>')
    blips = "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c}"/>' for x, y, r, c in
                    ((190, 40, 4, "#4ADE80"), (128, 58, 3.5, "#F87171"), (175, 105, 3, "#4ADE80"), (205, 85, 4.5, "#FDE68A")))
    globe = (f'<circle cx="270" cy="40" r="22" fill="none" stroke="{_w(.6)}" stroke-width="1.5"/>'
             f'<ellipse cx="270" cy="40" rx="9" ry="22" fill="none" stroke="{_w(.45)}"/>'
             f'<line x1="248" y1="40" x2="292" y2="40" stroke="{_w(.45)}"/>'
             f'<path d="M232 92 C 250 70 262 70 276 74" fill="none" stroke="#FDE68A" stroke-width="2" marker-end="url(#arr)"/>')
    return rings + sweep + blips + globe


def _calendar() -> str:
    cells = "".join(f'<rect x="{60 + c * 28}" y="{50 + r * 22}" width="22" height="16" rx="3" fill="{_w(.22 if (r, c) != (1, 3) else .0)}"/>'
                    for r in range(3) for c in range(6))
    return (f'<rect x="50" y="18" width="178" height="110" rx="10" fill="{_w(.12)}" stroke="{_w(.5)}" stroke-width="1.5"/>'
            f'<rect x="50" y="18" width="178" height="24" rx="10" fill="{_w(.3)}"/>'
            f'<line x1="85" y1="10" x2="85" y2="26" stroke="{_w(.8)}" stroke-width="4" stroke-linecap="round"/>'
            f'<line x1="193" y1="10" x2="193" y2="26" stroke="{_w(.8)}" stroke-width="4" stroke-linecap="round"/>' + cells
            + '<polygon points="153,68 157,78 168,78 159,84 163,95 153,88 143,95 147,84 138,78 149,78" fill="#FDE68A"/>'
            + f'<path d="M248 120 L248 40 L290 52 L248 64" fill="#F87171" stroke="{_w(.7)}" stroke-width="1.5"/>')


def _eye_pie() -> str:
    return (f'<path d="M40 70 Q110 10 180 70 Q110 130 40 70 Z" fill="{_w(.14)}" stroke="{_w(.7)}" stroke-width="2"/>'
            f'<circle cx="110" cy="70" r="24" fill="{_w(.25)}"/><circle cx="110" cy="70" r="11" fill="#FDE68A"/>'
            '<circle cx="250" cy="70" r="46" fill="#14B8A6"/>'
            '<path d="M250 70 L250 24 A46 46 0 0 1 294 82 Z" fill="#FDE68A"/>'
            '<path d="M250 70 L294 82 A46 46 0 0 1 222 106 Z" fill="#F87171"/>'
            f'<circle cx="250" cy="70" r="18" fill="{_w(.0)}" stroke="{_w(.5)}"/>')


def _report() -> str:
    return (f'<rect x="60" y="14" width="96" height="118" rx="8" fill="{_w(.9)}"/>'
            + "".join(f'<rect x="74" y="{34 + i * 14}" width="{68 - (i % 3) * 14}" height="5" rx="2" fill="#94A3B8"/>' for i in range(4))
            + '<rect x="74" y="96" width="10" height="22" fill="#14B8A6"/><rect x="90" y="86" width="10" height="32" fill="#14B8A6"/>'
              '<rect x="106" y="100" width="10" height="18" fill="#F87171"/><rect x="122" y="80" width="10" height="38" fill="#14B8A6"/>'
              f'<path d="M190 80 L292 30 L262 120 L238 94 Z" fill="{_w(.85)}"/><path d="M238 94 L292 30 L226 104 Z" fill="{_w(.55)}"/>'
              f'<path d="M180 120 Q 200 110 214 100" fill="none" stroke="{_w(.5)}" stroke-dasharray="4 4"/>')


def _shield() -> str:
    db_ = "".join(f'<ellipse cx="80" cy="{40 + i * 26}" rx="40" ry="10" fill="{_w(.25 + i * .1)}" stroke="{_w(.6)}"/>' for i in range(3))
    return (db_ + f'<path d="M200 18 L262 38 L262 74 Q262 112 200 132 Q138 112 138 74 L138 38 Z" fill="{_w(.18)}" stroke="{_w(.8)}" stroke-width="2"/>'
            '<path d="M174 76 L194 96 L230 56" fill="none" stroke="#4ADE80" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>')


def _book() -> str:
    return (f'<path d="M40 30 Q100 16 150 34 L150 128 Q100 112 40 124 Z" fill="{_w(.85)}"/>'
            f'<path d="M260 30 Q200 16 150 34 L150 128 Q200 112 260 124 Z" fill="{_w(.65)}"/>'
            + "".join(f'<line x1="58" y1="{48 + i * 14}" x2="134" y2="{44 + i * 14}" stroke="#94A3B8" stroke-width="3"/>' for i in range(5))
            + '<text x="182" y="92" font-size="48" font-family="serif" font-weight="700" fill="#0F766E">Σ</text>'
              '<text x="222" y="74" font-size="22" font-family="serif" font-style="italic" fill="#0F766E">β</text>')


def _plug() -> str:
    return (f'<rect x="200" y="30" width="80" height="82" rx="10" fill="{_w(.18)}" stroke="{_w(.7)}" stroke-width="1.5"/>'
            + "".join(f'<rect x="212" y="{42 + i * 22}" width="56" height="14" rx="4" fill="{_w(.3)}"/>'
                      f'<circle cx="260" cy="{49 + i * 22}" r="3" fill="#4ADE80"/>' for i in range(3))
            + f'<path d="M30 110 C 90 110 110 60 170 70" fill="none" stroke="#FDE68A" stroke-width="4"/>'
              f'<rect x="160" y="58" width="28" height="24" rx="5" fill="{_w(.85)}"/>'
              f'<line x1="188" y1="64" x2="200" y2="64" stroke="{_w(.85)}" stroke-width="3"/>'
              f'<line x1="188" y1="76" x2="200" y2="76" stroke="{_w(.85)}" stroke-width="3"/>')


ART = {"tong-quan": _candles, "dan-dat": _waterfall, "khoi-ngoai": _radar, "su-kien-ftse": _calendar,
       "watchlist": _eye_pie, "bao-cao": _report, "chat-luong": _shield, "phuong-phap": _book, "ket-noi": _plug}
TITLE_TO_SLUG = {"Tổng quan thị trường": "tong-quan", "Dẫn dắt & độ vênh": "dan-dat", "Ra-đa khối ngoại": "khoi-ngoai",
                 "Sự kiện FTSE": "su-kien-ftse", "Watchlist Impact": "watchlist", "Báo cáo & Telegram": "bao-cao",
                 "Chất lượng dữ liệu": "chat-luong", "Phương pháp & giới hạn": "phuong-phap", "Kết nối dữ liệu": "ket-noi"}
GRADIENTS = {"tong-quan": ("#0F766E", "#1E3A8A"), "dan-dat": ("#7C3AED", "#1E40AF"), "khoi-ngoai": ("#0E7490", "#134E4A"),
             "su-kien-ftse": ("#B45309", "#7C2D12"), "watchlist": ("#BE185D", "#5B21B6"), "bao-cao": ("#1D4ED8", "#0F766E"),
             "chat-luong": ("#15803D", "#0F172A"), "phuong-phap": ("#334155", "#0F766E"), "ket-noi": ("#0369A1", "#312E81")}


def art_svg(slug: str) -> str:
    fn = ART.get(slug, _candles)
    return ('<svg viewBox="0 0 320 140" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" aria-hidden="true">'
            '<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">'
            '<path d="M0,0 L8,4 L0,8 z" fill="#FDE68A"/></marker></defs>' + fn() + "</svg>")


def banner_html(title: str, sub: str, pills_html: str = "") -> str:
    slug = TITLE_TO_SLUG.get(title, "tong-quan")
    c1, c2 = GRADIENTS.get(slug, GRADIENTS["tong-quan"])
    return (f'<div class="ffr-banner" style="background:linear-gradient(120deg,{c1} 0%,{c2} 100%)">'
            f'<div class="ffr-banner-txt"><div class="ffr-banner-title">{title}</div><div class="ffr-banner-sub">{sub}</div>'
            f'<div class="ffr-banner-pills">{pills_html}</div></div>'
            f'<div class="ffr-banner-art">{art_svg(slug)}</div></div>')


# ── nền trang ────────────────────────────────────────────────────────────────
BACKGROUNDS = ["Mặc định", "Lưới biểu đồ", "Sóng ngọc", "Bình minh", "Đêm sao", "Nến mờ", "Ảnh của tôi"]
PREFS = abs_path("data/ui_prefs.json")
CUSTOM_DIR = abs_path("data")


def load_prefs() -> Dict:
    try:
        return json.loads(PREFS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_prefs(**kw) -> None:
    p = load_prefs()
    p.update(kw)
    PREFS.parent.mkdir(parents=True, exist_ok=True)
    PREFS.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")


def save_custom_image(data: bytes, name: str) -> str:
    ext = Path(name).suffix.lower() or ".png"
    target = CUSTOM_DIR / f"ui_background{ext}"
    for old in CUSTOM_DIR.glob("ui_background.*"):
        old.unlink(missing_ok=True)
    target.write_bytes(data)
    return str(target.name)


def _custom_uri() -> Optional[str]:
    files = sorted(CUSTOM_DIR.glob("ui_background.*"))
    if not files:
        return None
    mime = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp", ".gif": "gif"}.get(files[0].suffix.lower(), "png")
    return f"data:image/{mime};base64," + base64.b64encode(files[0].read_bytes()).decode()


def _svg_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def background_css(choice: str, dark: bool, opacity: float = 0.85) -> str:
    """CSS nền cho .stApp (lớp stAppViewContainer phía trên được làm trong suốt). Lớp phủ giữ chữ dễ đọc trên ảnh."""
    body = _background_body(choice, dark, opacity)
    if not body:
        return ""
    return ("html, body, [data-testid='stAppViewContainer'], [data-testid='stMain'] { background: transparent !important; }"
            + body)


def _background_body(choice: str, dark: bool, opacity: float) -> str:
    base = "#0B1320" if dark else "#F4F6F9"
    ov = f"rgba(11,19,32,{opacity})" if dark else f"rgba(244,246,249,{opacity})"
    layer = None
    if choice == "Lưới biểu đồ":
        g = "rgba(148,163,184,.13)" if not dark else "rgba(148,163,184,.08)"
        return (f".stApp {{ background-color:{base} !important; background-image: linear-gradient({g} 1px, transparent 1px),"
                f" linear-gradient(90deg, {g} 1px, transparent 1px) !important; background-size: 28px 28px !important; }}")
    if choice == "Sóng ngọc":
        layer = ("linear-gradient(160deg,#ccfbf1 0%,#e0f2fe 45%,#f0fdfa 100%)" if not dark
                 else "linear-gradient(160deg,#042f2e 0%,#0b1320 55%,#082f49 100%)")
        waves = ('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="300" viewBox="0 0 1200 300">'
                 '<path d="M0 200 C300 120 600 280 900 190 C1050 150 1150 170 1200 180 L1200 300 L0 300Z" fill="#14B8A6" fill-opacity=".12"/>'
                 '<path d="M0 240 C350 170 650 300 1000 230 C1100 210 1160 220 1200 230 L1200 300 L0 300Z" fill="#0F766E" fill-opacity=".12"/></svg>')
        return (f".stApp {{ background: url('{_svg_uri(waves)}') bottom/100% auto no-repeat fixed, {layer} !important; }}")
    if choice == "Bình minh":
        layer = ("linear-gradient(135deg,#fff7ed 0%,#fef3c7 40%,#fce7f3 100%)" if not dark
                 else "linear-gradient(135deg,#1c1917 0%,#3b0764 60%,#0b1320 100%)")
        return f".stApp {{ background:{layer} fixed !important; }}"
    if choice == "Đêm sao":
        stars = "".join(f'<circle cx="{(i * 97) % 400}" cy="{(i * 61) % 400}" r="{1 + (i % 3) * .5}" fill="#fff" fill-opacity="{.25 + (i % 4) * .12}"/>'
                        for i in range(60))
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400">{stars}</svg>'
        grad = "linear-gradient(180deg,#0B1320 0%,#1E1B4B 100%)" if dark else "linear-gradient(180deg,#1E293B 0%,#334155 100%)"
        extra = "" if dark else (" [data-testid='stMainBlockContainer'] { background:rgba(244,246,249,.94); border-radius:16px;"
                                 " padding:18px 26px !important; margin-top:12px; }")
        return f".stApp {{ background: url('{_svg_uri(svg)}'), {grad} fixed !important; }}" + extra
    if choice == "Nến mờ":
        c = "#0F766E" if not dark else "#2DD4BF"
        cand = "".join(f'<line x1="{x}" y1="{y - 18}" x2="{x}" y2="{y + 26}" stroke="{c}" stroke-opacity=".10" stroke-width="2"/>'
                       f'<rect x="{x - 6}" y="{y}" width="12" height="{12 + (x % 3) * 6}" fill="{c}" fill-opacity=".08"/>'
                       for x, y in ((20, 60), (60, 40), (100, 70), (140, 30), (180, 50)))
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="140">{cand}</svg>'
        return f".stApp {{ background: url('{_svg_uri(svg)}') repeat, {base} !important; }}"
    if choice == "Ảnh của tôi":
        uri = _custom_uri()
        if uri:
            return (f".stApp {{ background: linear-gradient({ov},{ov}), url('{uri}') center/cover no-repeat fixed !important; }}")
    return ""


def banner_css(dark: bool) -> str:
    return """
.ffr-banner { position:relative; display:flex; align-items:stretch; justify-content:space-between; gap:16px; border-radius:18px;
  padding:20px 26px; margin:2px 0 14px; color:#fff; overflow:hidden; box-shadow:0 10px 28px rgba(15,23,42,.18); min-height:132px; }
.ffr-banner::after { content:""; position:absolute; inset:0; background:radial-gradient(circle at 85% -20%, rgba(255,255,255,.22), transparent 55%);
  pointer-events:none; }
.ffr-banner-txt { position:relative; z-index:1; display:flex; flex-direction:column; justify-content:center; max-width:62%; }
.ffr-banner-title { font-size:28px; font-weight:800; letter-spacing:-.4px; line-height:1.15; }
.ffr-banner-sub { font-size:14px; opacity:.88; margin-top:6px; line-height:1.45; }
.ffr-banner-pills { margin-top:10px; }
.ffr-banner-pills .ffr-pill { background:rgba(255,255,255,.16) !important; color:#fff !important; border-color:rgba(255,255,255,.3) !important;
  margin:0 6px 0 0 !important; }
.ffr-banner-art { position:relative; z-index:1; width:300px; min-width:220px; height:120px; }
@media (max-width: 900px) { .ffr-banner-art { display:none; } .ffr-banner-txt { max-width:100%; } .ffr-banner-title { font-size:22px; } }
"""
