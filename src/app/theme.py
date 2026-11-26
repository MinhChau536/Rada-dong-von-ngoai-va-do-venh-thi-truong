"""
Hệ màu – nguồn màu DUY NHẤT cho CSS Streamlit, Plotly template 'ffr' và báo cáo PDF (bước B4.1, mục 11.2).

Giao diện web theo nguyên tắc của taste-skill (design-taste-frontend, cài cục bộ ở .claude/skills/):
  · giao diện 90–95% trung tính, MỘT màu nhấn (xanh ngọc) cho nút chính, liên kết, tab đang chọn, trạng thái;
  · một hệ: một thang khoảng cách (4·8·12·16·24·32·48), một họ bo góc (8/12/16), một kiểu thẻ (nền phẳng + viền mảnh,
    không bóng mờ khi đứng yên), một kiểu đường kẻ;
  · chữ IBM Plex Sans (đủ dấu tiếng Việt), số dạng bảng (tabular), chữ đọc ≥ 14px ở màu mực, xám chỉ cho nhãn;
  · nhấn bằng độ tương phản chứ không bằng dải màu / chữ chuyển màu; không tím;
  · chuyển động nhẹ: nút nhích 1px khi rê, lún khi bấm (150/120/90ms), tắt hết khi người dùng chọn giảm chuyển động.
Báo cáo PDF vẫn đọc LIGHT (không đổi) – web dùng WEB_LIGHT / WEB_DARK.
"""
from __future__ import annotations

from typing import Dict

import plotly.graph_objects as go
import plotly.io as pio

COMMON = {
    "up": "#16A34A", "down": "#DC2626", "ref": "#D97706", "ceiling": "#A21CAF", "floor": "#0891B2",
    "teal": "#14B8A6", "ma20": "#F59E0B", "ma50": "#2563EB",
    "sidebar": "#0F1B24", "sidebar_text": "#C9D3DC", "sidebar_label": "#8A98A6",
    "warn_bg": "#FFF7E6", "warn_border": "#F59E0B",
}
# bảng màu báo cáo PDF – giữ nguyên
LIGHT = {**COMMON, "dark": False, "bg": "#F4F6F9", "card": "#FFFFFF", "border": "#E3E8EF", "text": "#0F172A",
         "muted": "#5B6B7F", "accent": "#0F766E", "grid": "#E3E8EF", "track": "#EEF2F6", "soft": "#F8FAFC",
         "insight_bg": "#FFFBEB", "insight_border": "#FCD34D"}
DARK = {**COMMON, "dark": True, "sidebar": "#081221", "bg": "#0A1628", "card": "#0F1E33", "border": "#1E3050",
        "text": "#E8EEF6", "muted": "#94A6BD", "accent": "#2DD4BF", "grid": "#1C2D47", "track": "#172A44",
        "soft": "#13243C", "insight_bg": "#2A2414", "insight_border": "#A16207"}
# bảng màu web (taste-skill: "Frost and slate" sáng · "Night and sky" tối, màu nhấn giữ xanh ngọc của thương hiệu)
WEB_LIGHT = {**LIGHT, "bg": "#F5F7F8", "card": "#FFFFFF", "border": "#DDE3E7", "text": "#1B2A33", "muted": "#5A6872",
             "accent": "#0D7480", "accent_ink": "#FFFFFF", "grid": "#E6EBEE", "track": "#EDF1F3", "soft": "#F1F4F6",
             "hover": "#E8F2F3", "insight_bg": "#F1F4F6", "insight_border": "#DDE3E7"}
WEB_DARK = {**DARK, "sidebar": "#0B1017", "bg": "#0A0D14", "card": "#11161F", "border": "#232B38", "text": "#E9EDF3",
            "muted": "#949EAE", "accent": "#2DD4BF", "accent_ink": "#06201C", "grid": "#1B2230", "track": "#18202C",
            "soft": "#151B26", "hover": "rgba(45,212,191,.10)", "insight_bg": "#151B26", "insight_border": "#232B38"}
