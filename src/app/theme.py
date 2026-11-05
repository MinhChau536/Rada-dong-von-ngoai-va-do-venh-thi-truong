"""
Hệ màu – nguồn màu DUY NHẤT cho CSS Streamlit, Plotly template 'ffr' và báo cáo PDF (bước B4.1, mục 11.2).
Thay cho hàm _pal() rải rác của bản giữa kỳ.
"""
from __future__ import annotations

from typing import Dict

import plotly.graph_objects as go
import plotly.io as pio

COMMON = {
    "up": "#16A34A", "down": "#DC2626", "ref": "#D97706", "ceiling": "#A21CAF", "floor": "#0891B2",
    "teal": "#14B8A6", "ma20": "#F59E0B", "ma50": "#4F46E5",
    "sidebar": "#0F1E33", "sidebar_text": "#C7D2E0", "sidebar_label": "#7F8EA3",
    "warn_bg": "#FFF7E6", "warn_border": "#F59E0B",
}
LIGHT = {**COMMON, "dark": False, "bg": "#F4F6F9", "card": "#FFFFFF", "border": "#E3E8EF", "text": "#0F172A",
         "muted": "#5B6B7F", "accent": "#0F766E", "grid": "#E3E8EF", "track": "#EEF2F6", "soft": "#F8FAFC",
         "insight_bg": "#FFFBEB", "insight_border": "#FCD34D"}
DARK = {**COMMON, "dark": True, "sidebar": "#0A1424", "bg": "#0B1320", "card": "#111C2E", "border": "#1F2A3D",
        "text": "#E6EDF5", "muted": "#93A4B8", "accent": "#2DD4BF", "grid": "#1F2A3D", "track": "#18243A",
        "soft": "#14213A", "insight_bg": "#2A2414", "insight_border": "#A16207"}
ABSORB_COLORS = {"absorb": "#16A34A", "joint_sell": "#DC2626", "joint_buy": "#2563EB",
                 "domestic_take": "#D97706", "neutral": "#94A3B8"}
SESSION_COLORS = {"broad_up": "#16A34A", "narrow_up": "#84CC16", "flat": "#94A3B8",
                  "narrow_down": "#F97316", "broad_down": "#DC2626"}
FONT = "Be Vietnam Pro, Inter, system-ui, sans-serif"


def palette(mode: str = "light") -> Dict:
    return DARK if mode == "dark" else LIGHT


def color_for(v, p: Dict) -> str:
    try:
        if v is None or v != v:
            return p["muted"]
    except Exception:
        return p["muted"]
    return p["up"] if v > 1e-9 else p["down"] if v < -1e-9 else p["ref"]


def register_plotly(mode: str = "light") -> str:
    p = palette(mode)
    name = f"ffr_{mode}"
    tpl = go.layout.Template()
    tpl.layout = go.Layout(
        font=dict(family=FONT, color=p["text"], size=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=[p["accent"], "#4F46E5", "#F59E0B", "#DB2777", "#0891B2", "#65A30D", "#7C3AED"],
        xaxis=dict(gridcolor=p["grid"], zerolinecolor=p["grid"], linecolor=p["border"], automargin=True),
        yaxis=dict(gridcolor=p["grid"], zerolinecolor=p["grid"], linecolor=p["border"], automargin=True),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.08, x=0),
        margin=dict(l=8, r=8, t=30, b=8), hoverlabel=dict(font_family=FONT),
    )
    pio.templates[name] = tpl
    pio.templates["ffr"] = tpl
    return name


def css(mode: str = "light") -> str:
    p = palette(mode)
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&family=Inter:wght@400;500;600&display=swap');
:root {{ --ffr-bg:{p['bg']}; --ffr-card:{p['card']}; --ffr-border:{p['border']}; --ffr-text:{p['text']};
  --ffr-muted:{p['muted']}; --ffr-accent:{p['accent']}; --ffr-up:{p['up']}; --ffr-down:{p['down']}; --ffr-ref:{p['ref']}; }}
