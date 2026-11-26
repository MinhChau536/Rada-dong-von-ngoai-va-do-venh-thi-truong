"""
Biểu đồ PNG cho báo cáo PDF (matplotlib, không cần trình duyệt/kaleido). Mọi hàm nhận số liệu từ context.build()
và trả io.BytesIO (ảnh PNG) để FFRPdf.figure() chèn vào trang. Font Be Vietnam Pro (assets/fonts) để hiện đúng tiếng Việt.
Biểu đồ chỉ MÔ TẢ số liệu – không vẽ tín hiệu mua/bán.
"""
from __future__ import annotations

import io
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from src.app.theme import LIGHT, SESSION_COLORS  # noqa: E402
from src.common.config import ROOT  # noqa: E402

P = LIGHT
UP, DOWN, REF, ACCENT, MUTED, TEXT, GRID = P["up"], P["down"], P["ref"], P["accent"], P["muted"], P["text"], "#E3E8EF"
NAVY, INDIGO, AMBER, SLATE = "#0F1E33", "#4F46E5", "#F59E0B", "#94A3B8"
SESSION_LBL = {"broad_up": "Tăng lan rộng", "narrow_up": "Tăng thiếu lan tỏa", "flat": "Đi ngang",
               "narrow_down": "Giảm thiếu lan tỏa", "broad_down": "Giảm đồng thuận"}


def _font() -> str:
    fd = ROOT / "assets" / "fonts"
    for f in ("BeVietnamPro-Regular.ttf", "BeVietnamPro-Medium.ttf", "BeVietnamPro-SemiBold.ttf", "BeVietnamPro-Bold.ttf"):
        if (fd / f).exists():
            font_manager.fontManager.addfont(str(fd / f))
    return "Be Vietnam Pro"


plt.rcParams.update({
    "font.family": [_font(), "DejaVu Sans"], "font.size": 8, "axes.titlesize": 9, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.edgecolor": "#CBD5E1", "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "legend.frameon": False, "legend.fontsize": 7.2, "axes.unicode_minus": False,
})


def _vn(v: float, d: int = 0) -> str:
    s = f"{v:,.{d}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _clean(ax, grid_axis: str = "y") -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x" if grid_axis == "x" else "y")
    ax.grid(axis="y" if grid_axis == "x" else "x", visible=False)
    ax.tick_params(length=0, labelsize=7.2)


def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=220, bbox_inches="tight", pad_inches=0.04, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def _datefmt(ax, span_days: int) -> None:
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y" if span_days > 120 else "%d/%m"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))


# ── 1. VN-Index + MA + thanh khoản ───────────────────────────────────────────
def index_chart(vni: pd.Series, tv: pd.Series, events: Optional[Sequence[Tuple]] = None, months: int = 12,
                size=(7.4, 3.3)) -> io.BytesIO:
    end = vni.index.max()
    start = end - pd.Timedelta(days=int(months * 30.5))
    ma20, ma50 = vni.rolling(20).mean(), vni.rolling(50).mean()
    v, t = vni[vni.index >= start], tv[tv.index >= start] / 1e12
    fig, (a1, a2) = plt.subplots(2, 1, figsize=size, sharex=True, gridspec_kw={"height_ratios": [3.2, 1], "hspace": 0.06})
    a1.fill_between(v.index, v, v.min() * 0.985, color=ACCENT, alpha=0.07, lw=0)
    a1.plot(v.index, v, color=ACCENT, lw=1.5, label="VN-Index")
    a1.plot(v.index, ma20[ma20.index >= start], color=AMBER, lw=0.9, label="MA20")
    a1.plot(v.index, ma50[ma50.index >= start], color=INDIGO, lw=0.9, label="MA50")
    a1.set_ylim(v.min() * 0.985, v.max() * 1.015)
    a1.annotate(_vn(v.iloc[-1], 2), (v.index[-1], v.iloc[-1]), xytext=(4, 0), textcoords="offset points",
                fontsize=7.5, color=ACCENT, fontweight="bold", va="center")
    hi_i, lo_i = v.idxmax(), v.idxmin()
    for dt, lab, off in ((hi_i, f"Cao nhất {_vn(v[hi_i])}", 8), (lo_i, f"Thấp nhất {_vn(v[lo_i])}", -11)):
        a1.annotate(lab, (dt, v[dt]), xytext=(0, off), textcoords="offset points", fontsize=6.4, color=MUTED, ha="center")
    if events:
        for dt, lab in events:
            dt = pd.Timestamp(dt)
            if start <= dt <= end:
                for ax in (a1, a2):
                    ax.axvline(dt, color=AMBER, lw=0.8, ls=(0, (3, 2)))
                a1.text(dt, a1.get_ylim()[1], lab, fontsize=6.5, color="#B45309", ha="center", va="bottom", fontweight="bold")
    a1.legend(loc="upper left", ncol=3)
    chg = v.diff().reindex(t.index).fillna(0)
    a2.bar(t.index, t, width=1.0, color=[UP if c >= 0 else DOWN for c in chg], alpha=0.55)
    a2.plot(t.index, t.rolling(20).mean(), color=NAVY, lw=0.8, label="TB 20 phiên")
    a2.set_ylabel("GTGD\n(nghìn tỷ)", fontsize=6.5)
    a2.legend(loc="upper left")
    for ax in (a1, a2):
        _clean(ax)
    _datefmt(a2, (end - start).days)
    return _png(fig)


