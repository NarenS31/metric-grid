"""Design system: dark civic-research look. Inter for text, IBM Plex Mono for numbers and metadata (both bundled and embedded, so no
network). Colors, a 4/8 px spacing scale and five type sizes live here as CSS variables; chart code reads the same palette."""
import base64
from functools import lru_cache
from pathlib import Path

FONTS = Path(__file__).resolve().parent / "assets" / "fonts"

# Palette (single source for CSS, maps and charts)
BG, SURFACE, ELEVATED = "#0B1020", "#111A2E", "#172238"
BLUE, TEAL, AMBER, RED = "#6EA8FE", "#70E1C8", "#F3BD69", "#F07878"
TEXT, MUTED, BORDER = "#F3F6FC", "#99A8BF", "#26344B"
# Series colors used identically on maps, strips and charts
MW_ONLY = "#D5DDEB"      # megawatts-only plan: neutral light
VULN_AWARE = BLUE        # vulnerability-aware plan
DOTS = "#6B7C96"         # each of the 200 plans
COST, HOUSEHOLDS = TEAL, AMBER


@lru_cache(maxsize=1)
def font_faces() -> str:
    """@font-face rules with the bundled fonts as base64 (cached). Falls back to system fonts if a file is missing."""
    def face(family: str, file: str, weight: str) -> str:
        p = FONTS / file
        if not p.exists():
            return ""
        b64 = base64.b64encode(p.read_bytes()).decode()
        return (f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;font-display:swap;"
                f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    return face("Inter", "inter-vf.woff2", "100 900") + face("IBM Plex Mono", "plex-mono-400.woff2", "400") + face("IBM Plex Mono", "plex-mono-500.woff2", "500")


def css() -> str:
    return "<style>" + font_faces() + f"""
:root {{ --bg:{BG}; --surface:{SURFACE}; --elevated:{ELEVATED}; --blue:{BLUE}; --teal:{TEAL}; --amber:{AMBER}; --red:{RED};
  --text:{TEXT}; --muted:{MUTED}; --border:{BORDER}; --mwonly:{MW_ONLY};
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s6:24px; --s8:32px; --s12:48px; --s16:64px;
  --t-display:40px; --t-stat:28px; --t-h2:22px; --t-body:15px; --t-small:13px;
  --sans:'Inter',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif; --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
.stApp {{ background: var(--bg); color: var(--text); }}
html, body, .stApp, .stMarkdown, p, li, label, span, div, td, th, button, input, textarea {{ font-family: var(--sans); }}
html, body {{ overflow-x:hidden; font-size: var(--t-body); -webkit-font-smoothing:antialiased; }}
p, li, label {{ font-size: var(--t-body); line-height:1.55; }}
header[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"] button {{ color: var(--text) !important; }}
[data-testid="stExpandSidebarButton"] {{ background: var(--surface); border:1px solid var(--border); border-radius:6px; }}
footer, #MainMenu, [data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stDecoration"], [data-testid="stAppDeployButton"], [data-testid="stStatusWidget"] {{ display:none !important; }}
.block-container {{ max-width:1200px; padding: var(--s4) var(--s8) var(--s16) var(--s8); margin:0 auto; }}
[data-testid="stVerticalBlock"] {{ gap: var(--s4); }}
.mono, code, pre, .num {{ font-family: var(--mono) !important; font-variant-numeric: tabular-nums; }}
:focus-visible {{ outline:2px solid var(--blue) !important; outline-offset:2px; border-radius:4px; }}
a {{ color: var(--blue); text-decoration:none; }} a:hover {{ text-decoration:underline; }}

/* sidebar shell */
[data-testid="stSidebar"] {{ background: var(--surface); border-right:1px solid var(--border); }}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding: var(--s6) var(--s4); }}
.brand {{ display:flex; align-items:center; gap: var(--s3); margin-bottom: var(--s6); }}
.brand svg {{ width:28px; height:28px; flex:none; }}
.brand .name {{ font-size:17px; font-weight:600; letter-spacing:-0.01em; color: var(--text); }}
.brand .name b {{ font-weight:600; color: var(--blue); }}
.nav {{ display:flex; flex-direction:column; gap:2px; margin-bottom: var(--s6); }}
.nav {{ gap:2px !important; }}
[data-testid="stSidebar"] .nav a {{ display:block; text-decoration:none !important; color: var(--muted); font-size: var(--t-small); padding: var(--s2) var(--s3); border-radius:6px; border-left:2px solid transparent; transition: background .12s, color .12s; }}
.nav a:hover {{ background: var(--elevated); color: var(--text); }}
.nav a.on {{ color: var(--text); border-left-color: var(--blue); background: var(--elevated); }}
.side-meta {{ color: var(--muted); font-size: var(--t-small); line-height:1.5; border-top:1px solid var(--border); padding-top: var(--s4); }}
.side-meta .k {{ display:block; margin-top: var(--s3); }}
.side-meta .mono {{ color: var(--text); font-size: var(--t-small); }}

/* page header */
.pagehead {{ display:flex; justify-content:space-between; align-items:flex-start; gap: var(--s6); flex-wrap:wrap; margin-bottom: var(--s2); }}
.crumb {{ color: var(--muted); font-size: var(--t-small); margin: 0 0 var(--s2) 0; }}
.crumb .mono {{ color: var(--muted); }}
.title {{ font-size: var(--t-display); line-height:1.12; font-weight:600; letter-spacing:-0.025em; margin:0 0 var(--s2) 0; color: var(--text); }}
.deck {{ color: var(--muted); font-size: var(--t-body); max-width: 820px; margin:0; }}
.deck b {{ color: var(--text); font-weight:500; }}
.fresh {{ text-align:right; color: var(--muted); font-size: var(--t-small); line-height:1.5; }}
.fresh .mono {{ color: var(--text); }}

/* metric cards */
.tiles {{ display:grid; grid-template-columns:repeat(4,1fr); gap: var(--s4); margin-bottom: var(--s2); }}
.tile {{ background: var(--surface); border:1px solid var(--border); border-radius:8px; padding: var(--s3) var(--s4); transition: border-color .12s; }}
.tile:hover {{ border-color:#34476A; }}
.tile .l {{ color: var(--text); font-size: var(--t-small); margin:var(--s2) 0 0 0; line-height:1.35; }}
.tile .v {{ font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: var(--t-stat); font-weight:500; line-height:1.1; color: var(--text); letter-spacing:-0.02em; }}
.tile .v small {{ font-size: var(--t-small); color: var(--muted); font-weight:400; margin-left: var(--s1); letter-spacing:0; }}
.tile .s {{ color: var(--muted); font-size: var(--t-small); margin-top: var(--s2); line-height:1.4; }}
.tile.good .v {{ color: var(--teal); }} .tile.attn {{ border-color:#5A4A2A; }} .tile.attn .v {{ color: var(--amber); }}

/* controls */
[data-testid="stVerticalBlockBorderWrapper"] {{ background: var(--surface); border:1px solid var(--border) !important; border-radius:8px; }}
.stApp [data-testid="stSlider"] [role="slider"] {{ background: var(--blue); }}
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{ display:none !important; }}
button {{ transition: border-color .12s, background .12s; }}
[data-testid="stCaptionContainer"], .stCaption {{ font-size: var(--t-small); color: var(--muted); }}

/* maps */
.maptitle {{ font-size: var(--t-body); font-weight:600; margin:0; padding-bottom: var(--s2); display:flex; align-items:center; gap: var(--s2); }}
.maptitle .dot {{ width:10px; height:10px; border-radius:2px; flex:none; }}
.mapnums {{ font-family: var(--mono); font-size: var(--t-small); color: var(--muted); margin:0; font-variant-numeric: tabular-nums; }}
svg.map {{ width:100%; height:auto; max-height:300px; display:block; margin:0 auto; border-radius:8px; border:1px solid var(--border); background: var(--surface); }}
.legend {{ display:flex; gap: var(--s4); align-items:center; font-size: var(--t-small); color: var(--muted); flex-wrap:wrap; }}
.sw {{ display:inline-block; width:10px; height:10px; border-radius:2px; vertical-align:middle; margin-right: var(--s1); border:1px solid #FFFFFF22; }}
.fine {{ color: var(--muted); font-size: var(--t-small); margin:0; line-height:1.5; }}
.fine + .fine, p + .fine {{ margin-top: var(--s3); }}
[data-testid="stVerticalBlockBorderWrapper"] > div {{ padding-bottom: var(--s1); }}

/* sections */
.sec {{ margin-top: var(--s12); scroll-margin-top: var(--s6); }}
.sec h2 {{ font-size: var(--t-h2); font-weight:600; letter-spacing:-0.015em; margin:0 0 var(--s2) 0; padding:0; color: var(--text); }}
.sec p.lede {{ color: var(--muted); font-size: var(--t-body); margin:0 0 var(--s2) 0; max-width:760px; }}
.src {{ color: var(--muted); font-size: var(--t-small); margin:0 0 var(--s4) 0; }}
.src .kind {{ font-family: var(--mono); color: var(--teal); }}
.honest {{ border-left:2px solid var(--amber); background: var(--surface); padding: var(--s3) var(--s4); border-radius:0 8px 8px 0; margin:0; }}
.honest, .honest * {{ font-size: var(--t-body); }}
.note {{ background: var(--surface); border:1px solid var(--border); border-radius:8px; padding: var(--s3) var(--s4); font-size: var(--t-small); }}
.note.warn {{ border-color: var(--amber); }}
.flip {{ font-size: var(--t-small); line-height:1.45; padding: var(--s2) 0; border-bottom:1px solid var(--border); }}
.flipcol h4 {{ font-size: var(--t-body); font-weight:600; margin: var(--s2) 0; }}
.tip {{ border-bottom:1px dotted var(--muted); cursor:help; }}
.badge {{ display:inline-block; padding:2px var(--s2); border-radius:4px; font-size: var(--t-small); background: var(--elevated); border:1px solid var(--border); margin-right: var(--s2); color: var(--muted); }}
.badge.v {{ color: var(--blue); border-color:#2C4A7A; }}

/* tables */
table.t {{ border-collapse:collapse; width:100%; }}
table.t th {{ text-align:left; color: var(--muted); font-weight:500; border-bottom:1px solid var(--border); padding: var(--s2) var(--s3); font-size: var(--t-small); }}
table.t td {{ border-bottom:1px solid #1B2840; padding: var(--s3); vertical-align:top; font-size: var(--t-small); }}
table.t tr:last-child td {{ border-bottom:none; }}
table.t tbody tr:hover td, table.t tr:hover td {{ background:#14203A; }}
.prio td:nth-child(n+3), .prio th:nth-child(n+3), .tmp td:nth-child(n+2), .tmp th:nth-child(n+2) {{ font-family: var(--mono); font-variant-numeric: tabular-nums; text-align:right; }}
.prio td:nth-child(1), .loc td:nth-child(2) {{ font-family: var(--mono); }}
.prio td:last-child, .prio th:last-child {{ font-family: var(--sans); text-align:left; }}
code, pre {{ font-size: var(--t-small) !important; background: var(--elevated) !important; color: var(--text); }}
[data-testid="stExpander"] {{ border:1px solid var(--border); border-radius:8px; background: var(--surface); }}
iframe, canvas {{ max-width:100%; }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; }} }}
@media (max-width: 700px) {{
  :root {{ --t-display:28px; --t-stat:22px; }}
  .block-container {{ padding-left: var(--s4); padding-right: var(--s4); padding-top: var(--s12); }}
  .tiles {{ grid-template-columns:repeat(2,1fr); gap: var(--s2); }}
  .tile {{ padding: var(--s3); }}
  .fresh {{ text-align:left; }}
  .sec {{ margin-top: var(--s8); }}
}}
</style>"""


# Back-compat name used by older code and tests
CSS = css()

LOGO_SVG = (f"<svg viewBox='0 0 28 28' xmlns='http://www.w3.org/2000/svg' aria-hidden='true'>"
            f"<rect x='1' y='1' width='7' height='7' rx='1.5' fill='{BORDER}'/><rect x='10.5' y='1' width='7' height='7' rx='1.5' fill='{BORDER}'/>"
            f"<rect x='20' y='1' width='7' height='7' rx='1.5' fill='{BLUE}'/><rect x='1' y='10.5' width='7' height='7' rx='1.5' fill='{BORDER}'/>"
            f"<rect x='10.5' y='10.5' width='7' height='7' rx='1.5' fill='{BLUE}'/><rect x='20' y='10.5' width='7' height='7' rx='1.5' fill='{BORDER}'/>"
            f"<rect x='1' y='20' width='7' height='7' rx='1.5' fill='{BLUE}'/><rect x='10.5' y='20' width='7' height='7' rx='1.5' fill='{BORDER}'/>"
            f"<rect x='20' y='20' width='7' height='7' rx='1.5' fill='{BORDER}'/></svg>")