html, body, [data-testid="stAppViewContainer"], .stApp {{ background:{p['bg']} !important; color:{p['text']};
  font-family:{FONT}; }}
[data-testid="stHeader"] {{ background:transparent; }}
.block-container {{ padding-top:1.4rem; max-width:1500px; }}
h1,h2,h3,h4,p,span,div,label {{ font-family:{FONT}; }}
/* ── thanh bên ── */
section[data-testid="stSidebar"] {{ background:{p['sidebar']} !important; width:270px !important; }}
section[data-testid="stSidebar"] * {{ color:{p['sidebar_text']}; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a {{ border-radius:8px; padding:4px 10px; border-left:3px solid transparent; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {{ background:rgba(20,184,166,.10); }}
section[data-testid="stSidebar"] input {{ background:rgba(255,255,255,.06) !important; color:#E6EDF5 !important;
  border:1px solid rgba(255,255,255,.12) !important; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{ background:rgba(255,255,255,.06) !important;
  border:1px solid rgba(255,255,255,.14) !important; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] * {{ color:#C7D2E0 !important; }}
section[data-testid="stSidebar"] button {{ background:rgba(255,255,255,.06) !important; border:1px solid rgba(255,255,255,.14) !important; }}
section[data-testid="stSidebar"] button p {{ color:#E6EDF5 !important; }}
.ffr-brand {{ display:flex; align-items:center; gap:10px; margin:2px 0 14px; }}
.ffr-logo {{ width:38px; height:38px; border-radius:10px; background:linear-gradient(135deg,#14B8A6,#0F766E);
  display:flex; align-items:center; justify-content:center; color:#fff !important; font-weight:800; font-size:18px; }}
.ffr-brand b {{ display:block; color:#F1F5F9 !important; font-size:16px; line-height:1.1; }}
.ffr-brand small {{ color:{p['sidebar_label']} !important; font-size:9.5px; letter-spacing:1.6px; font-weight:700; }}
.ffr-grp {{ color:{p['sidebar_label']} !important; font-size:10.5px; letter-spacing:1.4px; font-weight:700;
  text-transform:uppercase; margin:14px 0 2px 4px; }}
.ffr-active {{ background:rgba(20,184,166,.14); border-left:3px solid #14B8A6; border-radius:8px; padding:7px 12px;
  color:#F1F5F9 !important; font-weight:700; font-size:14px; margin:2px 0; }}
.ffr-srcbox {{ background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.08); border-radius:10px;
  padding:10px 12px; font-size:12px; line-height:1.7; margin-top:14px; }}
.ffr-disc {{ border-left:3px solid #F59E0B; background:rgba(245,158,11,.08); border-radius:8px; padding:9px 11px;
  font-size:11.5px; margin-top:10px; line-height:1.5; }}
.ffr-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px; }}
/* ── nội dung ── */
.ffr-head {{ display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap; gap:10px; margin-bottom:10px; }}
.ffr-title {{ font-size:24px; font-weight:800; color:{p['text']}; letter-spacing:-.3px; }}
.ffr-sub {{ font-size:13.5px; color:{p['muted']}; }}
.ffr-pill {{ font-size:12px; font-weight:600; padding:4px 10px; border-radius:999px; border:1px solid {p['border']};
  background:{p['card']}; color:{p['muted']}; display:inline-flex; align-items:center; gap:6px; margin-left:6px; }}
.ffr-card {{ background:{p['card']}; border:1px solid {p['border']}; border-radius:12px; padding:14px 16px;
  box-shadow:0 1px 2px rgba(15,23,42,.04); height:100%; }}
.ffr-lbl {{ font-size:11px; font-weight:700; letter-spacing:.7px; text-transform:uppercase; color:{p['muted']}; }}
.ffr-val {{ font-size:24px; font-weight:800; color:{p['text']}; line-height:1.15; margin-top:4px; font-variant-numeric:tabular-nums; }}
.ffr-chg {{ font-size:13.5px; font-weight:700; font-variant-numeric:tabular-nums; }}
.ffr-meta {{ display:flex; justify-content:space-between; font-size:11.5px; color:{p['muted']}; margin-top:5px;
  font-variant-numeric:tabular-nums; gap:6px; }}
.ffr-sec {{ display:flex; align-items:baseline; gap:10px; margin:24px 0 10px; }}
.ffr-sec h3 {{ font-size:17px; font-weight:800; color:{p['text']}; margin:0; padding:0; }}
.ffr-sec span {{ font-size:12.5px; color:{p['muted']}; }}
.ffr-new {{ font-size:10px; font-weight:800; background:{p['accent']}; color:#fff !important; padding:2px 6px; border-radius:5px; letter-spacing:.5px; }}
.ffr-chip {{ display:inline-block; padding:2px 8px; border-radius:6px; font-size:11.5px; font-weight:700; }}
.ffr-intro {{ background:{p['card']}; border:1px solid {p['border']}; border-left:4px solid {p['accent']}; border-radius:10px;
  padding:9px 14px; font-size:13px; color:{p['muted']}; margin:4px 0 14px; display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; }}
.ffr-intro b {{ color:{p['text']}; }}
.ffr-status {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; font-size:12px; color:{p['muted']}; margin-bottom:6px; }}
.ffr-insight {{ background:{p['insight_bg']}; border:1px solid {p['insight_border']}; border-radius:10px; padding:12px 14px;
  font-size:13px; line-height:1.6; color:{p['text']}; }}
.ffr-bar {{ display:flex; height:13px; border-radius:999px; overflow:hidden; background:{p['track']}; margin:9px 0 6px; }}
.ffr-legend {{ display:flex; justify-content:space-between; font-size:12.5px; font-weight:700; font-variant-numeric:tabular-nums; flex-wrap:wrap; gap:6px; }}
.ffr-kpi {{ background:{p['card']}; border:1px solid {p['border']}; border-radius:12px; padding:10px 13px; height:100%; }}
.ffr-kpi small {{ font-size:11px; color:{p['muted']}; font-weight:700; text-transform:uppercase; letter-spacing:.5px; }}
.ffr-kpi b {{ display:block; font-size:21px; font-weight:800; font-variant-numeric:tabular-nums; }}
table.ffr-t {{ width:100%; border-collapse:collapse; font-size:13px; font-variant-numeric:tabular-nums; }}
table.ffr-t th {{ text-align:right; font-size:11px; text-transform:uppercase; letter-spacing:.4px; color:{p['muted']};
  font-weight:700; padding:7px 8px; border-bottom:1px solid {p['border']}; white-space:nowrap; }}
table.ffr-t td {{ text-align:right; padding:6px 8px; border-bottom:1px solid {p['track']}; color:{p['text']}; }}
table.ffr-t th.l, table.ffr-t td.l {{ text-align:left; }}
table.ffr-t td:first-child {{ white-space:nowrap; }}
table.ffr-t tr:hover td {{ background:{p['soft']}; }}
.ffr-sym {{ font-weight:800; color:{p['accent']}; }}
.ffr-comp {{ display:flex; justify-content:space-between; font-size:12.5px; color:{p['muted']}; margin:7px 0 3px; }}
.ffr-comp b {{ color:{p['text']}; }}
.ffr-track {{ height:6px; border-radius:999px; background:{p['track']}; overflow:hidden; }}
.ffr-track i {{ display:block; height:100%; border-radius:999px; }}
.ffr-foot {{ font-size:12px; color:{p['muted']}; margin-top:22px; padding-top:10px; border-top:1px solid {p['border']};
  display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; }}
.ffr-demo {{ background:#FEF3C7; color:#92400E !important; border:1px solid #F59E0B; }}
.ffr-strip {{ display:flex; gap:10px; overflow-x:auto; padding-bottom:4px; }}
.ffr-strip .ffr-card {{ min-width:215px; flex:1; }}
div[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background:{p['accent']} !important; border-color:{p['accent']} !important; }}
div[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color:#fff !important; }}
div[data-testid="stMetric"] {{ background:{p['card']}; border:1px solid {p['border']}; border-radius:12px; padding:10px 14px; }}
</style>"""