# ── 2. Độ rộng: thanh 100% hôm nay + lịch sử 20 phiên ────────────────────────
def breadth_today(x: pd.Series, size=(7.4, 0.75)) -> io.BytesIO:
    parts = [("Trần", int(x["n_ceiling"]), P["ceiling"]), ("Tăng", int(x["n_up"] - x["n_ceiling"]), UP),
             ("Đứng", int(x["n_unch"]), REF), ("Giảm", int(x["n_down"] - x["n_floor"]), DOWN),
             ("Sàn", int(x["n_floor"]), P["floor"])]
    tot = sum(p[1] for p in parts) or 1
    fig, ax = plt.subplots(figsize=size)
    left = 0
    for lab, n, c in parts:
        if n <= 0:
            continue
        ax.barh(0, n, left=left, color=c, height=0.55)
        if n / tot > 0.06:
            ax.text(left + n / 2, 0, f"{n}", ha="center", va="center", color="white", fontsize=7.5, fontweight="bold")
        left += n
    ax.set_xlim(0, tot)
    ax.set_yticks([])
    ax.set_xticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(False)
    ax.legend(handles=[Rectangle((0, 0), 1, 1, color=c) for _, n, c in parts],
              labels=[f"{lab} {n}" for lab, n, _ in parts], ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.05),
              fontsize=6.4, handlelength=0.8, columnspacing=0.8)
    return _png(fig)


def breadth_history(hist: pd.DataFrame, n: int = 30, size=(3.7, 2.4)) -> io.BytesIO:
    h = hist.tail(n).copy()
    h["trade_date"] = pd.to_datetime(h["trade_date"])
    tot = (h["n_up"] + h["n_unch"] + h["n_down"]).replace(0, np.nan)
    up, un, dn = h["n_up"] / tot * 100, h["n_unch"] / tot * 100, h["n_down"] / tot * 100
    x = np.arange(len(h))
    fig, ax = plt.subplots(figsize=size)
    ax.bar(x, up, color=UP, width=0.8, label="% mã tăng")
    ax.bar(x, un, bottom=up, color=REF, width=0.8, alpha=0.75, label="% đứng giá")
    ax.bar(x, dn, bottom=up + un, color=DOWN, width=0.8, label="% mã giảm")
    ax.axhline(50, color="white", lw=0.8)
    ax.set_ylim(0, 100)
    ax.set_title(f"Cơ cấu tăng/giảm {len(h)} phiên (HOSE)")
    step = max(len(h) // 6, 1)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([f"{d:%d/%m}" for d in h["trade_date"].iloc[::step]])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3)
    _clean(ax)
    return _png(fig)


# ── 3. Độ vênh D có dải phân vị 10–90 ─────────────────────────────────────────
def divergence_chart(hist: pd.DataFrame, n: int = 120, size=(3.7, 2.4)) -> io.BytesIO:
    h = hist.copy()
    h["trade_date"] = pd.to_datetime(h["trade_date"])
    lo = h["D"].shift(1).rolling(250, min_periods=40).quantile(.1)
    hi = h["D"].shift(1).rolling(250, min_periods=40).quantile(.9)
    h = h.assign(lo=lo, hi=hi).tail(n)
    fig, ax = plt.subplots(figsize=size)
    ax.fill_between(h["trade_date"], h["lo"], h["hi"], color=ACCENT, alpha=0.12, lw=0, label="Dải phân vị 10–90 (250 phiên)")
    ax.plot(h["trade_date"], h["D"], color=ACCENT, lw=0.9, label="D (điểm %)")
    out = h[(h["D"] > h["hi"]) | (h["D"] < h["lo"])]
    ax.scatter(out["trade_date"], out["D"], s=9, color=DOWN, zorder=3, label="Ngoài dải")
    ax.axhline(0, color=MUTED, lw=0.6)
    ax.set_title(f"Độ vênh D = %VN-Index − % cổ phiếu trung vị · {len(h)} phiên")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, fontsize=6.4)
    _clean(ax)
    _datefmt(ax, (h["trade_date"].max() - h["trade_date"].min()).days)
    return _png(fig)


