"""
Khung PDF dùng chung (giữ khung trang bìa/kiểu chữ của reports/pdf_generator.py, reports/cover.py giữa kỳ – bước B9).
fpdf2 + font Be Vietnam Pro (assets/fonts, giấy phép OFL). Màu lấy từ src/app/theme.py (một nguồn màu).
Biểu đồ vẽ bằng hình học fpdf (thanh ngang) từ cùng bảng chỉ báo → không cần kaleido/trình duyệt.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from fpdf import FPDF

from src.app.theme import LIGHT
from src.common.config import ROOT, get

FONT_DIR = ROOT / "assets" / "fonts"


def hex2rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class FFRPdf(FPDF):
    def __init__(self, title: str, subtitle: str, banner: str, demo: bool = False):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.p = LIGHT
        self.doc_title, self.doc_sub, self.banner, self.demo = title, subtitle, banner, demo
        self.add_font("BVP", "", str(FONT_DIR / "BeVietnamPro-Regular.ttf"))
        self.add_font("BVP", "B", str(FONT_DIR / "BeVietnamPro-Bold.ttf"))
        self.add_font("BVP", "I", str(FONT_DIR / "BeVietnamPro-Medium.ttf"))
        self.set_auto_page_break(True, margin=16)
        self.set_margins(14, 14, 14)

    # Be Vietnam Pro không có chữ Hy Lạp → thay ký hiệu bằng chữ Latin tương đương trong PDF
    GREEK = {"ε": "eps", "β": "beta", "Ω": "Omega", "⁺": "+", "⁻": "-", "Δ": "Δ".replace("Δ", "d"), "Σ": "Tổng ", "τ": "tau",
             "ρ": "rho", "δ": "delta", "μ": "mu", "λ": "lambda", "α": "alpha", "≥": ">=", "≤": "<=",
             "σ": "sigma", "√": "căn ", "→": "->", "▲": "trên ", "▼": "dưới "}

    def normalize_text(self, text):
        for k, v in self.GREEK.items():
            text = text.replace(k, v)
        return super().normalize_text(text)

    def color(self, key_or_hex: str, what: str = "text"):
        rgb = hex2rgb(self.p.get(key_or_hex, key_or_hex))
        {"text": self.set_text_color, "fill": self.set_fill_color, "draw": self.set_draw_color}[what](*rgb)

    def header(self):
        self.color("sidebar", "fill")
        self.rect(0, 0, 210, 18, "F")
        self.color("#14B8A6", "fill")
        self.rect(14, 5, 8, 8, "F")
        self.set_xy(14, 5.6)
        self.set_font("BVP", "B", 9)
        self.set_text_color(255, 255, 255)
        self.cell(8, 7, "F", align="C")
        self.set_xy(25, 4)
        self.set_font("BVP", "B", 11)
        self.cell(100, 6, f"{get('app.name')} · {self.doc_title}")
        self.set_xy(25, 10)
        self.set_font("BVP", "", 7.5)
        self.set_text_color(199, 210, 224)
        self.cell(120, 4, self.doc_sub)
        self.set_xy(120, 6)
        self.set_font("BVP", "B", 7.5)
        self.set_text_color(253, 230, 138)
        self.cell(76, 6, self.banner, align="R")
        self.set_y(22)
        if self.demo:
            self.set_fill_color(254, 243, 199)
            self.set_text_color(146, 64, 14)
            self.set_font("BVP", "B", 7.5)
            self.cell(0, 5, "DỮ LIỆU KIỂM THỬ – không phải số liệu thị trường thật", fill=True, align="C",
                      new_x="LMARGIN", new_y="NEXT")
            self.ln(1)

    def footer(self):
        self.set_y(-12)
        self.set_font("BVP", "", 7)
        self.color("muted")
        self.cell(0, 5, f"Nguồn: SSI FastConnect V3 (REST + WebSocket) · giờ Việt Nam · {get('app.disclaimer')}",
                  align="L")
        self.cell(0, 5, f"Trang {self.page_no()}", align="R")

    # ── khối ──────────────────────────────────────────────────────────────────
    def h2(self, text: str):
        self.ln(2)
        self.set_font("BVP", "B", 11.5)
        self.color("text")
        self.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        self.color("accent", "draw")
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.l_margin + 18, self.get_y())
        self.ln(2)

    def para(self, text: str, size: float = 9, style: str = ""):
        self.set_font("BVP", style, size)
        self.color("text")
        self.multi_cell(0, 4.6, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def cards(self, items: Sequence[Tuple[str, str, str, Optional[str]]], per_row: int = 4, h: float = 19):
        """items: (nhãn, giá trị, dòng phụ, màu giá trị)"""
        w = (210 - self.l_margin - self.r_margin - (per_row - 1) * 3) / per_row
        for i, (lbl, val, sub, col) in enumerate(items):
            if i % per_row == 0:
                if i:
                    self.set_y(y0 + h + 3)
                y0 = self.get_y()
            x = self.l_margin + (i % per_row) * (w + 3)
            self.color("card", "fill")
            self.color("border", "draw")
            self.set_line_width(0.25)
            self.rect(x, y0, w, h, "DF", round_corners=True, corner_radius=2)
            self.set_xy(x + 3, y0 + 2)
            self.set_font("BVP", "B", 6.5)
            self.color("muted")
            self.cell(w - 6, 3.5, lbl.upper())
            self.set_xy(x + 3, y0 + 6)
            self.set_font("BVP", "B", 12.5)
            self.color(col or "text")
            self.cell(w - 6, 6, val)
            self.set_xy(x + 3, y0 + 13)
            self.set_font("BVP", "", 6.8)
            self.color("muted")
            self.cell(w - 6, 4, sub)
        self.set_y(y0 + h + 4)

    def hbars(self, labels: List[str], values: List[float], unit: str = "", height_each: float = 5.2, width: float = 85,
              x: Optional[float] = None, fmt_fn=None):
        x0 = x if x is not None else self.l_margin
        y = self.get_y()
        mx = max([abs(v) for v in values] + [1e-9])
        mid = x0 + 18 + width / 2
        y0_bars = y
        for lab, v in zip(labels, values):
            self.set_xy(x0, y)
            self.set_font("BVP", "B", 7.5)
            self.color("text")
            self.cell(16, height_each - 1, lab, align="R")
            w = abs(v) / mx * (width / 2 - 20)
            self.color("up" if v >= 0 else "down", "fill")
            self.rect(mid if v >= 0 else mid - w, y + 0.6, w, height_each - 2.2, "F")
            self.set_font("BVP", "", 7)
            txt = fmt_fn(v) if fmt_fn else f"{v:+.1f}{unit}"
            self.set_xy(mid + w + 1 if v >= 0 else mid - w - 19, y)
            self.cell(18, height_each - 1, txt, align="L" if v >= 0 else "R")
            y += height_each
        self.color("muted", "draw")
        self.set_line_width(0.2)
        self.line(mid, y0_bars, mid, y)
        self.set_xy(self.l_margin, y + 1)
        return y

    def bullets(self, items: Sequence[str], size: float = 8.8):
        self.set_font("BVP", "", size)
        self.color("text")
        for t in items:
            if self.get_y() > 272:
                self.add_page()
            x0 = self.l_margin
            self.set_x(x0)
            self.cell(4, 4.6, "•")
            self.set_x(x0 + 4)
            self.multi_cell(0, 4.6, t, new_x="LMARGIN", new_y="NEXT")
            self.ln(0.6)
        self.ln(1)

    def line_chart(self, series: dict, h: float = 52, events: Optional[Sequence[Tuple]] = None,
                   colors: Optional[dict] = None, title: str = ""):
        """series: {tên: pd.Series có index ngày}; đường đầu là chuỗi chính (đậm). events: [(ngày, nhãn)]."""
        import pandas as pd
        x0, w = self.l_margin, 210 - self.l_margin - self.r_margin
        if title:
            self.set_font("BVP", "B", 8)
            self.color("muted")
            self.cell(0, 4.5, title, new_x="LMARGIN", new_y="NEXT")
        y0 = self.get_y()
        allv = pd.concat([s.dropna() for s in series.values()])
        if allv.empty:
            return
        lo, hi = float(allv.min()), float(allv.max())
        pad = (hi - lo) * 0.06 or 1
        lo, hi = lo - pad, hi + pad
        t0, t1 = allv.index.min(), allv.index.max()
        span = max((t1 - t0).days, 1)
        plot_x, plot_w = x0 + 12, w - 12
        X = lambda t: plot_x + (pd.Timestamp(t) - t0).days / span * plot_w  # noqa: E731
        Y = lambda v: y0 + h - (v - lo) / (hi - lo) * h  # noqa: E731
        self.color("border", "draw")
        self.set_line_width(0.15)
        self.set_font("BVP", "", 6.2)
        self.color("muted")
        for k in range(5):
            v = lo + (hi - lo) * k / 4
            self.line(plot_x, Y(v), plot_x + plot_w, Y(v))
            self.set_xy(x0, Y(v) - 1.6)
            self.cell(11, 3.2, f"{v:,.0f}".replace(",", "."), align="R")
        for k in range(6):
            t = t0 + pd.Timedelta(days=span * k / 5)
            self.set_xy(X(t) - 8, y0 + h + 0.6)
            self.cell(16, 3, f"{t:%m/%Y}", align="C")
        if events:
            for t, lab in events:
                t = pd.Timestamp(t)
                if t0 <= t <= t1:
                    self.color("#F59E0B", "draw")
                    self.set_line_width(0.3)
                    self.set_dash_pattern(dash=1, gap=1)
                    self.line(X(t), y0, X(t), y0 + h)
                    self.set_dash_pattern()
                    self.set_xy(X(t) - 6, y0 - 0.5)
                    self.set_font("BVP", "B", 6.2)
                    self.color("#B45309")
                    self.cell(12, 3, lab, align="C")
        palette = colors or {}
        default = ["accent", "#94A3B8", "#F97316", "#8B5CF6"]
        for i, (name, s) in enumerate(series.items()):
            s = s.dropna()
            if len(s) < 2:
                continue
            self.color(palette.get(name, default[i % len(default)]), "draw")
            self.set_line_width(0.55 if i == 0 else 0.3)
            self.polyline([(X(t), Y(float(v))) for t, v in s.items()])
        lx = plot_x + 2
        self.set_font("BVP", "", 6.5)
        for i, name in enumerate(series):
            self.color(palette.get(name, default[i % len(default)]), "fill")
            self.rect(lx, y0 + 1.5, 4, 1.4, "F")
            self.color("text")
            self.set_xy(lx + 5, y0 + 0.4)
            self.cell(self.get_string_width(name) + 2, 3.6, name)
            lx += self.get_string_width(name) + 10
        self.set_line_width(0.2)
        self.set_xy(self.l_margin, y0 + h + 5)

    def table(self, headers: List[str], rows: List[List[str]], widths: List[float], size: float = 7.5,
              aligns: Optional[List[str]] = None):
        aligns = aligns or ["L"] + ["R"] * (len(headers) - 1)
        self.set_font("BVP", "B", size - 0.5)
        self.color("soft", "fill")
        self.color("muted")
        for h, w, a in zip(headers, widths, aligns):
            self.cell(w, 6, h, fill=True, align=a)
        self.ln()
        self.set_font("BVP", "", size)
        self.color("text")
        self.color("border", "draw")
        self.set_line_width(0.2)
        for r in rows:
            if self.get_y() > 275:
                self.add_page()
            for c, w, a in zip(r, widths, aligns):
                self.cell(w, 5.2, str(c), align=a, border="B")
            self.ln()
        self.ln(2)