GOLD = {"dark": "#F5B341", "light": "#B7791F"}             # chỉ còn cho logo / đường MA20 – không dùng làm màu nhấn giao diện
FONT = "'IBM Plex Sans', 'Be Vietnam Pro', system-ui, -apple-system, 'Segoe UI', sans-serif"
MONO = "'IBM Plex Mono', ui-monospace, 'SFMono-Regular', Consolas, monospace"
SERIF = FONT                                                # tên cũ – một họ chữ sans duy nhất
ABSORB_COLORS = {"absorb": "#16A34A", "joint_sell": "#DC2626", "joint_buy": "#2563EB",
                 "domestic_take": "#D97706", "neutral": "#94A3B8"}
SESSION_COLORS = {"broad_up": "#16A34A", "narrow_up": "#84CC16", "flat": "#94A3B8",
                  "narrow_down": "#F97316", "broad_down": "#DC2626"}
EASE = "cubic-bezier(.2,.8,.2,1)"


def palette(mode: str = "light") -> Dict:
    return WEB_DARK if mode == "dark" else WEB_LIGHT


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
        font=dict(family=FONT, color=p["text"], size=12.5),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=[p["accent"], "#2563EB", "#D97706", "#E11D48", "#0891B2", "#65A30D", "#64748B"],
        xaxis=dict(gridcolor=p["grid"], zerolinecolor=p["grid"], linecolor=p["border"], automargin=True),
        yaxis=dict(gridcolor=p["grid"], zerolinecolor=p["grid"], linecolor=p["border"], automargin=True),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.08, x=0),
        margin=dict(l=8, r=8, t=30, b=8),
        hoverlabel=dict(font_family=FONT, bgcolor=p["card"], bordercolor=p["border"], font_color=p["text"]),
    )
    pio.templates[name] = tpl
    pio.templates["ffr"] = tpl
    return name


def css(mode: str = "light") -> str:
    p = palette(mode)
    D = p["dark"]
    TXT, MUT, ACC, AINK, BD, CARD, SOFT, TRACK = (p["text"], p["muted"], p["accent"], p["accent_ink"], p["border"],
                                                    p["card"], p["soft"], p["track"])
    HOV = p["hover"]
    # thanh bên: một nền mực phẳng ở cả hai chế độ
    SB, SBT, SBL = p["sidebar"], p["sidebar_text"], p["sidebar_label"]
    SBLINE = "rgba(255,255,255,.08)"
    SBFILL = "rgba(255,255,255,.05)"
    SBACC = "#2DD4BF"
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap&subset=vietnamese');
:root {{ --ffr-bg:{p['bg']}; --ffr-card:{CARD}; --ffr-border:{BD}; --ffr-text:{TXT}; --ffr-muted:{MUT};
  --ffr-accent:{ACC}; --ffr-accent-ink:{AINK}; --ffr-soft:{SOFT}; --ffr-up:{p['up']}; --ffr-down:{p['down']}; --ffr-ref:{p['ref']};
  --ffr-gold:{ACC}; --ffr-serif:{FONT}; --ffr-mono:{MONO}; --ffr-font:{FONT};
  --r-sm:8px; --r-md:12px; --r-lg:16px; --ease:{EASE}; --m-in:150ms; --m-out:120ms; --m-press:90ms; }}

/* ── nền, chữ ── */
html, body, [data-testid="stAppViewContainer"], .stApp {{ background:{p['bg']} !important; color:{TXT};
  font-family:{FONT}; font-size:15px; -webkit-font-smoothing:antialiased; font-feature-settings:"tnum" 1; }}
h1,h2,h3,h4,p,span,div,label,li,td,th,input,textarea,button {{ font-family:{FONT}; }}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {{ line-height:1.6; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ font-size:13.5px !important; line-height:1.55; color:{MUT} !important; }}
[data-testid="stHeader"] {{ background:transparent; }}
.block-container {{ padding:16px 32px 48px !important; max-width:1560px !important; }}
code, kbd, pre {{ font-family:{MONO} !important; }}
::selection {{ background:{'rgba(45,212,191,.28)' if D else '#CDE7EA'}; }}
*:focus-visible {{ outline:2px solid {ACC} !important; outline-offset:2px; }}

