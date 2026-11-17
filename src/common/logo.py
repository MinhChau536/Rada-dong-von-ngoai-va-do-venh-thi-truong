"""
Logo FTSE Flow Radar – một thiết kế, hai định dạng:
  • SVG (giao diện web, thanh bên)     → svg(size)
  • PNG (PDF, biểu tượng tab trình duyệt) → png_path()  (vẽ bằng Pillow, lưu ở assets/logo/ffr_logo.png)

Ý tưởng: ô vuông bo góc chuyển màu ngọc lam → xanh đậm; ba cung radar đồng tâm ở góc dưới trái và vệt quét
(“ra-đa”), đường dòng vốn đi lên cắt qua radar (“flow”), điểm sáng vàng ở đỉnh – tín hiệu được phát hiện.
"""
from __future__ import annotations

from pathlib import Path

from src.common.config import ROOT

TEAL, NAVY, GOLD = "#14B8A6", "#0B3B5C", "#FBBF24"
FLOW = [(14, 50), (24, 41), (32, 45), (49, 24)]          # đường dòng vốn trên lưới 64×64
CENTER = (14, 50)
RADII = (12, 22, 32)


def svg(size: int = 40, uid: str = "ffr") -> str:
    pts = " ".join(f"{x},{y}" for x, y in FLOW)
    cx, cy = CENTER
    arcs = "".join(f'<path d="M{cx} {cy - r} A{r} {r} 0 0 1 {cx + r} {cy}" fill="none" stroke="#fff" '
                   f'stroke-opacity="{0.22 + 0.12 * i}" stroke-width="2.4" stroke-linecap="round"/>' for i, r in enumerate(RADII))
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="FTSE Flow Radar">'
            f'<defs><linearGradient id="{uid}g" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{TEAL}"/><stop offset="1" stop-color="{NAVY}"/></linearGradient>'
            f'<linearGradient id="{uid}s" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity=".0"/>'
            f'<stop offset="1" stop-color="#fff" stop-opacity=".28"/></linearGradient></defs>'
            f'<rect width="64" height="64" rx="15" fill="url(#{uid}g)"/>'
            f'<path d="M{cx} {cy} L{cx} {cy - 32} A32 32 0 0 1 {cx + 22.6} {cy - 22.6} Z" fill="url(#{uid}s)"/>'
            f'{arcs}'
            f'<polyline points="{pts}" fill="none" stroke="#fff" stroke-width="4.6" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{cx}" cy="{cy}" r="3.2" fill="#fff"/>'
            f'<circle cx="49" cy="24" r="8" fill="{GOLD}" fill-opacity=".25"/>'
            f'<circle cx="49" cy="24" r="4.6" fill="{GOLD}"/></svg>')


def png_path(size: int = 512) -> Path:
    """Vẽ (một lần) và trả đường dẫn PNG của logo."""
    out = ROOT / "assets" / "logo" / "ffr_logo.png"
    if out.exists():
        return out
    from PIL import Image, ImageDraw
    k = 4                                                   # siêu lấy mẫu rồi thu nhỏ → viền mịn
    S = size * k
    u = S / 64

    def hx(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    a, b = hx(TEAL), hx(NAVY)
    grad = Image.new("RGB", (S, S))
    px = grad.load()
    for y in range(0, S, k):
        for x in range(0, S, k):
            t = (x + y) / (2 * S)
            c = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
            for dy in range(k):
                for dx in range(k):
                    px[x + dx, y + dy] = c
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(15 * u), fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    over = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    cx, cy = CENTER[0] * u, CENTER[1] * u
    d.pieslice([cx - 32 * u, cy - 32 * u, cx + 32 * u, cy + 32 * u], 270, 315, fill=(255, 255, 255, 50))
    for i, r in enumerate(RADII):
        d.arc([cx - r * u, cy - r * u, cx + r * u, cy + r * u], 270, 360, fill=(255, 255, 255, int(255 * (0.22 + 0.12 * i))),
              width=int(2.4 * u))
    pts = [(x * u, y * u) for x, y in FLOW]
    d.line(pts, fill=(255, 255, 255, 255), width=int(4.6 * u), joint="curve")
    for x, y in pts[:1] + pts[-1:]:
        rr = 2.3 * u
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(255, 255, 255, 255))
    d.ellipse([cx - 3.2 * u, cy - 3.2 * u, cx + 3.2 * u, cy + 3.2 * u], fill=(255, 255, 255, 255))
    g = hx(GOLD)
    for r, al in ((8, 64), (4.6, 255)):
        d.ellipse([49 * u - r * u, 24 * u - r * u, 49 * u + r * u, 24 * u + r * u], fill=g + (al,))
    img = Image.alpha_composite(img, over).resize((size, size), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    (out.parent / "ffr_logo.svg").write_text(svg(256), encoding="utf-8")
    return out
