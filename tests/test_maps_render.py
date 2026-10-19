"""Browser test: both maps actually draw (not blank boxes) in Chromium and WebKit, with no external requests.

Starts the real app on a free port and screenshots each map. A flat single-colour image fails. Skipped if Playwright or the browser
builds are not installed (dev-only: requirements-dev.txt, then `python -m playwright install chromium webkit`).
"""
import io
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
from PIL import Image, ImageStat  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "src/metric_grid/app/streamlit_app.py"), "--server.port", str(port),
                             "--server.headless", "true", "--browser.gatherUsageStats", "false"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.skip("app did not start")
    yield f"http://127.0.0.1:{port}/"
    proc.kill()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("size", [(1440, 900), (390, 844)])
def test_both_maps_draw_real_content(server, engine, size):
    with pw.sync_playwright() as p:
        try:
            browser = getattr(p, engine).launch()
        except Exception as exc:  # browser build not installed
            pytest.skip(f"{engine} not installed: {exc}")
        page = browser.new_page(viewport={"width": size[0], "height": size[1]})
        external = []
        page.on("request", lambda rq: external.append(rq.url) if not rq.url.startswith(("http://127.0.0.1", "data:", "blob:")) else None)
        page.goto(server)
        page.wait_for_selector("svg.map", timeout=60000)
        maps = page.locator("svg.map")
        assert maps.count() == 2
        for i in range(2):
            m = maps.nth(i)
            m.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            img = Image.open(io.BytesIO(m.screenshot())).convert("RGB")
            stat = ImageStat.Stat(img)
            colors = len(img.getcolors(maxcolors=1_000_000) or [])
            assert max(stat.stddev) > 8 and colors > 20, f"{engine} map {i} looks blank (stddev {stat.stddev}, {colors} colours)"
            assert m.locator("path").count() > 180  # 183 zones plus hatch and outline
        assert page.evaluate("document.documentElement.scrollWidth") <= size[0]  # no horizontal scroll
        browser.close()
        assert not external, external
