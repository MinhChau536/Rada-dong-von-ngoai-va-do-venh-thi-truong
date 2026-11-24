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
DARK = {**COMMON, "dark": True, "sidebar": "#081221", "bg": "#0A1628", "card": "#0F1E33", "border": "#1E3050",
        "text": "#E8EEF6", "muted": "#94A6BD", "accent": "#2DD4BF", "grid": "#1C2D47", "track": "#172A44",
        "soft": "#13243C", "insight_bg": "#2A2414", "insight_border": "#A16207"}
GOLD = {"dark": "#F5B341", "light": "#B7791F"}             # màu nhấn cho chữ đặc biệt (tiêu đề nổi bật, mã CK, mục đang chọn)
SERIF = "'Playfair Display', Georgia, serif"
MONO = "'JetBrains Mono', 'IBM Plex Mono', Consolas, monospace"
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
    G = GOLD["dark" if p["dark"] else "light"]
    TXT, MUT = p["text"], p["muted"]
    CARDBG = ("linear-gradient(180deg,rgba(17,33,56,.94),rgba(12,25,44,.94))" if p["dark"] else "#FFFFFF")
    CBD = "rgba(148,163,184,.14)" if p["dark"] else "#E3E8EF"
    SH = ".35" if p["dark"] else ".06"
    TABBG = "rgba(255,255,255,.04)" if p["dark"] else "#F1F5F9"
    ROW = "rgba(255,255,255,.025)" if p["dark"] else "#F8FAFC"
    NOTEBG = "rgba(56,189,248,.08)" if p["dark"] else "#F0F9FF"
    NOTEBD = "rgba(56,189,248,.25)" if p["dark"] else "#BAE6FD"
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&family=Inter:wght@400;500;600&family=Playfair+Display:wght@600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap&subset=vietnamese');
:root {{ --ffr-bg:{p['bg']}; --ffr-card:{p['card']}; --ffr-border:{p['border']}; --ffr-text:{p['text']};
  --ffr-muted:{p['muted']}; --ffr-accent:{p['accent']}; --ffr-up:{p['up']}; --ffr-down:{p['down']}; --ffr-ref:{p['ref']}; }}
html, body, [data-testid="stAppViewContainer"], .stApp {{ background:{p['bg']} !important; color:{p['text']};
  font-family:{FONT}; }}