/* nút mở lại thanh bên khi đã thu gọn */
[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {{ z-index:1000020 !important;
  visibility:visible !important; opacity:1 !important; display:flex !important; }}
[data-testid="stSidebarCollapsedControl"] button, button[data-testid="stExpandSidebarButton"],
[data-testid="stExpandSidebarButton"] button {{ background:{ACC} !important; color:{AINK} !important; border:1px solid {ACC} !important;
  border-radius:var(--r-sm) !important; width:40px !important; height:40px !important; box-shadow:none !important;
  opacity:1 !important; visibility:visible !important; }}
[data-testid="stSidebarCollapsedControl"] svg, [data-testid="stExpandSidebarButton"] svg,
[data-testid="stSidebarCollapsedControl"] span, [data-testid="stExpandSidebarButton"] span {{ color:{AINK} !important; fill:{AINK} !important; }}

/* ── thanh bên: nền mực phẳng, một đường kẻ, mục đang mở tô màu nhấn ── */
section[data-testid="stSidebar"] {{ background:{SB} !important; width:316px !important; min-width:316px !important;
  border-right:1px solid {SBLINE}; }}
section[data-testid="stSidebar"] * {{ color:{SBT}; }}
[data-testid="stAppViewContainer"] {{ height:100vh !important; height:100dvh !important; max-height:100dvh !important; }}
section[data-testid="stSidebar"] {{ height:100vh !important; height:100dvh !important; max-height:100dvh !important; }}
[data-testid="stSidebarContent"] {{ height:100% !important; max-height:100dvh !important; overflow-y:auto !important; overscroll-behavior:contain;
  -webkit-overflow-scrolling:touch; scrollbar-width:thin; scrollbar-color:rgba(255,255,255,.22) transparent; }}
[data-testid="stSidebarContent"]::-webkit-scrollbar {{ width:8px; }}
[data-testid="stSidebarContent"]::-webkit-scrollbar-track {{ background:transparent; }}
[data-testid="stSidebarContent"]::-webkit-scrollbar-thumb {{ background:rgba(255,255,255,.22); border-radius:8px; }}
[data-testid="stSidebarContent"]::-webkit-scrollbar-thumb:hover {{ background:rgba(255,255,255,.36); }}
section[data-testid="stSidebar"] input {{ background:{SBFILL} !important; color:#EEF2F6 !important; border:1px solid {SBLINE} !important; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{ background:#17232E !important; border:1px solid rgba(255,255,255,.12) !important;
  border-radius:var(--r-sm) !important; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] * {{ color:#EEF2F6 !important; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] input::placeholder {{ color:#8A98A6 !important; }}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] div:has(> input) {{ background:#17232E !important;
  border:1px solid rgba(255,255,255,.12) !important; border-radius:var(--r-sm) !important; }}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] input {{ background:transparent !important; color:#EEF2F6 !important; }}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] input::placeholder {{ color:#8A98A6 !important; opacity:1; }}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] button {{ background:transparent !important; border:none !important; }}
section[data-testid="stSidebar"] button {{ background:{SBFILL} !important; border:1px solid rgba(255,255,255,.12) !important;
  padding:4px 10px !important; border-radius:var(--r-sm) !important; }}
section[data-testid="stSidebar"] button p {{ color:#EEF2F6 !important; font-size:13px; white-space:nowrap; }}
.ffr-brand {{ display:flex; align-items:center; gap:12px; margin:0 0 16px; padding:12px; border-radius:var(--r-md);
  background:{SBFILL}; border:1px solid {SBLINE}; }}
.ffr-brand svg {{ flex:0 0 auto; }}
.ffr-brand b {{ display:block; color:#F5F7F9 !important; font-size:16px; font-weight:600; line-height:1.25; letter-spacing:-.01em; white-space:nowrap; }}
.ffr-brand small {{ display:block; color:{SBL} !important; font-size:12px; font-weight:400; white-space:nowrap; line-height:1.4; }}
.ffr-grp {{ display:flex; align-items:center; gap:8px; margin:20px 0 4px 4px; }}
.ffr-grp span {{ color:{SBL} !important; font-size:13px; font-weight:500; letter-spacing:0; text-transform:none; white-space:nowrap; }}
.ffr-grp::after {{ content:""; flex:1; height:1px; background:{SBLINE}; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a {{ border-radius:var(--r-sm); padding:8px 12px !important; margin:1px 0;
  border:1px solid transparent; transition:background var(--m-in) var(--ease), color var(--m-in) var(--ease); }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a p {{ color:{SBT} !important; font-size:14.5px !important; font-weight:500 !important; white-space:nowrap; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a span {{ color:{SBL} !important; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {{ background:{SBFILL} !important; }}
section[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover p {{ color:#FFFFFF !important; }}
section[data-testid="stSidebar"] .st-key-nav_active [data-testid="stPageLink"] a {{ background:rgba(45,212,191,.12) !important;
  border:1px solid rgba(45,212,191,.30) !important; box-shadow:inset 2px 0 0 {SBACC}; }}
section[data-testid="stSidebar"] .st-key-nav_active [data-testid="stPageLink"] a p {{ color:#FFFFFF !important; font-weight:600 !important; }}
section[data-testid="stSidebar"] .st-key-nav_active [data-testid="stPageLink"] a span {{ color:{SBACC} !important; }}
.ffr-sep {{ height:1px; background:{SBLINE}; margin:16px 0 12px; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] details {{ background:transparent !important;
  border:1px solid {SBLINE} !important; border-radius:var(--r-md) !important; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary p {{ color:#E6EBF0 !important; font-weight:500; }}
.ffr-srcbox {{ background:transparent; border:1px solid {SBLINE}; border-radius:var(--r-md); padding:12px; font-size:13px; margin-top:12px; }}
.ffr-srct {{ color:{SBL} !important; font-size:13px; font-weight:500; letter-spacing:0; text-transform:none; margin-bottom:6px; }}
.ffr-srcr {{ display:flex; align-items:center; padding:3px 0; color:{SBT} !important; }}
.ffr-srcr em {{ margin-left:auto; font-style:normal; color:#F5F7F9 !important; font-weight:500; font-variant-numeric:tabular-nums; }}
.ffr-disc {{ border:1px solid {SBLINE}; background:transparent; border-radius:var(--r-md); padding:12px; font-size:13px; margin-top:12px;
  line-height:1.55; color:{SBT} !important; }}
.ffr-disc-t {{ font-weight:600; color:#F5F7F9 !important; font-size:13px; margin-bottom:2px; }}
.ffr-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:8px; }}

/* ── nội dung: đầu mục, thẻ, chỉ số ── */
.ffr-acad {{ display:flex; align-items:center; gap:8px; background:transparent; border:none; border-bottom:1px solid {BD};
  padding:0 0 8px; margin:0 0 12px; font-size:13px; color:{MUT}; }}
.ffr-acad b, .ffr-acad b.ffr-gold {{ color:{TXT} !important; font-weight:600; }}
.ffr-head {{ display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap; gap:12px; margin-bottom:12px; }}
.ffr-title {{ font-size:24px; font-weight:600; color:{TXT}; letter-spacing:-.02em; }}
.ffr-sub {{ font-size:14px; color:{MUT}; }}
.ffr-pill {{ font-size:13px; font-weight:500; padding:4px 10px; border-radius:999px; border:1px solid {BD};
  background:{CARD}; color:{MUT}; display:inline-flex; align-items:center; gap:6px; margin-left:6px; }}
.ffr-card {{ background:{CARD}; border:1px solid {BD}; border-radius:var(--r-md); padding:16px; height:100%; box-shadow:none; }}
.ffr-lbl {{ font-size:13px; font-weight:500; letter-spacing:0; text-transform:none; color:{MUT}; }}
.ffr-val {{ font-size:26px; font-weight:600; color:{TXT}; line-height:1.15; margin-top:4px; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }}
.ffr-chg {{ font-size:14px; font-weight:600; font-variant-numeric:tabular-nums; }}
.ffr-meta {{ display:flex; justify-content:space-between; font-size:13px; color:{MUT}; margin-top:6px; font-variant-numeric:tabular-nums; gap:6px; }}
.ffr-sec {{ display:flex; align-items:baseline; gap:12px; margin:32px 0 12px; flex-wrap:wrap; }}
.ffr-sec h3 {{ font-size:19px; font-weight:600; color:{TXT}; margin:0; padding:0; letter-spacing:-.01em; }}
.ffr-sec span {{ font-size:14px; color:{MUT}; }}
.ffr-new {{ font-size:12px; font-weight:600; background:{ACC}; color:{AINK} !important; padding:2px 6px; border-radius:6px; }}
.ffr-chip {{ display:inline-block; padding:2px 8px; border-radius:6px; font-size:13px; font-weight:500; white-space:nowrap; }}
.ffr-intro {{ background:{CARD}; border:1px solid {BD}; border-radius:var(--r-md); padding:12px 16px; font-size:14px; color:{MUT};
  margin:4px 0 16px; display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; }}
.ffr-intro b {{ color:{TXT}; }}
.ffr-status {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; font-size:13px; color:{MUT}; margin-bottom:8px; }}
.ffr-insight {{ background:transparent; border:none; border-left:2px solid {ACC}; border-radius:0; padding:4px 0 4px 12px;
  color:{TXT}; font-size:14.5px; line-height:1.6; }}
.ffr-lead {{ font-size:15px; line-height:1.6; color:{TXT}; margin:12px 2px 2px; max-width:110ch; }}
.ffr-lead b {{ font-weight:600; }}
.ffr-note {{ display:flex; align-items:center; gap:8px; border-radius:var(--r-sm); padding:8px 12px; margin:0 0 12px; font-size:13.5px;
  background:{SOFT}; border:1px solid {BD}; color:{TXT}; }}
.ffr-note b {{ color:{TXT}; font-weight:600; }}
.ffr-bar {{ display:flex; height:12px; border-radius:999px; overflow:hidden; background:{TRACK}; margin:8px 0 6px; }}
.ffr-legend {{ display:flex; justify-content:space-between; font-size:13px; font-weight:600; font-variant-numeric:tabular-nums; flex-wrap:wrap; gap:6px; }}
.ffr-kpi {{ background:{CARD}; border:1px solid {BD}; border-radius:var(--r-md); padding:12px 16px; height:100%; }}
.ffr-kpi small {{ font-size:13px; color:{MUT}; font-weight:500; text-transform:none; letter-spacing:0; }}
.ffr-kpi b {{ display:block; font-size:22px; font-weight:600; letter-spacing:-.01em; font-variant-numeric:tabular-nums; margin-top:2px; }}
.ffr-sym, .tc-sym {{ font-weight:600; color:{ACC} !important; }}
.ffr-gold, b.ffr-gold {{ color:{ACC} !important; }}
.ffr-comp {{ display:flex; justify-content:space-between; font-size:13px; color:{MUT}; margin:8px 0 4px; }}
.ffr-comp b {{ color:{TXT}; }}
.ffr-track {{ height:6px; border-radius:999px; background:{TRACK}; overflow:hidden; }}
.ffr-track i {{ display:block; height:100%; border-radius:999px; }}
.ffr-foot {{ font-size:13px; color:{MUT}; margin-top:32px; padding-top:12px; border-top:1px solid {BD};
  display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; }}
.ffr-demo {{ background:#FEF3C7; color:#92400E !important; border:1px solid #F59E0B; }}
.ffr-strip {{ display:flex; gap:12px; overflow-x:auto; padding-bottom:4px; }}
.ffr-strip .ffr-card {{ min-width:215px; flex:1; }}
div[data-testid="stMetric"] {{ background:{CARD}; border:1px solid {BD}; border-radius:var(--r-md); padding:12px 16px; }}

/* ── bảng: số căn phải, đường kẻ mảnh, hàng rê chuột đổi nền nhẹ ── */
table.ffr-t, table.tc-t {{ width:100%; border-collapse:collapse; font-size:14px; font-variant-numeric:tabular-nums; }}
table.ffr-t th, table.tc-t th {{ text-align:right; font-size:13px; font-weight:500; color:{MUT}; text-transform:none; letter-spacing:0;
  padding:8px; border-bottom:1px solid {BD}; white-space:normal; vertical-align:bottom; }}
table.ffr-t td, table.tc-t td {{ white-space:nowrap; text-align:right; padding:7px 8px; border-bottom:1px solid {TRACK}; color:{TXT}; }}
table.ffr-t th.l, table.ffr-t td.l, table.tc-t th.l, table.tc-t td.l {{ text-align:left; }}
table.ffr-t td.l {{ white-space:normal; }}
table.ffr-t td:first-child {{ white-space:nowrap; }}
table.tc-t td:first-child {{ color:{MUT}; }}
table.tc-t tbody tr:nth-child(odd) td {{ background:transparent; }}
table.ffr-t tr:hover td, table.tc-t tbody tr:hover td {{ background:{HOV} !important; }}
.tc-tw {{ width:100%; overflow-x:auto; }}

/* ── thẻ widget (st-key-tcw…): một kiểu thẻ cho cả trang ── */
div[class*="st-key-tcw"] {{ background:{CARD} !important; border:1px solid {BD} !important; border-radius:var(--r-lg) !important;
  box-shadow:none !important; padding:16px 20px 20px !important; overflow:hidden; }}
.tc-head {{ background:{CARD}; border-radius:var(--r-md); padding:16px 20px; border:1px solid {BD}; }}
.tc-h1 {{ font-size:26px; font-weight:600; color:{TXT}; letter-spacing:-.02em; line-height:1.15; }}
.tc-date {{ font-size:14px; color:{MUT}; margin-top:4px; }}
.tc-title {{ text-align:left !important; font-size:17px !important; font-weight:600 !important; color:{TXT} !important;
  letter-spacing:-.01em; padding:0 !important; }}
.tc-title::before {{ content:none !important; }}
.tc-sub {{ text-align:left !important; font-size:13.5px !important; color:{MUT} !important; margin:2px 0 12px 0 !important; }}
.tc-row {{ display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; font-size:13px; color:{MUT}; margin-top:6px; }}
.tc-row b {{ color:{TXT}; }}
.tc-breadth {{ display:flex; height:16px; border-radius:4px; overflow:hidden; margin-top:6px; }}
.tc-breadth i {{ display:flex; align-items:center; justify-content:center; color:#fff; font-size:12px; font-style:normal; font-weight:600; }}
.tc-note {{ font-size:13px; color:{MUT}; margin-top:6px; }}

/* ── tab cấp trang: to, IN HOA (theo yêu cầu), tab đang chọn tô kín màu nhấn ── */
.stTabs [role="tablist"] {{ gap:6px; border-bottom:1px solid {BD}; padding-bottom:0; flex-wrap:wrap; }}
.stTabs [data-testid="stTab"] {{ padding:10px 18px !important; border-radius:var(--r-sm) var(--r-sm) 0 0; background:transparent;
  border:1px solid transparent; border-bottom:none; height:auto;
  transition:background var(--m-in) var(--ease), color var(--m-in) var(--ease); }}
.stTabs [data-testid="stTab"] p {{ font-size:14.5px !important; font-weight:600 !important; text-transform:uppercase;
  letter-spacing:.04em; color:{MUT} !important; }}
.stTabs [data-testid="stTab"]:hover {{ background:{HOV}; }}
.stTabs [data-testid="stTab"]:hover p {{ color:{TXT} !important; }}
.stTabs [data-testid="stTab"][aria-selected="true"] {{ background:{ACC} !important; border-color:{ACC}; }}
.stTabs [data-testid="stTab"][aria-selected="true"] p {{ color:{AINK} !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs .react-aria-SelectionIndicator {{ background:{ACC} !important; }}
.stTabs [data-baseweb="tab-border"] {{ display:none; }}
/* tab trong thẻ: nút chọn nhỏ, chữ thường, mục đang chọn tô màu nhấn */
div[class*="st-key-tcw"] .stTabs [role="tablist"] {{ border-bottom:none !important; background:{SOFT}; border-radius:10px;
  padding:3px; gap:3px !important; flex-wrap:nowrap; }}
div[class*="st-key-tcw"] .stTabs [data-testid="stTab"] {{ flex:1 1 0; min-width:0; justify-content:center; background:transparent !important;
  border:none !important; border-radius:var(--r-sm) !important; padding:6px 6px !important; margin:0; }}
div[class*="st-key-tcw"] .stTabs [data-testid="stTab"] p {{ font-size:13.5px !important; font-weight:500 !important; color:{MUT} !important;
  text-transform:none !important; letter-spacing:0 !important; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
div[class*="st-key-tcw"] .stTabs [data-testid="stTab"]:hover p {{ color:{TXT} !important; }}
div[class*="st-key-tcw"] .stTabs [aria-selected="true"] {{ background:{CARD} !important; box-shadow:0 0 0 1px {BD}; }}
div[class*="st-key-tcw"] .stTabs [aria-selected="true"] p {{ color:{TXT} !important; font-weight:600 !important; }}
div[class*="st-key-tcw"] .stTabs .react-aria-SelectionIndicator,
div[class*="st-key-tcw"] .stTabs [data-baseweb="tab-highlight"], div[class*="st-key-tcw"] .stTabs [data-baseweb="tab-border"] {{ display:none; }}

/* ── nút, nhóm nút, ô nhập ── */
div[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background:{ACC} !important; border-color:{ACC} !important; }}
div[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color:{AINK} !important; }}
[data-testid="stMain"] [data-testid^="stBaseButton"], [data-testid="stMain"] [data-testid="stDownloadButton"] button {{
  border-radius:var(--r-sm) !important; min-height:40px; box-shadow:none !important;
  transition:transform var(--m-out) var(--ease), background var(--m-in) var(--ease), border-color var(--m-in) var(--ease); }}
[data-testid="stMain"] [data-testid="stBaseButton-primary"] {{ background:{ACC} !important; border-color:{ACC} !important; }}
[data-testid="stMain"] [data-testid="stBaseButton-primary"] p {{ color:{AINK} !important; font-weight:600; }}
[data-testid="stMain"] [data-baseweb="select"] > div, [data-testid="stMain"] [data-baseweb="input"] {{ border-radius:var(--r-sm) !important; }}
[data-testid="stMain"] [data-testid="stExpander"] details {{ border:1px solid {BD} !important; border-radius:var(--r-md) !important;
  background:{CARD}; }}
[data-testid="stMain"] [data-testid="stExpander"] summary p {{ font-weight:500; }}
[data-testid="stAlert"] {{ border-radius:var(--r-md) !important; }}
@media (hover:hover) and (pointer:fine) {{
  [data-testid="stMain"] [data-testid^="stBaseButton"]:not(:disabled):hover,
  [data-testid="stMain"] [data-testid="stDownloadButton"] button:not(:disabled):hover {{ transform:translateY(-1px); }}
  [data-testid="stMain"] [data-testid^="stBaseButton"]:not(:disabled):active,
  [data-testid="stMain"] [data-testid="stDownloadButton"] button:not(:disabled):active {{ transform:translateY(1px) scale(.985);
    transition-duration:var(--m-press); }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; animation:none !important; }} }}
@media (max-width: 640px) {{ .block-container {{ padding:12px 16px 40px !important; }} .ffr-val {{ font-size:22px; }} }}
</style>"""
