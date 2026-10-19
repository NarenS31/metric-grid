"""Dev tool: WCAG 2.1 contrast ratios for the colour pairs the page actually uses (palette from app/theme.py). Exit 1 if any pair fails."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metric_grid.app import maps, theme  # noqa: E402


def lum(hexc: str) -> float:
    c = [int(hexc.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hexof(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(x) for x in rgb)


T, M, B, S, E = theme.TEXT, theme.MUTED, theme.BG, theme.SURFACE, theme.ELEVATED
HOVER = "#14203A"
LOW, HIGH = hexof(maps.KEPT_LIGHT), hexof(maps.KEPT_DARK)
PAIRS = [  # (description, foreground, background, minimum)
    ("body text on page", T, B, 4.5), ("body text on card", T, S, 4.5), ("body text on elevated", T, E, 4.5),
    ("muted text on page (deck, map numbers, legend, footnote)", M, B, 4.5), ("muted text on card (tile sub-lines, table headers, notes)", M, S, 4.5),
    ("muted text on elevated (badges, code)", M, E, 4.5), ("muted text on table hover row", M, HOVER, 4.5), ("body text on table hover row", T, HOVER, 4.5),
    ("tile label (text) on card", T, S, 4.5), ("tile number, good (teal) on card", theme.TEAL, S, 4.5), ("tile number, attention (amber) on card", theme.AMBER, S, 4.5),
    ("source kind (teal) on page", theme.TEAL, B, 4.5), ("link / accent (blue) on page", theme.BLUE, B, 4.5), ("link / accent (blue) on sidebar", theme.BLUE, S, 4.5),
    ("muted nav text on sidebar", M, S, 4.5), ("nav hover text on elevated", T, E, 4.5), ("blue badge text on elevated", theme.BLUE, E, 4.5),
    ("chart axis labels (muted) on page", M, B, 4.5), ("chart axis labels (muted) on card", M, S, 4.5),
    ("map: cut colour vs lightest kept-on zone", maps.CUT_COLOR, LOW, 3.0), ("map: cut colour vs darkest kept-on zone", maps.CUT_COLOR, HIGH, 3.0),
    ("map: cut colour vs map background", maps.CUT_COLOR, S, 3.0), ("map: kept-on (high SVI) vs map background", HIGH, S, 3.0),
    ("map: kept-on (low SVI) vs map background", LOW, S, 1.0), ("map: district outline (teal) vs map background", theme.TEAL, S, 3.0),
    ("strip: each plan dot vs card", theme.DOTS, S, 3.0), ("strip: vulnerability-aware circle vs card", theme.VULN_AWARE, S, 3.0),
    ("strip: typical plan diamond vs card", theme.MW_ONLY, S, 3.0), ("control border (segmented control, toggle) vs page", "#5F7394", B, 3.0),
    ("focus ring (blue) vs page", theme.BLUE, B, 3.0),
]


def main() -> int:
    bad = 0
    for desc, fg, bg, need in PAIRS:
        r = ratio(fg, bg)
        ok = r >= need
        bad += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {r:5.2f}:1 (need {need})  {desc}  [{fg} on {bg}]")
    print("FAILURES:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