[data-testid="stHeader"] {{ background:transparent; }}
/* nút mở lại thanh bên khi đã thu gọn – luôn nổi rõ ở góc trái trên */
[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {{ z-index:1000020 !important;
  visibility:visible !important; opacity:1 !important; display:flex !important; }}
[data-testid="stSidebarCollapsedControl"] button, button[data-testid="stExpandSidebarButton"],
[data-testid="stExpandSidebarButton"] button {{ background:#F5B341 !important; color:#0F1E33 !important;
  border:1px solid #B7791F !important; border-radius:10px !important; width:40px !important; height:40px !important;
  box-shadow:0 4px 14px rgba(0,0,0,.35) !important; opacity:1 !important; visibility:visible !important; }}
[data-testid="stSidebarCollapsedControl"] svg, [data-testid="stExpandSidebarButton"] svg,
[data-testid="stSidebarCollapsedControl"] span, [data-testid="stExpandSidebarButton"] span {{ color:#0F1E33 !important;
  fill:#0F1E33 !important; }}
[data-testid="stSidebarCollapsedControl"] button:hover, button[data-testid="stExpandSidebarButton"]:hover {{
  background:#FFD27A !important; }}
.block-container {{ padding:1.1rem 2.2rem 3rem !important; max-width:100% !important; }}
h1,h2,h3,h4,p,span,div,label {{ font-family:{FONT}; }}
/* ── thanh bên ── */
section[data-testid="stSidebar"] {{ background:linear-gradient(180deg,{p['sidebar']} 0%,#0B1A30 100%) !important;
  width:330px !important; min-width:330px !important; border-right:1px solid rgba(245,179,65,.14); }}
section[data-testid="stSidebar"] * {{ color:{p['sidebar_text']}; }}
/* thanh menu cuộn được bằng chuột, bàn di và kéo thanh cuộn – thanh cuộn luôn hiện */
[data-testid="stSidebarContent"] {{ overflow-y:auto !important; overscroll-behavior:contain;
  -webkit-overflow-scrolling:touch; scrollbar-width:thin; scrollbar-color:rgba(245,179,65,.55) rgba(255,255,255,.06); }}
[data-testid="stSidebarContent"]::-webkit-scrollbar {{ width:9px; }}
[data-testid="stSidebarContent"]::-webkit-scrollbar-track {{ background:rgba(255,255,255,.05); }}
[data-testid="stSidebarContent"]::-webkit-scrollbar-thumb {{ background:rgba(245,179,65,.55); border-radius:8px; }}
[data-testid="stSidebarContent"]::-webkit-scrollbar-thumb:hover {{ background:rgba(245,179,65,.85); }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a {{ border-radius:8px; padding:4px 10px; border-left:3px solid transparent; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {{ background:rgba(20,184,166,.10); }}
section[data-testid="stSidebar"] input {{ background:rgba(255,255,255,.06) !important; color:#E6EDF5 !important;
  border:1px solid rgba(255,255,255,.12) !important; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{ background:rgba(255,255,255,.06) !important;
  border:1px solid rgba(255,255,255,.14) !important; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{ background:#16263D !important; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] * {{ color:#E6EDF5 !important; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] input::placeholder {{ color:#93A4B8 !important; }}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] div:has(> input) {{ background:#16263D !important;
  border:1px solid rgba(255,255,255,.16) !important; border-radius:10px !important; }}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] input {{ background:transparent !important; color:#E6EDF5 !important; }}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] input::placeholder {{ color:#93A4B8 !important; opacity:1; }}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] button {{ background:transparent !important; border:none !important; }}
section[data-testid="stSidebar"] button {{ background:rgba(255,255,255,.06) !important; border:1px solid rgba(255,255,255,.14) !important; }}
section[data-testid="stSidebar"] button p {{ color:#E6EDF5 !important; font-size:13px; white-space:nowrap; }}
section[data-testid="stSidebar"] button {{ padding:4px 8px !important; }}
.ffr-brand {{ display:flex; align-items:center; gap:12px; margin:0 0 16px; padding:12px; border-radius:14px;
  background:linear-gradient(135deg,rgba(20,184,166,.16),rgba(255,255,255,.02)); border:1px solid rgba(255,255,255,.08); }}
.ffr-brand svg {{ flex:0 0 auto; filter:drop-shadow(0 4px 10px rgba(20,184,166,.35)); }}
.ffr-brand b {{ display:block; color:#F8FAFC !important; font-size:15px; font-weight:800; line-height:1.2; letter-spacing:-.2px; white-space:nowrap; }}
.ffr-brand small {{ display:block; color:#94A3B8 !important; font-size:10.5px; font-weight:500; white-space:nowrap; line-height:1.35; }}
.ffr-grp {{ display:flex; align-items:center; gap:8px; margin:16px 0 4px 2px; }}
.ffr-grp span {{ color:#64748B !important; font-size:10.5px; letter-spacing:1.5px; font-weight:800; text-transform:uppercase; white-space:nowrap; }}
.ffr-grp::after {{ content:""; flex:1; height:1px; background:rgba(255,255,255,.08); }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a {{ border-radius:10px; padding:6px 12px !important;
  border-left:3px solid transparent; margin:1px 0; transition:background .15s; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a p {{ color:#CBD5E1 !important; font-size:13.5px; font-weight:500; white-space:nowrap; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a span {{ color:#7F8EA3 !important; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {{ background:rgba(255,255,255,.06) !important; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover p {{ color:#FFFFFF !important; }}
section[data-testid="stSidebar"] .st-key-nav_active [data-testid="stPageLink"] a {{
  background:linear-gradient(90deg,rgba(20,184,166,.26),rgba(20,184,166,.04)) !important; border-left:3px solid #2DD4BF; }}
section[data-testid="stSidebar"] .st-key-nav_active [data-testid="stPageLink"] a p {{ color:#FFFFFF !important; font-weight:700; }}
section[data-testid="stSidebar"] .st-key-nav_active [data-testid="stPageLink"] a span {{ color:#2DD4BF !important; }}
.ffr-sep {{ height:1px; background:rgba(255,255,255,.08); margin:14px 0 10px; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] details {{ background:rgba(255,255,255,.03) !important;
  border:1px solid rgba(255,255,255,.08) !important; border-radius:12px !important; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary p {{ color:#E2E8F0 !important; font-weight:600; }}
.ffr-srcbox {{ background:rgba(255,255,255,.03); border:1px solid rgba(255,255,255,.08); border-radius:12px;
  padding:10px 12px; font-size:12px; margin-top:12px; }}
.ffr-srct {{ color:#64748B !important; font-size:10.5px; letter-spacing:1.3px; font-weight:800; text-transform:uppercase; margin-bottom:6px; }}
.ffr-srcr {{ display:flex; align-items:center; padding:3px 0; color:#CBD5E1 !important; }}
.ffr-srcr em {{ margin-left:auto; font-style:normal; color:#F1F5F9 !important; font-weight:600; font-variant-numeric:tabular-nums; }}
.ffr-disc {{ border:1px solid rgba(251,191,36,.35); background:linear-gradient(135deg,rgba(251,191,36,.14),rgba(251,191,36,.04));
  border-radius:12px; padding:10px 12px; font-size:12px; margin-top:10px; line-height:1.5; color:#FDE68A !important; }}
.ffr-disc-t {{ font-weight:800; color:#FBBF24 !important; font-size:12.5px; margin-bottom:2px; }}
.ffr-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:8px; box-shadow:0 0 0 3px rgba(255,255,255,.04); }}
.ffr-acad {{ display:flex; align-items:center; gap:10px; background:{'#2A2414' if p['dark'] else '#FFFBEB'}; border:1px solid {'#A16207' if p['dark'] else '#FCD34D'}; border-radius:10px;
  padding:7px 14px; margin:0 0 10px; font-size:12.5px; color:{'#FDE68A' if p['dark'] else '#92400E'}; }}
.ffr-acad b {{ color:{'#FBBF24' if p['dark'] else '#B45309'}; }}
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
.ffr-chip {{ display:inline-block; padding:2px 8px; border-radius:6px; font-size:11.5px; font-weight:700; white-space:nowrap; }}
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
table.ffr-t {{ width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric:tabular-nums; }}
table.ffr-t th {{ text-align:right; font-size:11px; text-transform:uppercase; letter-spacing:.4px; color:{p['muted']};
  font-weight:700; padding:7px 8px; border-bottom:1px solid {p['border']}; white-space:normal; vertical-align:bottom; }}
table.ffr-t td {{ white-space:nowrap; text-align:right; padding:6px 8px; border-bottom:1px solid {p['track']}; color:{p['text']}; }}
table.ffr-t th.l, table.ffr-t td.l {{ text-align:left; }}
table.ffr-t td.l {{ white-space:normal; }}
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
/* ── trang Toàn cảnh thị trường: lưới thẻ tiêu đề + thanh tab (phong cách cổng thông tin chứng khoán) ── */
div[class*="st-key-tcw"] {{ background:{p['card']}; border:1px solid {p['border']} !important; border-radius:10px !important;
  box-shadow:0 1px 3px rgba(15,23,42,.06); padding:10px 12px 14px !important; overflow:hidden; }}
.tc-head {{ background:linear-gradient(90deg,{'#16263D' if p['dark'] else '#E8EEFB'},{p['card']}); border-radius:12px;
  padding:14px 20px; border:1px solid {p['border']}; }}
.tc-h1 {{ font-size:28px; font-weight:800; color:{'#F87171' if p['dark'] else '#B42318'}; letter-spacing:-.3px; line-height:1.1; }}
.tc-date {{ font-size:14px; color:{p['muted']}; margin-top:4px; }}
.tc-title {{ text-align:center; font-size:18px; font-weight:700; color:{'#F87171' if p['dark'] else '#B42318'}; padding:2px 0 0; }}
.tc-sub {{ text-align:center; font-size:11.5px; color:{p['muted']}; margin-top:-2px; }}
div[class*="st-key-tcw"] .stTabs [role="tablist"] {{ gap:0; border-bottom:2px solid #1E3A5F; }}
div[class*="st-key-tcw"] .stTabs [data-testid="stTab"] {{ flex:1 1 0; min-width:0; justify-content:center; padding:6px 3px;
  margin:0; background:{p['soft']}; border-radius:0; height:auto; }}
div[class*="st-key-tcw"] .stTabs [data-testid="stTab"] p {{ font-size:12.5px; font-weight:600; color:{p['text']};
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
div[class*="st-key-tcw"] .stTabs .react-aria-SelectionIndicator {{ display:none; }}
div[class*="st-key-tcw"] .stTabs [aria-selected="true"] {{ background:#1E3A5F !important; }}
div[class*="st-key-tcw"] .stTabs [aria-selected="true"] p {{ color:#FFFFFF !important; }}
div[class*="st-key-tcw"] .stTabs [data-baseweb="tab-highlight"], div[class*="st-key-tcw"] .stTabs [data-baseweb="tab-border"] {{ display:none; }}
.tc-tw {{ width:100%; overflow-x:auto; }}
table.tc-t {{ width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric:tabular-nums; }}
table.tc-t th {{ font-size:11.5px; font-weight:700; color:{p['text']}; padding:6px 6px; text-align:right;
  border-bottom:1px solid {p['border']}; white-space:normal; vertical-align:bottom; }}
table.tc-t td {{ padding:6px 5px; text-align:right; border-bottom:1px solid {p['track']}; white-space:nowrap; color:{p['text']}; }}
table.tc-t tbody tr:nth-child(odd) td {{ background:{p['soft']}; }}
table.tc-t th.l, table.tc-t td.l {{ text-align:left; }}
table.tc-t td:first-child {{ color:{p['muted']}; }}
.tc-sym {{ color:{'#93C5FD' if p['dark'] else '#1E3A5F'}; font-weight:700; }}
.tc-row {{ display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; font-size:12.5px; color:{p['muted']}; margin-top:6px; }}
.tc-row b {{ color:{p['text']}; }}
.tc-breadth {{ display:flex; height:16px; border-radius:4px; overflow:hidden; margin-top:6px; }}
.tc-breadth i {{ display:flex; align-items:center; justify-content:center; color:#fff; font-size:10.5px; font-style:normal; font-weight:700; }}
.tc-note {{ font-size:11px; color:{p['muted']}; margin-top:6px; font-style:italic; }}

/* ══ Lớp giao diện "pro" (navy + gold, serif + mono) – chỉ trình bày, không đổi nội dung ══ */
:root {{ --ffr-gold:{G}; --ffr-serif:{SERIF}; --ffr-mono:{MONO}; }}
.ffr-gold, b.ffr-gold {{ color:{G} !important; }}
/* thanh bên */
.ffr-brand {{ background:linear-gradient(135deg,rgba(245,179,65,.14),rgba(255,255,255,.02)) !important;
  border:1px solid rgba(245,179,65,.28) !important; }}
.ffr-brand b {{ font-family:{SERIF}; font-size:18px !important; letter-spacing:.2px; }}
.ffr-grp span {{ font-family:{MONO}; color:#C9A253 !important; font-size:10.5px !important; letter-spacing:1.8px !important; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a {{ padding:9px 14px !important; border:1px solid transparent;
  border-left:3px solid transparent; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a p {{ text-transform:uppercase; letter-spacing:.6px; font-size:12.8px !important;
  font-weight:600 !important; }}
section[data-testid="stSidebar"] .st-key-nav_active [data-testid="stPageLink"] a {{
  background:linear-gradient(90deg,rgba(245,179,65,.22),rgba(245,179,65,.05)) !important; border:1px solid rgba(245,179,65,.65) !important;
  border-left:3px solid #F5B341 !important; box-shadow:0 0 0 3px rgba(245,179,65,.06), 0 6px 18px rgba(0,0,0,.25); }}
section[data-testid="stSidebar"] .st-key-nav_active [data-testid="stPageLink"] a p,
section[data-testid="stSidebar"] .st-key-nav_active [data-testid="stPageLink"] a span {{ color:#F5B341 !important; }}
.ffr-srct {{ font-family:{MONO}; color:#C9A253 !important; }}
/* tiêu đề, nhãn */
.ffr-sec h3, .ffr-title {{ font-family:{FONT}; font-weight:700 !important; letter-spacing:-.2px; }}
.ffr-lbl, .ffr-kpi small {{ font-family:{FONT}; letter-spacing:.6px !important; font-weight:700 !important; }}
table.ffr-t th, table.tc-t th {{ font-family:{FONT}; letter-spacing:.3px !important; font-size:12px !important; font-weight:700 !important; }}
.ffr-kpi {{ border-radius:14px !important; position:relative; overflow:hidden; }}
.ffr-kpi::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:linear-gradient(180deg,{G},transparent); }}
.ffr-kpi b {{ font-size:22px !important; }}
.ffr-sym, .tc-sym {{ color:{G} !important; font-weight:700 !important; }}
.ffr-card {{ border-radius:14px !important; }}
/* thẻ widget */
div[class*="st-key-tcw"] {{ border-radius:16px !important; border:1px solid {CBD} !important;
  background:{CARDBG} !important; box-shadow:0 10px 30px rgba(2,8,23,{SH}); padding:14px 16px 16px !important; }}
.tc-title {{ text-align:left !important; font-family:{FONT}; font-size:18px !important; font-weight:700 !important;
  color:{TXT} !important; letter-spacing:.1px; padding:2px 0 0 !important; }}
.tc-title::before {{ content:""; display:inline-block; width:8px; height:8px; border-radius:50%; background:{G};
  margin:0 10px 3px 0; box-shadow:0 0 0 4px rgba(245,179,65,.18); }}
.tc-sub {{ text-align:left !important; font-size:12.5px !important; color:{MUT} !important; margin:2px 0 8px 18px !important; }}
/* tab trong thẻ: dạng nút chọn, mục đang chọn tô vàng */
div[class*="st-key-tcw"] .stTabs [role="tablist"] {{ border-bottom:none !important; background:{TABBG}; border-radius:10px;
  padding:3px; gap:3px !important; }}
div[class*="st-key-tcw"] .stTabs [data-testid="stTab"] {{ background:transparent !important; border-radius:8px !important; padding:6px 4px !important; }}
div[class*="st-key-tcw"] .stTabs [data-testid="stTab"] p {{ font-family:{FONT}; font-size:13px !important; font-weight:600 !important;
  color:{MUT} !important; }}
div[class*="st-key-tcw"] .stTabs [aria-selected="true"] {{ background:{G} !important; }}
div[class*="st-key-tcw"] .stTabs [aria-selected="true"] p {{ color:#1A1206 !important; font-weight:700 !important; }}
/* bảng */
table.tc-t tbody tr:nth-child(odd) td {{ background:{ROW} !important; }}
table.tc-t tbody tr:hover td, table.ffr-t tr:hover td {{ background:rgba(245,179,65,.07) !important; }}
/* hộp nhắc */
.ffr-acad {{ border-radius:12px !important; border-left:3px solid {G} !important; }}
.ffr-note {{ display:flex; align-items:center; gap:10px; border-radius:12px; padding:7px 14px; margin:0 0 10px; font-size:12.5px;
  background:{NOTEBG}; border:1px solid {NOTEBD}; border-left:3px solid #38BDF8; color:{TXT}; }}
.ffr-note b {{ color:#38BDF8; }}
.ffr-insight {{ border-left:3px solid {G} !important; border-radius:12px !important; }}
.ffr-pill {{ font-size:12px !important; }}
</style>"""