# ── 4. Thanh ngang hai chiều (đóng góp điểm, khối ngoại, ngành) ──────────────
def hbar(labels: List[str], values: List[float], title: str = "", unit: str = "", dec: int = 2,
         size=(3.7, 2.6), total: Optional[Tuple[str, float]] = None, color_by_sign: bool = True) -> io.BytesIO:
    lab, val = list(labels), list(values)
    if total:
        lab.append(total[0])
        val.append(total[1])
    y = np.arange(len(lab))[::-1]
    fig, ax = plt.subplots(figsize=size)
    cols = [UP if v >= 0 else DOWN for v in val] if color_by_sign else [ACCENT] * len(val)
    if total:
        cols[-1] = NAVY
    ax.barh(y, val, color=cols, height=0.66)
    mx = max([abs(v) for v in val] + [1e-9])
    for yi, v in zip(y, val):
        ax.text(v + (mx * 0.02 if v >= 0 else -mx * 0.02), yi, f"{_vn(v, dec) if v < 0 else '+' + _vn(v, dec)}{unit}",
                va="center", ha="left" if v >= 0 else "right", fontsize=6.6, color=TEXT)
    ax.set_yticks(y)
    ax.set_yticklabels(lab, fontsize=7.2)
    ax.axvline(0, color=MUTED, lw=0.6)
    ax.set_xlim(-mx * 1.35 if min(val) < 0 else 0, mx * 1.35 if max(val) > 0 else 0)
    if title:
        ax.set_title(title)
    ax.set_xticks([])
    _clean(ax, "x")
    ax.grid(False)
    return _png(fig)


