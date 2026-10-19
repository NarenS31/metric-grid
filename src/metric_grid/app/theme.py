"""Editorial look: warm off-white, dark ink, one serif for headings, one sans for text, violet only for the vulnerability-aware plan
and key numbers. Four font sizes (40/28 serif, 16/13 sans; 28/16 on a phone) on an 8 px spacing scale. No external fonts or assets (offline)."""
INK, BG, ACCENT, MUTED = "#1C1A24", "#FAF7F2", "#5B3FD6", "#6B6678"

CSS = f"""
<style>
:root {{ --ink:{INK}; --bg:{BG}; --accent:{ACCENT}; --muted:{MUTED}; --line:#E3DCCF; --card:#FFFDF9; --neutral:#2B2833;
  --s1:8px; --s2:16px; --s3:24px; --s4:32px; --s6:48px; --s8:64px; --h1:40px; --h2:28px; --body:16px; --small:13px; }}
.stApp {{ background: var(--bg); color: var(--ink); }}
header[data-testid="stHeader"], footer, #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stAppDeployButton"], [data-testid="stStatusWidget"], [data-testid="stBaseButton-header"] {{ display:none !important; }}
.block-container {{ max-width: 1200px; padding: var(--s1) var(--s3) var(--s8) var(--s3); margin: 0 auto; }}
[data-testid="stVerticalBlock"] {{ gap: var(--s2); }}
html, body, .stApp, .stMarkdown, p, li, label, span, div, td, th, button, input {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }}
html, body {{ overflow-x:hidden; font-size: var(--body); }}
p, li, label, td {{ font-size: var(--body); line-height: 1.5; }}
h1, h2, h3, .serif {{ font-family: Georgia, "Times New Roman", serif !important; color: var(--ink); letter-spacing: -0.01em; }}
.topbar {{ display:flex; align-items:center; gap:var(--s2); padding-bottom:var(--s1); flex-wrap:wrap; }}
.brand {{ font-family: Georgia, serif; font-size: var(--body); font-weight:700; letter-spacing:.02em; }}
.pill {{ display:inline-block; padding:2px var(--s2); border-radius:999px; font-size: var(--small); border:1px solid var(--line); background:var(--card); }}
.headline {{ font-family: Georgia, "Times New Roman", serif; font-size: var(--h1); line-height:1.15; font-weight:700; margin: var(--s1) 0 var(--s1) 0; }}
.subhead {{ color: var(--muted); font-size: var(--body); margin: 0 0 var(--s1) 0; }}
.tiles {{ display:grid; grid-template-columns:repeat(4,1fr); gap: var(--s2); margin-bottom: var(--s1); }}
.tile {{ background: var(--card); border:1px solid var(--line); border-radius:12px; padding: 12px var(--s2); }}
.tile .v {{ font-family: Georgia, serif; font-size: var(--h2); font-weight:700; line-height:1.1; color: var(--accent); }}
.tile .l {{ font-size: var(--body); line-height:1.3; margin-top: 4px; }}
.tile .s {{ font-size: var(--small); color: var(--muted); margin-top: 4px; }}
.maptitle {{ font-family: Georgia, serif; font-size: var(--body); font-weight:700; margin: 0; padding-bottom: var(--s1); line-height:1.3; }}
.maptitle.v {{ color: var(--accent); }}
.mapnums {{ font-size: var(--small); color: var(--muted); margin: 0; text-align:center; }}
svg.map {{ width:100%; height:auto; max-height: 336px; margin: 0 auto; display:block; border-radius:12px; border:1px solid var(--line); }}
.legend {{ display:flex; gap: var(--s2); align-items:center; font-size: var(--small); color: var(--muted); flex-wrap:wrap; margin: var(--s1) 0; }}
.sw {{ display:inline-block; width:12px; height:12px; border-radius:3px; vertical-align:middle; margin-right:4px; border:1px solid #0002; }}
.fine {{ color: var(--muted); font-size: var(--small); margin: var(--s1) 0; }}
.sec {{ margin-top: var(--s8); }}
.sec h2 {{ font-family: Georgia, serif !important; font-size: var(--h2); font-weight:700; margin: 0 0 var(--s1) 0; padding:0; }}
.sec p.lede {{ color: var(--muted); font-size: var(--body); margin: 0 0 var(--s3) 0; max-width: 760px; }}
.honest {{ border-left:4px solid var(--accent); padding: 4px var(--s2); margin: 0 0 var(--s2) 0; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background: var(--card); border:1px solid var(--line) !important; border-radius:12px; }}
.note {{ background:#F1ECFB; border:1px solid #D9CFF5; border-radius:8px; padding: var(--s1) var(--s2); font-size: var(--small); margin: var(--s1) 0; }}
.note.warn {{ background:#FFF3E0; border-color:#F2C98A; }}
.flip {{ font-size: var(--small); line-height:1.4; padding: var(--s1) 0; border-bottom:1px solid var(--line); }}
.flipcol h4 {{ font-family:Georgia,serif; margin: var(--s1) 0; font-size: var(--body); }}
.tip {{ border-bottom:1px dotted var(--muted); cursor:help; }}
.badge {{ display:inline-block; padding:2px var(--s1); border-radius:6px; font-size: var(--small); background:#EFE9DD; margin-right: var(--s1); }}
.badge.v {{ background:#E9E2FB; color:#3B2A92; }}
table.t {{ border-collapse:collapse; width:100%; }}
table.t th {{ text-align:left; color: var(--muted); font-weight:600; border-bottom:2px solid var(--ink); padding: var(--s1); font-size: var(--small); }}
table.t td {{ border-bottom:1px solid var(--line); padding: var(--s1); vertical-align:top; font-size: var(--small); }}
code, pre {{ font-size: var(--small) !important; background:#F4EFE5 !important; }}
/* controls bar */
.stApp [data-testid="stSlider"] [role="slider"] {{ background: var(--accent); }}
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{ display:none !important; }}
[data-testid="stCaptionContainer"], .stCaption {{ font-size: var(--small); }}
iframe, canvas {{ max-width:100%; }}
@media (max-width: 700px) {{
  :root {{ --h1: 28px; --h2: 28px; }}
  .block-container {{ padding-left: var(--s2); padding-right: var(--s2); }}
  .tiles {{ grid-template-columns:repeat(2,1fr); gap: var(--s1); }}
  .tile {{ padding: var(--s1) 12px; }}
  .tile .l {{ font-size: var(--small); }}
  .sec {{ margin-top: var(--s6); }}
}}
</style>
"""
