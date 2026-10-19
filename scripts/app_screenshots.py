"""Dev tool: screenshot the running app at 1440x900 and run page checks. Needs `pip install -r requirements-dev.txt`.

Start the app first:  PYTHONPATH=src streamlit run src/metric_grid/app/streamlit_app.py --server.port 8765
Then:                 python scripts/app_screenshots.py
"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://localhost:8765/"
STATES = {  # file -> (query string, text that proves the state rendered)
    "app_default": ("", "Same"),
    "app_alpha1": ("?alpha=1", "Same"),
    "app_alpha0": ("?alpha=0", "Same"),
    "app_cap_on": ("?cap=1", "No county takes more than"),
    "app_zone_detail": ("?zone=23", "H_human"),
}
BANNED = ["privacy-preserving", "federated learning", "AI optimizer", "conventional plan", "circuit", "feeder", "service area",
          "neighborhood demand", "least harm", "outage plan"]
REQUIRED_SENTENCE = ("The Elliott regional event anchors this scenario. NC-08 load and required reduction are modeled "
                     "district-scale estimates, not observed utility circuit values.")


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
            page.wait_for_selector(".headline", timeout=60000)
            page.get_by_text(proof).first.wait_for(timeout=60000)
            page.wait_for_timeout(5000)  # let the deck.gl canvases draw
            sw = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            text = page.inner_text("body")
            text_all = page.evaluate("document.body.textContent")
            hits = [w for w in BANNED if re.search(re.escape(w), text_all.replace(REQUIRED_SENTENCE, ""), re.I)]
            # Streamlit scrolls an inner container, so grow the viewport to the content height for a full-page shot
            height = page.evaluate("document.querySelector('[data-testid=stMain]').scrollHeight")
            page.set_viewport_size({"width": 1440, "height": int(height)})
            page.wait_for_timeout(4000)
            page.screenshot(path=str(out / f"{name}.png"))
            if name == "app_default":  # the demand panel, cropped from the full-height page
                box = page.get_by_text("Why forecasts aren't enough").first.bounding_box()
                page.screenshot(path=str(out / "app_demand_panel.png"),
                                clip={"x": 60, "y": box["y"] - 28, "width": 1320, "height": 560})
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
        browser.close()
    print(json.dumps(report, indent=1))
    print("PROBLEMS:", problems or "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
