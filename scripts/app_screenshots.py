"""Dev tool: screenshot the running app at 1440x900 and run page checks. Needs `pip install -r requirements-dev.txt`.

Start the app first:  PYTHONPATH=src streamlit run src/metric_grid/app/streamlit_app.py --server.port 8765
Then:                 python scripts/app_screenshots.py
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://localhost:8765/"
STATES = {  # file -> (query string, text that proves the state rendered)
    "app_default": ("", "Same"),
    "app_alpha1": ("?alpha=1", "Same"),
    "app_alpha0": ("?alpha=0", "Same"),
    "app_cap_on": ("?cap=1", "No county takes more than"),
    "app_zone_detail": ("?zone=23", "at-risk score"),
}
BANNED = ["privacy-preserving", "federated learning", "AI optimizer", "conventional plan", "circuit", "feeder", "service area",
          "neighborhood demand", "least harm", "outage plan"]
REQUIRED_SENTENCE = ("The Elliott regional event anchors this scenario. NC-08 load and required reduction are modeled "
                     "district-scale estimates, not observed utility circuit values.")


LIMIT_BYTES = 300_000


def compress_png(path: Path, limit: int = LIMIT_BYTES) -> int:
    """Shrink a screenshot to under `limit` bytes: palette-quantize (fewer colors until it fits), then scale down if still too big.
    UI screenshots have flat colors, so this loses almost nothing visible. Returns the final size in bytes."""
    img = Image.open(path).convert("RGB")
    scale = 1.0
    while True:
        work = img if scale == 1.0 else img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        for colors in (128, 96, 64, 48, 32):
            q = work.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
            q.save(path, optimize=True)
            if path.stat().st_size <= limit:
                return path.stat().st_size
        scale *= 0.85
        if scale < 0.4:
            return path.stat().st_size


def main() -> int:
    out = ROOT / "docs" / "figures"
    problems, report = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, (query, proof) in STATES.items():
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            external, console_errors = set(), []
            page.on("request", lambda rq: external.add(rq.url.split("/")[2]) if not rq.url.startswith(("http://localhost", "data:", "blob:")) else None)
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.goto(BASE + query, wait_until="domcontentloaded")
            page.wait_for_selector(".title", timeout=60000)
            page.get_by_text(proof).first.wait_for(timeout=60000)
            page.wait_for_timeout(3000)  # let the page settle
            sw = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            text = page.inner_text("body")
            text_all = page.evaluate("document.body.textContent")
            hits = [w for w in BANNED if re.search(re.escape(w), text_all.replace(REQUIRED_SENTENCE, ""), re.I)]
            # Streamlit scrolls an inner container, so grow the viewport to the content height for a full-page shot
            height = page.evaluate("document.querySelector('[data-testid=stMain]').scrollHeight")
            page.set_viewport_size({"width": 1440, "height": int(height) + 500})
            page.wait_for_timeout(4000)
            # Crop to the part of the page that tells the story, at full width, so the PNG stays legible under the size limit:
            # the top ~1,900 px (headline, maps, distribution strips) for every state except the zone detail (the cards row).
            if name == "app_zone_detail":
                box = page.get_by_text("Look up a zone", exact=True).first.bounding_box()
                clip = {"x": 0, "y": max(box["y"] - 40, 0), "width": 1440, "height": 780}
            else:
                clip = {"x": 0, "y": 0, "width": 1440, "height": 1900}
            page.screenshot(path=str(out / f"{name}.png"), clip=clip)
            if name == "app_default":  # the demand panel, cropped from the full-height page
                box = page.get_by_text("Why forecasts aren't enough").first.bounding_box()
                page.screenshot(path=str(out / "app_demand_panel.png"),
                                clip={"x": 60, "y": box["y"] - 28, "width": 1320, "height": 640})
            report[name] = {"scrollWidth/clientWidth": sw, "external_hosts": sorted(external), "console_errors": console_errors[:3],
                            "banned_words": hits, "has_required_sentence": REQUIRED_SENTENCE in re.sub(r"\s+", " ", text_all),
                            "canvases": page.locator("canvas").count()}
            if sw[0] > sw[1] + 1:
                problems.append(f"{name}: horizontal scroll {sw}")
            if hits:
                problems.append(f"{name}: banned words {hits}")
            if external:
                problems.append(f"{name}: external requests {sorted(external)}")
            page.close()
        # v2 page shots: first screen at 1440x900, the whole page at 1440, the first screen at a 390 px phone
        for fname, (w, h), full in (("app_v2_first_screen.png", (1440, 900), False), ("app_v2_full_page.png", (1440, 900), True),
                                    ("app_v2_phone_first_screen.png", (390, 844), False)):
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(BASE, wait_until="domcontentloaded")
            page.wait_for_selector("svg.map", timeout=60000)
            page.wait_for_timeout(3000)
            if full:
                height = page.evaluate("document.querySelector('[data-testid=stMain]').scrollHeight")
                page.set_viewport_size({"width": w, "height": int(height) + 50})
                page.wait_for_timeout(3000)
            page.screenshot(path=str(out / fname))
            sw = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            if sw[0] > sw[1] + 1:
                problems.append(f"{fname}: horizontal scroll {sw}")
            page.close()
        browser.close()
    for png in sorted(out.glob("app_*.png")):
        size = compress_png(png)
        report.setdefault("compressed_bytes", {})[png.name] = size
    print(json.dumps(report, indent=1))
    print("PROBLEMS:", problems or "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