def sector_compare(sec1: pd.DataFrame, sec20: pd.DataFrame, n: int = 12, size=(7.4, 2.9)) -> io.BytesIO:
    s20 = sec20.set_index("sector")["ret_pct"]
    s1 = sec1.set_index("sector")["ret_pct"]
    order = s20.reindex(s20.abs().sort_values(ascending=False).index).head(n).sort_values(ascending=False)
    x = np.arange(len(order))
    fig, ax = plt.subplots(figsize=size)
    a = ax.bar(x - 0.2, [s1.get(k, np.nan) for k in order.index], width=0.38, color=SLATE, label="1 phiên")
    b = ax.bar(x + 0.2, order.values, width=0.38, color=[UP if v >= 0 else DOWN for v in order.values], label="20 phiên")
    for rects in (a, b):
        for r in rects:
            h = r.get_height()
            if not np.isnan(h):
                ax.text(r.get_x() + r.get_width() / 2, h + (0.15 if h >= 0 else -0.15), _vn(h, 1),
                        ha="center", va="bottom" if h >= 0 else "top", fontsize=5.8, color=TEXT)
    ax.axhline(0, color=MUTED, lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(order.index, rotation=32, ha="right", rotation_mode="anchor", fontsize=6.4)
    ax.set_ylabel("Lợi suất (%)", fontsize=6.8)
    ax.set_title(f"Lợi suất ngành theo vốn hóa – {len(order)} ngành biến động mạnh nhất 20 phiên")
    ax.legend(loc="upper right", ncol=2)
    _clean(ax)
    return _png(fig)


# ── 5. Bản đồ nhiệt (treemap) theo GTGD, màu theo % ─────────────────────────
def _squarify(values: List[float], x: float, y: float, w: float, h: float) -> List[Tuple[float, float, float, float]]:
    """Thuật toán squarified treemap (Bruls et al., 2000) – trả (x, y, w, h) theo thứ tự values (đã sắp giảm dần)."""
    vals = [v for v in values]
    tot = sum(vals)
    if tot <= 0:
        return []
    vals = [v * w * h / tot for v in vals]
    rects: List[Tuple[float, float, float, float]] = []

    def worst(row, side):
        s = sum(row)
        return max(max(side ** 2 * r / s ** 2, s ** 2 / (side ** 2 * r)) for r in row)

    def layout(row, x, y, w, h):
        s = sum(row)
        if w >= h:
            cw = s / h
            yy = y
            for r in row:
                rects.append((x, yy, cw, r / cw))
                yy += r / cw
            return x + cw, y, w - cw, h
        ch = s / w
        xx = x
        for r in row:
            rects.append((xx, y, r / ch, ch))
            xx += r / ch
        return x, y + ch, w, h - ch

    row: List[float] = []
    i = 0
    while i < len(vals):
        side = min(w, h)
        if not row or worst(row + [vals[i]], side) <= worst(row, side):
            row.append(vals[i])
            i += 1
        else:
            x, y, w, h = layout(row, x, y, w, h)
            row = []
    if row:
        layout(row, x, y, w, h)
    return rects


def treemap(stock: pd.DataFrame, n: int = 60, size=(7.4, 3.4)) -> io.BytesIO:
    v = stock[stock["is_valid"]].nlargest(n, "tv").sort_values("tv", ascending=False)
    rects = _squarify(v["tv"].tolist(), 0, 0, 100, 46)
    fig, ax = plt.subplots(figsize=size)
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("rg", [DOWN, "#FCA5A5", "#F3F4F6", "#86EFAC", UP])
    norm = matplotlib.colors.TwoSlopeNorm(vmin=-4, vcenter=0, vmax=4)
    for (x, y, w, h), r in zip(rects, v.itertuples()):
        ret = r.ret * 100
        col = REF if abs(ret) < 0.005 else cmap(norm(max(min(ret, 4), -4)))
        ax.add_patch(Rectangle((x, y), w, h, facecolor=col, edgecolor="white", lw=1.2))
        if w * h > 14:
            fs = 7.5 if w * h > 60 else 6.2
            dark = abs(ret) > 2.2 or abs(ret) < 0.005
            ax.text(x + w / 2, y + h / 2, f"{r.symbol}\n{_vn(ret, 2) if ret < 0 else '+' + _vn(ret, 2)}%",
                    ha="center", va="center", fontsize=fs, color="white" if dark else TEXT, fontweight="bold", linespacing=1.1)
    ax.set_xlim(0, 100)
    ax.set_ylim(46, 0)
    ax.axis("off")
    ax.set_title(f"Bản đồ nhiệt {len(v)} mã giao dịch lớn nhất HOSE – diện tích theo GTGD, màu theo % thay đổi giá")
    return _png(fig)


# ── 6. Khối ngoại: ròng theo phiên + lũy kế ──────────────────────────────────
def foreign_flow(hist: pd.DataFrame, n: int = 40, size=(7.4, 2.5)) -> io.BytesIO:
    h = hist.tail(n).copy()
    h["trade_date"] = pd.to_datetime(h["trade_date"])
    nf = h["NF_total"] / 1e9
    x = np.arange(len(h))
    fig, ax = plt.subplots(figsize=size)
    ax.bar(x, nf.fillna(0), color=[UP if v >= 0 else DOWN for v in nf.fillna(0)], width=0.72, label="Ròng trong phiên")
    miss = nf.isna()
    if miss.any():
        ax.scatter(x[miss.values], [0] * int(miss.sum()), marker="x", color=MUTED, s=14, label="SSI chưa công bố")
    ax2 = ax.twinx()
    ax2.plot(x, nf.fillna(0).cumsum(), color=NAVY, lw=1.2, label="Lũy kế (trục phải)")
    ax2.tick_params(length=0, labelsize=7, colors=MUTED)
    ax2.grid(False)
    for s in ("top", "left", "right"):
        ax2.spines[s].set_visible(False)
    ax.set_ylabel("Tỷ đồng", fontsize=6.8)
    step = max(len(h) // 8, 1)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([f"{d:%d/%m}" for d in h["trade_date"].iloc[::step]])
    ax.axhline(0, color=MUTED, lw=0.6)
    ax.set_title(f"Khối ngoại mua/bán ròng HOSE {len(h)} phiên (tỷ đồng)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3)
    _clean(ax)
    return _png(fig)


# ── 7. Lũy kế nhóm FTSE / đối chứng / VN30 ───────────────────────────────────
def groups_cum(groups: pd.DataFrame, since: pd.Timestamp, events: Optional[Sequence[Tuple]] = None,
               size=(7.4, 2.5)) -> io.BytesIO:
    g = groups[(groups["group_type"] == "universe") & (pd.to_datetime(groups["trade_date"]) >= since)].copy()
    g["trade_date"] = pd.to_datetime(g["trade_date"])
    fig, ax = plt.subplots(figsize=size)
    names = {"FTSE": ("Nhóm FTSE", ACCENT, 1.5), "CONTROL": ("Nhóm đối chứng", AMBER, 1.1), "VN30": ("VN30", INDIGO, 0.9)}
    for k, (lab, c, lw) in names.items():
        s = g[g["group_name"] == k].sort_values("trade_date")
        if s.empty:
            continue
        cum = ((1 + s["ret_eq"].fillna(0)).cumprod() - 1) * 100
        ax.plot(s["trade_date"], cum, color=c, lw=lw, label=f"{lab} ({_vn(cum.iloc[-1], 1)}%)")
    if events:
        for dt, lab in events:
            dt = pd.Timestamp(dt)
            if dt >= since:
                ax.axvline(dt, color=AMBER, lw=0.7, ls=(0, (3, 2)))
                ax.text(dt, ax.get_ylim()[1], lab, fontsize=6.5, color="#B45309", ha="center", va="bottom")
    ax.axhline(0, color=MUTED, lw=0.6)
    ax.set_ylabel("Lợi suất lũy kế (%)", fontsize=6.8)
    ax.set_title(f"Lợi suất đồng trọng số lũy kế từ {since:%d/%m/%Y}")
    ax.legend(loc="lower left", ncol=3)
    _clean(ax)
    _datefmt(ax, (g["trade_date"].max() - since).days if not g.empty else 30)
    return _png(fig)


# ── 8. Biên dao động thống kê (hình nón) ─────────────────────────────────────
def outlook_fan(vni: pd.Series, vr: Dict, back: int = 60, size=(7.4, 2.5)) -> io.BytesIO:
    v = vni.tail(back)
    fig, ax = plt.subplots(figsize=size)
    x0 = len(v) - 1
    ax.plot(np.arange(len(v)), v.values, color=ACCENT, lw=1.4, label="VN-Index")
    last = float(v.iloc[-1])
    hz = sorted(vr)
    if hz:
        H = max(hz)
        sig = vr[hz[0]]["sigma_d"]
        t = np.arange(0, H + 1)
        k = vr[hz[0]]
        for z, a, lab in ((k.get("k90", 1.645), 0.10, "Biên 90%"), (k.get("k68", 1.0), 0.20, "Biên 68%")):
            ax.fill_between(x0 + t, last * np.exp(-z * sig * np.sqrt(t)), last * np.exp(z * sig * np.sqrt(t)),
                            color=ACCENT, alpha=a, lw=0, label=lab)
        for h in hz:
            r = vr[h]
            for k in ("lo90", "hi90"):
                ax.annotate(_vn(r[k]), (x0 + h, r[k]), xytext=(3, 0), textcoords="offset points", fontsize=6.4,
                            color=MUTED, va="center")
            ax.axvline(x0 + h, color=GRID, lw=0.7)
            ax.text(x0 + h, ax.get_ylim()[0], f"+{h} phiên", fontsize=6.4, color=MUTED, ha="center", va="bottom")
    ax.axvline(x0, color=MUTED, lw=0.6, ls=":")
    ax.set_xticks([0, x0])
    ax.set_xticklabels([f"{v.index[0]:%d/%m}", f"{v.index[-1]:%d/%m}"])
    ax.set_title(f"VN-Index {len(v)} phiên gần nhất và biên dao động thống kê (EWMA) cho các phiên tới")
    ax.legend(loc="upper left", ncol=3)
    _clean(ax)
    return _png(fig)


# ── 9. Watchlist: hiệu suất chuẩn hóa ────────────────────────────────────────
def watch_perf(stock_hist: pd.DataFrame, vni: pd.Series, symbols: List[str], n: int = 60, size=(7.4, 2.5)) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=size)
    pal = [ACCENT, INDIGO, AMBER, "#DB2777", "#0891B2", "#65A30D", "#7C3AED", "#EA580C", "#0F172A"]
    dates = vni.index[-n:]
    if len(dates):
        b = vni[vni.index >= dates[0]]
        ax.plot(b.index, (b / b.iloc[0] - 1) * 100, color=SLATE, lw=2.2, alpha=0.7, label="VN-Index")
    h = stock_hist.copy()
    h["trade_date"] = pd.to_datetime(h["trade_date"])
    for i, s in enumerate(symbols[:9]):
        x = h[(h["symbol"] == s) & (h["trade_date"] >= (dates[0] if len(dates) else h["trade_date"].min()))]
        x = x.sort_values("trade_date")
        if len(x) < 2:
            continue
        cum = ((1 + x["ret"].fillna(0)).cumprod() - 1) * 100
        ax.plot(x["trade_date"], cum, color=pal[i % len(pal)], lw=1.1, label=f"{s} ({_vn(cum.iloc[-1], 1)}%)")
    ax.axhline(0, color=MUTED, lw=0.6)
    ax.set_ylabel("Lợi suất lũy kế (%)", fontsize=6.8)
    ax.set_title(f"Hiệu suất lũy kế {n} phiên – danh mục theo dõi so với VN-Index")
    ax.legend(loc="upper left", ncol=5, fontsize=6.4)
    _clean(ax)
    _datefmt(ax, n * 1.45)
    return _png(fig)


# ── 10. Cơ cấu loại phiên (donut) ────────────────────────────────────────────
def session_mix(types: Dict[str, int], n: int, size=(2.3, 2.3)) -> io.BytesIO:
    keys = [k for k in SESSION_LBL if types.get(k)]
    vals = [types[k] for k in keys]
    fig, ax = plt.subplots(figsize=size)
    ax.pie(vals, colors=[SESSION_COLORS[k] for k in keys], startangle=90, counterclock=False,
           wedgeprops=dict(width=0.38, edgecolor="white"))
    ax.text(0, 0, f"{n}\nphiên", ha="center", va="center", fontsize=8.5, fontweight="bold", color=TEXT)
    ax.legend([f"{SESSION_LBL[k]} {types[k]}" for k in keys], loc="upper center", bbox_to_anchor=(0.5, 0.02),
              fontsize=6.2, ncol=1, handlelength=0.8)
    ax.set_title("Loại phiên 20 phiên", loc="center")
    return _png(fig)


# ── 11. Đóng góp có khối ngoại cùng chiều + nhóm FTSE trong ΔVN-Index ───────
def codir_chart(ex: pd.DataFrame, n: int = 60, size=(3.7, 2.4)) -> io.BytesIO:
    e = ex.tail(n)
    x = np.arange(len(e))
    fig, ax = plt.subplots(figsize=size)
    ax.bar(x, e["codir"] * 100, color="#38BDF8", alpha=0.55, width=0.8, label="Phiên")
    ax.plot(x, (e["codir"] * 100).rolling(10).mean(), color=AMBER, lw=1.6, label="TB 10 phiên")
    if "codir_base" in e:
        ax.plot(x, e["codir_base"] * 100, color=MUTED, lw=1.0, ls=":", label="Thường lệ (trung vị 250 phiên)")
    ax.set_ylim(0, 100)
    ax.set_title(f"% biến động VN-Index có khối ngoại ròng ≥ 5% GTGD cùng chiều · {len(e)} phiên")
    step = max(len(e) // 5, 1)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([f"{d:%d/%m}" for d in pd.to_datetime(e["trade_date"]).iloc[::step]])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    _clean(ax)
    return _png(fig)


def ftse_contrib_chart(ex: pd.DataFrame, n: int = 60, size=(3.7, 2.4)) -> io.BytesIO:
    e = ex.tail(n)
    x = np.arange(len(e))
    rest = e["dI"] - e["ftse_C"]
    fig, ax = plt.subplots(figsize=size)
    ax.bar(x - 0.2, e["ftse_C"], color=AMBER, width=0.4, label="27 mã FTSE (điểm)")
    ax.bar(x + 0.2, rest, color=SLATE, width=0.4, label="Các mã còn lại (điểm)")
    ax.axhline(0, color=MUTED, lw=0.6)
    ax.set_title("Điểm đóng góp vào VN-Index: 27 mã FTSE và các mã còn lại")
    step = max(len(e) // 5, 1)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([f"{d:%d/%m}" for d in pd.to_datetime(e["trade_date"]).iloc[::step]])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    _clean(ax)
    return _png(fig)


# ── Chẩn đoán kỹ thuật: giá + MA, RSI(14), MACD ──────────────────────────────
def tech_chart(t: Dict, n: int = 120, size=(7.4, 3.6)) -> io.BytesIO:
    """Ba ô xếp dọc: VN-Index + MA20/50 + hỗ trợ/kháng cự · RSI(14) với vùng 30/70 · MACD và histogram."""
    c = t["close_series"].tail(n)
    rsi = t["rsi_series"].reindex(c.index)
    m = t["macd_df"].reindex(c.index)
    full = t["close_series"]
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=size, sharex=True, gridspec_kw={"height_ratios": [2.2, 1, 1]})
    a1.plot(c.index, c.values, color=NAVY, lw=1.3, label="VN-Index")
    a1.plot(c.index, full.rolling(20).mean().reindex(c.index), color=AMBER, lw=0.9, label="MA20")
    a1.plot(c.index, full.rolling(50).mean().reindex(c.index), color=INDIGO, lw=0.9, label="MA50")
    for lv in t["supports"][:2]:
        a1.axhline(lv, color=UP, lw=0.7, ls="--")
        a1.text(c.index[0], lv, f" hỗ trợ {_vn(lv)}", fontsize=6.2, color=UP, va="bottom")
    for lv in t["resists"][:2]:
        a1.axhline(lv, color=DOWN, lw=0.7, ls="--")
        a1.text(c.index[0], lv, f" kháng cự {_vn(lv)}", fontsize=6.2, color=DOWN, va="bottom")
    a1.set_title(f"Phân tích kỹ thuật VN-Index {len(c)} phiên: xu hướng, RSI(14), MACD(12,26,9)")
    a1.legend(loc="upper right", ncol=3)
    a2.plot(rsi.index, rsi.values, color=INDIGO, lw=1)
    a2.axhspan(70, 100, color=DOWN, alpha=0.07, lw=0)
    a2.axhspan(0, 30, color=UP, alpha=0.07, lw=0)
    for y in (30, 70):
        a2.axhline(y, color=MUTED, lw=0.6, ls=":")
    a2.set_ylim(10, 90)
    a2.set_ylabel("RSI", fontsize=7)
    a3.bar(m.index, m["hist"], color=[UP if v >= 0 else DOWN for v in m["hist"]], width=1.0, alpha=0.6)
    a3.plot(m.index, m["macd"], color=NAVY, lw=0.9, label="MACD")
    a3.plot(m.index, m["signal"], color=AMBER, lw=0.9, label="Tín hiệu")
    a3.axhline(0, color=MUTED, lw=0.5)
    a3.set_ylabel("MACD", fontsize=7)
    a3.legend(loc="upper left", ncol=2)
    for a in (a1, a2, a3):
        _clean(a)
    _datefmt(a3, (c.index[-1] - c.index[0]).days)
    fig.tight_layout(h_pad=0.3)
    return _png(fig)
