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
from src.common.logo import png_path

FONT_DIR = ROOT / "assets" / "fonts"
ACADEMIC = ("ĐỀ TÀI NGHIÊN CỨU HỌC THUẬT – KHÔNG MANG TÍNH CHẤT KHUYẾN NGHỊ ĐẦU TƯ · số liệu và nhận định chỉ phục vụ "
            "mục đích học tập, nghiên cứu")
ACADEMIC_SHORT = "Đề tài nghiên cứu học thuật – không mang tính chất khuyến nghị đầu tư"


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
        self.on_cover = False
        self.chapter_no = 0

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
        if self.on_cover:
            return
        self.color("sidebar", "fill")
        self.rect(0, 0, 210, 18, "F")
        self.image(str(png_path()), x=14, y=4, w=10, h=10)
        self.set_xy(27, 4)
        self.set_font("BVP", "B", 11)
        self.set_text_color(255, 255, 255)
        self.cell(100, 6, f"{get('app.name')} · {self.doc_title}")
        self.set_xy(27, 10)
        self.set_font("BVP", "", 7.5)
        self.set_text_color(199, 210, 224)
        self.cell(120, 4, self.doc_sub)
        self.set_xy(120, 6)
        self.set_font("BVP", "B", 7.5)
        self.set_text_color(253, 230, 138)
        self.cell(76, 6, self.banner, align="R")
        # Dải khuyến cáo học thuật – có trên MỌI trang nội dung
        self.set_fill_color(254, 243, 199)
        self.rect(0, 18, 210, 4.6, "F")
        self.set_xy(14, 18.3)
        self.set_font("BVP", "B", 6.8)
        self.set_text_color(146, 64, 14)
        self.cell(182, 4, ACADEMIC, align="C")
        self.set_y(26)
        if self.demo:
            self.set_fill_color(254, 243, 199)
            self.set_text_color(146, 64, 14)
            self.set_font("BVP", "B", 7.5)
            self.cell(0, 5, "DỮ LIỆU KIỂM THỬ – không phải số liệu thị trường thật", fill=True, align="C",
                      new_x="LMARGIN", new_y="NEXT")
            self.ln(1)

    def footer(self):
        if self.on_cover:
            return
        self.set_y(-12.5)
        self.color("border", "draw")
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), 210 - self.r_margin, self.get_y())
        self.ln(0.8)
        self.set_font("BVP", "B", 6.8)
        self.set_text_color(180, 83, 9)
        self.cell(0, 4, ACADEMIC_SHORT, align="L")
        self.set_x(self.l_margin)
        self.set_font("BVP", "", 6.8)
        self.color("muted")
        self.cell(0, 4, f"Nguồn: SSI FastConnect V3 · giờ Việt Nam   |   Trang {self.page_no()}", align="R")

    # ── khối ──────────────────────────────────────────────────────────────────
    def h2(self, text: str, keep: float = 32):
        self.ensure(keep)
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
        row_h = 5.2
        total = 6 + row_h * len(rows)
        if total <= self.room(full=True) and total > self.room():
            self.add_page()                     # cả bảng vừa một trang → không tách lẻ vài dòng sang trang sau
        elif self.room() < 6 + row_h * 3:
            self.add_page()
        x0 = self.get_x()

        def head():
            self.set_x(x0)
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

        head()
        for r in rows:
            if self.get_y() + row_h > self.page_break_trigger:
                self.add_page()
                head()                          # lặp lại tiêu đề cột khi bảng sang trang
            self.set_x(x0)
            for i, (c, w, a) in enumerate(zip(r, widths, aligns)):
                txt = str(c)
                if txt[:1] in "+-" and len(txt) > 1 and txt[1:2].isdigit() and i > 0:
                    self.color("up" if txt[0] == "+" else "down")
                else:
                    self.color("text")
                self.cell(w, row_h, txt, align=a, border="B")
            self.ln()
        self.color("text")
        self.ln(2)

    # ── bố cục: không để khoảng trống lớn ────────────────────────────────────
    def room(self, full: bool = False) -> float:
        """Chiều cao còn lại (mm) trên trang hiện tại; full=True: chiều cao vùng nội dung của một trang mới."""
        return self.page_break_trigger - (26 if full else self.get_y())

    def ensure(self, h: float) -> None:
        if self.room() < h:
            self.add_page()

    @staticmethod
    def _img_ratio(buf) -> float:
        from PIL import Image
        buf.seek(0)
        with Image.open(buf) as im:
            w, h = im.size
        buf.seek(0)
        return h / w

    def figure(self, buf, w: Optional[float] = None, caption: str = "") -> None:
        """Chèn ảnh PNG toàn chiều rộng; tự sang trang nếu không đủ chỗ."""
        w = w or (210 - self.l_margin - self.r_margin)
        h = w * self._img_ratio(buf)
        self.ensure(h + (5 if caption else 1))
        y = self.get_y()
        self.image(buf, x=self.l_margin + (210 - self.l_margin - self.r_margin - w) / 2, y=y, w=w)
        self.set_y(y + h + 0.5)
        if caption:
            self.set_font("BVP", "I", 6.8)
            self.color("muted")
            self.multi_cell(0, 3.4, caption, new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def figures_row(self, bufs: Sequence, captions: Optional[Sequence[str]] = None, gap: float = 4) -> None:
        """Hai (hoặc nhiều) ảnh cạnh nhau, cùng chiều rộng, căn đỉnh."""
        n = len(bufs)
        w = (210 - self.l_margin - self.r_margin - gap * (n - 1)) / n
        hs = [w * self._img_ratio(b) for b in bufs]
        h = max(hs)
        self.ensure(h + (6 if captions else 1))
        y = self.get_y()
        for i, b in enumerate(bufs):
            self.image(b, x=self.l_margin + i * (w + gap), y=y, w=w)
        yy = y + h + 0.5
        if captions:
            self.set_font("BVP", "I", 6.8)
            self.color("muted")
            for i, c in enumerate(captions):
                self.set_xy(self.l_margin + i * (w + gap), yy)
                self.multi_cell(w, 3.4, c)
            yy += 7
        self.set_xy(self.l_margin, yy)
        self.ln(1.5)

    def callout(self, title: str, items: Sequence[str], size: float = 8.4) -> None:
        """Hộp nền nhạt, viền trái màu nhấn – dùng cho 'Số liệu đáng chú ý'."""
        w = 210 - self.l_margin - self.r_margin
        self.set_font("BVP", "", size)
        lines = sum(len(self.multi_cell(w - 12, 4.4, t, dry_run=True, output="LINES")) for t in items)
        h = 9 + lines * 4.4 + len(items) * 0.8 + 2
        self.ensure(h)
        x, y = self.l_margin, self.get_y()
        self.set_fill_color(240, 253, 250)
        self.rect(x, y, w, h, "F")
        self.color("accent", "fill")
        self.rect(x, y, 1.4, h, "F")
        self.set_xy(x + 5, y + 2.5)
        self.set_font("BVP", "B", 9)
        self.color("accent")
        self.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")
        self.set_font("BVP", "", size)
        self.color("text")
        for t in items:
            self.set_x(x + 5)
            self.cell(3.5, 4.4, "•")
            self.set_x(x + 9)
            self.multi_cell(w - 12, 4.4, t, new_x="LMARGIN", new_y="NEXT")
            self.ln(0.8)
        self.set_y(y + h + 3)

    # ── chương có đánh số + mục lục ──────────────────────────────────────────
    def h1(self, title: str, lead: str = "", keep: float = 95) -> None:
        """Tiêu đề chương: tự đánh số, ghi vào mục lục (fpdf2 start_section). keep: chỗ trống tối thiểu để tiêu đề
        không nằm lẻ cuối trang tách khỏi nội dung đầu chương."""
        self.ensure(keep)
        self.chapter_no += 1
        label = f"{self.chapter_no}. {title}"
        self.start_section(label, level=0)
        y = self.get_y() + 1
        self.color("accent", "fill")
        self.rect(self.l_margin, y, 9, 9, "F")
        self.set_xy(self.l_margin, y + 1)
        self.set_font("BVP", "B", 10.5)
        self.set_text_color(255, 255, 255)
        self.cell(9, 7, str(self.chapter_no), align="C")
        self.set_xy(self.l_margin + 12, y + 0.6)
        self.set_font("BVP", "B", 14)
        self.color("text")
        self.cell(0, 8, title.upper(), new_x="LMARGIN", new_y="NEXT")
        self.color("border", "draw")
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y() + 1.5, 210 - self.r_margin, self.get_y() + 1.5)
        self.ln(3.5)
        if lead:
            self.set_font("BVP", "I", 8.6)
            self.color("muted")
            self.multi_cell(0, 4.4, lead, new_x="LMARGIN", new_y="NEXT")
            self.ln(1.5)

    def cover(self, kind: str, date_text: str, stamp: str, cards: Sequence[Tuple[str, str, str, Optional[str]]],
              contents: Sequence[str], note: str) -> None:
        """Trang bìa: nền xanh đậm, tên báo cáo, phiên, 4 chỉ số chính, danh sách nội dung."""
        self.on_cover = True
        self.add_page()
        self.color("sidebar", "fill")
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(15, 118, 110)
        self.rect(0, 0, 210, 4, "F")
        for i, (cx, cy, r) in enumerate(((180, 40, 70), (195, 80, 40), (30, 270, 55))):
            self.set_draw_color(30, 58, 90)
            self.set_line_width(0.4)
            self.circle(cx, cy, r, style="D")
        self.image(str(png_path()), x=20, y=27, w=15, h=15)
        self.set_xy(38, 28.5)
        self.set_text_color(255, 255, 255)
        self.set_font("BVP", "B", 12)
        self.cell(0, 6, get("app.name"))
        self.set_xy(38, 35)
        self.set_font("BVP", "", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 5, "RADAR DÒNG VỐN NGOẠI & ĐỘ VÊNH THỊ TRƯỜNG · GIAI ĐOẠN NÂNG HẠNG FTSE")
        self.set_xy(20, 78)
        self.set_font("BVP", "B", 11)
        self.set_text_color(45, 212, 191)
        self.cell(0, 6, "BÁO CÁO THỊ TRƯỜNG CHỨNG KHOÁN VIỆT NAM")
        self.set_xy(20, 87)
        self.set_font("BVP", "B", 34)
        self.set_text_color(255, 255, 255)
        self.cell(0, 15, kind.upper())
        self.set_xy(20, 104)
        self.set_font("BVP", "", 15)
        self.set_text_color(226, 232, 240)
        self.cell(0, 8, date_text)
        self.set_xy(20, 114)
        self.set_font("BVP", "B", 8.5)
        self.set_text_color(253, 230, 138)
        self.cell(0, 5, self.banner)
        self.set_xy(20, 120)
        self.set_font("BVP", "", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 5, stamp)
        # 4 chỉ số
        y, w = 140, (170 - 3 * 4) / 4
        for i, (lbl, val, sub, col) in enumerate(cards[:4]):
            x = 20 + i * (w + 4)
            self.set_fill_color(23, 42, 66)
            self.rect(x, y, w, 26, "F", round_corners=True, corner_radius=2)
            self.set_xy(x + 3, y + 3)
            self.set_font("BVP", "B", 6.8)
            self.set_text_color(148, 163, 184)
            self.cell(w - 6, 4, lbl.upper())
            self.set_xy(x + 3, y + 8.5)
            self.set_font("BVP", "B", 14)
            self.set_text_color(255, 255, 255)
            self.cell(w - 6, 7, val)
            self.set_xy(x + 3, y + 17)
            self.set_font("BVP", "B", 7.5)
            rgb = {"up": (74, 222, 128), "down": (248, 113, 113)}.get(col or "", (251, 191, 36))
            self.set_text_color(*rgb)
            self.cell(w - 6, 5, sub)
        # nội dung chính
        self.set_xy(20, 180)
        self.set_font("BVP", "B", 9)
        self.set_text_color(45, 212, 191)
        self.cell(0, 6, "NỘI DUNG CHÍNH", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(45, 212, 191)
        self.set_line_width(0.4)
        self.line(20, self.get_y(), 40, self.get_y())
        self.ln(2.5)
        half = (len(contents) + 1) // 2
        y0 = self.get_y()
        for i, t in enumerate(contents):
            col, row = divmod(i, half)
            self.set_xy(20 + col * 86, y0 + row * 7)
            self.set_font("BVP", "B", 9)
            self.set_text_color(45, 212, 191)
            self.cell(8, 6, f"{i + 1:02d}")
            self.set_font("BVP", "", 9)
            self.set_text_color(226, 232, 240)
            self.cell(76, 6, t)
        self.set_fill_color(251, 191, 36)
        self.rect(20, 252, 170, 11, "F", round_corners=True, corner_radius=2)
        self.set_xy(20, 254.5)
        self.set_font("BVP", "B", 8.6)
        self.set_text_color(69, 26, 3)
        self.cell(170, 6, ACADEMIC_SHORT.upper(), align="C")
        self.set_xy(20, 268)
        self.set_font("BVP", "I", 7)
        self.set_text_color(148, 163, 184)
        self.multi_cell(170, 3.6, note)
        self.on_cover = False

    def toc_page(self, info_rows: Sequence[Tuple[str, str]]) -> None:
        """Trang mục lục (số trang điền sau khi dựng xong toàn bộ) + khối 'Thông tin báo cáo'."""
        self.add_page()

        def render(pdf: "FFRPdf", outline) -> None:
            pdf.set_y(29)
            pdf.set_font("BVP", "B", 18)
            pdf.color("text")
            pdf.cell(0, 10, "MỤC LỤC", new_x="LMARGIN", new_y="NEXT")
            pdf.color("accent", "draw")
            pdf.set_line_width(0.8)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 22, pdf.get_y())
            pdf.ln(6)
            for sec in outline:
                if sec.level > 0:
                    continue
                link = pdf.add_link(page=sec.page_number)
                no, _, name = sec.name.partition(". ")
                y = pdf.get_y()
                pdf.color("accent", "fill")
                pdf.rect(pdf.l_margin, y + 1, 7, 7, "F")
                pdf.set_xy(pdf.l_margin, y + 1.4)
                pdf.set_font("BVP", "B", 8.5)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(7, 6, no, align="C")
                pdf.set_xy(pdf.l_margin + 11, y + 1.2)
                pdf.set_font("BVP", "B", 10)
                pdf.color("text")
                tw = pdf.get_string_width(name)
                pdf.cell(tw + 2, 6.5, name, link=link)
                pdf.color("border", "draw")
                pdf.set_line_width(0.2)
                pdf.set_dash_pattern(dash=0.6, gap=1.2)
                pdf.line(pdf.l_margin + 14 + tw, y + 6, 210 - pdf.r_margin - 12, y + 6)
                pdf.set_dash_pattern()
                pdf.set_xy(210 - pdf.r_margin - 12, y + 1.2)
                pdf.color("accent")
                pdf.cell(12, 6.5, str(sec.page_number), align="R", link=link)
                pdf.set_y(y + 10)
            pdf.ln(6)
            pdf.set_font("BVP", "B", 10)
            pdf.color("text")
            pdf.cell(0, 7, "THÔNG TIN BÁO CÁO", new_x="LMARGIN", new_y="NEXT")
            pdf.color("accent", "draw")
            pdf.set_line_width(0.5)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 18, pdf.get_y())
            pdf.ln(2.5)
            for k, v in info_rows:
                y = pdf.get_y()
                pdf.set_font("BVP", "B", 8)
                pdf.color("muted")
                pdf.set_xy(pdf.l_margin, y)
                pdf.multi_cell(42, 4.4, k)
                pdf.set_font("BVP", "", 8)
                pdf.color("text")
                pdf.set_xy(pdf.l_margin + 44, y)
                pdf.multi_cell(0, 4.4, v, new_x="LMARGIN", new_y="NEXT")
                pdf.color("border", "draw")
                pdf.set_line_width(0.15)
                pdf.line(pdf.l_margin, pdf.get_y() + 1, 210 - pdf.r_margin, pdf.get_y() + 1)
                pdf.ln(2.2)

        self.insert_toc_placeholder(render, pages=1)
