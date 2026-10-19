"""Editorial look: warm off-white, dark ink, serif headline, one violet accent. No external fonts or assets (offline)."""
INK, BG, ACCENT, MUTED = "#1C1A24", "#FAF7F2", "#5B3FD6", "#6B6678"

CSS = f"""
<style>
:root {{ --ink:{INK}; --bg:{BG}; --accent:{ACCENT}; --muted:{MUTED}; --line:#E3DCCF; --card:#FFFDF9; }}
.stApp {{ background: var(--bg); color: var(--ink); }}
header[data-testid="stHeader"], footer, #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"] {{ display:none !important; }}
.block-container {{ max-width: 1360px; padding: 1.1rem 2rem 3rem 2rem; }}
html, body, [class*="css"], .stMarkdown, p, li, label, span, div {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }}
h1, h2, h3, .serif {{ font-family: Georgia, "Times New Roman", serif !important; color: var(--ink); letter-spacing: -0.01em; }}
.topbar {{ display:flex; align-items:center; gap:.7rem; padding-bottom:.6rem; border-bottom:1px solid var(--line); flex-wrap:wrap; }}
.brand {{ font-family: Georgia, serif; font-size:1.35rem; font-weight:700; margin-right:.4rem; }}
.pill {{ display:inline-block; padding:.18rem .7rem; border-radius:999px; font-size:.78rem; border:1px solid var(--line); background:var(--card); color:var(--ink); }}
.pill.accent {{ background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }}
.tagline {{ color:var(--muted); font-size:.85rem; margin:.45rem 0 0 0; }}
.eyebrow {{ color:var(--accent); text-transform:uppercase; letter-spacing:.09em; font-size:.78rem; font-weight:700; margin:1.4rem 0 .3rem 0; }}
.headline {{ font-family: Georgia, "Times New Roman", serif; font-size:2.55rem; line-height:1.12; font-weight:700; margin:0 0 .6rem 0; }}
.honest {{ font-size:1.05rem; line-height:1.45; border-left:4px solid var(--accent); padding:.15rem 0 .15rem .9rem; margin:.2rem 0 .7rem 0; }}
.scaling {{ color:var(--muted); font-size:.82rem; margin:.2rem 0; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background: var(--card); border:1px solid var(--line) !important; border-radius:14px; }}
.maptitle {{ font-family: Georgia, serif; font-size:1.25rem; font-weight:700; margin:.2rem 0 .1rem 0; }}
.mapsub {{ color:var(--muted); font-size:.82rem; margin-bottom:.3rem; }}
.metric {{ border-top:2px solid var(--ink); padding:.35rem 0 .2rem 0; }}
.metric .v {{ font-family: Georgia, serif; font-size:1.45rem; font-weight:700; line-height:1.1; }}
.metric .l {{ color:var(--muted); font-size:.74rem; text-transform:uppercase; letter-spacing:.05em; }}
.metric .s {{ color:var(--muted); font-size:.74rem; }}
.note {{ background:#F1ECFB; border:1px solid #D9CFF5; border-radius:10px; padding:.5rem .8rem; font-size:.86rem; margin:.4rem 0; }}
.legend {{ display:flex; gap:1rem; align-items:center; font-size:.76rem; color:var(--muted); flex-wrap:wrap; margin:.2rem 0 .6rem 0; }}
.sw {{ display:inline-block; width:.95rem; height:.95rem; border-radius:3px; vertical-align:middle; margin-right:.3rem; border:1px solid #0002; }}
.flip {{ font-size:.86rem; line-height:1.35; padding:.35rem 0; border-bottom:1px solid var(--line); }}
.flipcol h4 {{ font-family:Georgia,serif; margin:.2rem 0 .4rem 0; font-size:1.05rem; }}
.tip {{ border-bottom:1px dotted var(--muted); cursor:help; }}
.note.warn {{ background:#FFF3E0; border-color:#F2C98A; }}
.cap {{ color:var(--muted); font-size:.84rem; margin:.3rem 0; }}
.badge {{ display:inline-block; padding:.12rem .55rem; border-radius:6px; font-size:.72rem; background:#EFE9DD; margin-right:.3rem; }}
.badge.v {{ background:#E9E2FB; color:#3B2A92; }}
table.t {{ border-collapse:collapse; width:100%; font-size:.84rem; }}
table.t th {{ text-align:left; color:var(--muted); font-weight:600; border-bottom:2px solid var(--ink); padding:.3rem .4rem; font-size:.74rem; text-transform:uppercase; letter-spacing:.04em; }}
table.t td {{ border-bottom:1px solid var(--line); padding:.35rem .4rem; vertical-align:top; }}
code, pre {{ font-size:.82rem !important; background:#F4EFE5 !important; }}
.stApp [data-testid="stSlider"] [role="slider"] {{ background:var(--accent); }}
iframe, canvas {{ max-width:100%; }}
html, body {{ overflow-x:hidden; }}
</style>
"""
