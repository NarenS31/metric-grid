"""Submission audit: banned words, AI disclosure coverage, no typed model numbers in the UI, docs that quote the model stay true."""
import ast
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metric_grid import frozen
from metric_grid.app import provenance
from metric_grid.config import ROOT
from metric_grid.model import scenarios

BANNED = ["privacy-preserving", "federated learning", "AI optimizer", "conventional plan", "circuit", "feeder", "service area",
          "neighborhood demand", "least harm", "outage plan"]
# Files that must quote the banned list (or the original brief) are exempt from the word check.
EXEMPT_BANNED = {"docs/SPEC.md", "CLAUDE.md", "tests/test_app.py", "tests/test_audit.py", "scripts/app_screenshots.py"}
TEXT_SUFFIX = {".md", ".py", ".yaml", ".yml", ".toml", ".txt", ".ino", ".h", ".ini", ""}


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode == 0 and out.stdout.strip():
        return out.stdout.split()
    return [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and ".venv" not in p.parts and ".git" not in p.parts]


def test_no_banned_words_in_any_tracked_text_file():
    hits = []
    for f in tracked():
        p = ROOT / f
        if f in EXEMPT_BANNED or p.suffix not in TEXT_SUFFIX or not p.is_file():
            continue
        text = p.read_text(errors="ignore").replace(provenance.DISTRICT_SENTENCE, "")  # rule-4 sentence is required verbatim
        text = text.replace("not observed utility circuit values", "")  # the same phrase when a source file splits the sentence in two
        hits += [(f, w) for w in BANNED if re.search(re.escape(w), text, re.I)]
    assert not hits, hits


def test_ai_disclosure_lists_every_tracked_file():
    doc = (ROOT / "docs" / "AI_DISCLOSURE.md").read_text()
    skip = lambda f: f.startswith(("data/frozen/", "docs/figures/")) or f.endswith((".gitkeep", "__init__.py"))
    missing = [f for f in tracked() if not skip(f) and f not in doc]
    assert not missing, f"add these to docs/AI_DISCLOSURE.md: {missing}"
    for tool in ("Claude", "Claude Code", "Perplexity"):
        assert tool in doc
    assert "hardware testing in progress" in doc


NUM_ALLOW = {"0", "1", "2", "5", "10", "23", "0,", "2013", "2022", "65", "08", "861", "930"}  # label facts, deep-link example, dataset names


def test_app_strings_contain_no_typed_model_numbers():
    """Numbers shown on the page must be computed. Only label-style numbers (years, dataset names, alpha 0/1) may appear in literals."""
    bad = []
    for name in ("streamlit_app.py", "copy.py", "provenance.py", "data.py", "lookup.py"):
        tree = ast.parse((ROOT / "src" / "metric_grid" / "app" / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                txt = node.value
                if re.search(r"[:;]\s*[\d.]+(px|rem|em|%)|rgb|#[0-9A-Fa-f]{3,6}|grid-template|repeating|gap:|margin|font|border|padding|width|height", txt):
                    continue  # CSS / inline style
                for m in re.finditer(r"(?<![\w.:{])\d[\d,.]*%?(?![\w}:])", txt):
                    if m.group().rstrip("%") not in NUM_ALLOW and m.group() not in NUM_ALLOW:
                        bad.append((name, node.lineno, m.group()))
    assert not bad, bad


@pytest.fixture(scope="module")
def default_pair():
    rec = [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0.5 and not r["cap"]][0]
    return scenarios.record_to_pair(rec)


def test_readme_default_scenario_table_matches_the_model(default_pair):
    readme = (ROOT / "README.md").read_text()
    b, w = default_pair.baseline, default_pair.weighted
    for v in (f"{b.mw_shed:.1f}", f"{w.mw_shed:.1f}", f"{b.households:,.0f}", f"{w.households:,.0f}", f"{b.electric_heat_households:,.0f}",
              f"{w.electric_heat_households:,.0f}", f"{b.h_human:,.0f}", f"{w.h_human:,.0f}", f"${b.h_econ:,.0f}", f"${w.h_econ:,.0f}",
              f"{default_pair.band_lo_mw:.1f} and {default_pair.band_hi_mw:.1f} MW", f"+{w.households - b.households:,.0f}"):
        assert v in readme, v
    consts = frozen.load_constants()
    assert f"{consts['T_NC08_mw']:.1f} MW" in readme and f"{consts['n_protected']} zones, {consts['protected_load_mw'] / consts['D_NC08_mw']:.1%}" in readme
    union = scenarios.county_breakdown(_zh(), w).loc["Union County", "share_of_cut"]
    assert f"{union:.0%} of its cut in one low-vulnerability county (Union)" in readme


def _zh():
    from metric_grid.config import load_config
    from metric_grid.model import harm
    return harm.compute_harm(frozen.load_zones(), load_config(), frozen.load_constants()["kw_per_job"])


def test_shotlist_numbers_and_code_match_reality(default_pair):
    s = (ROOT / "docs" / "VIDEO_SHOTLIST.md").read_text()
    from metric_grid.app import copy
    assert copy.headline(default_pair) in s
    assert f"cuts {default_pair.weighted.households - default_pair.baseline.households:,.0f} MORE households" in s
    import pandas as pd
    rows = pd.DataFrame(frozen.load_sensitivity()["rows"])
    assert f"{int((rows['human_change_pct'] < 0).sum())} of {len(rows)} settings beat the baseline on human harm" in s
    assert f"I tried {len(rows)} settings" in s and "(zone 8 is open)" in s
    # every excerpt line on the shot list exists in optimizer.py, and block 1 is contiguous there
    opt = (ROOT / "src/metric_grid/model/optimizer.py").read_text()
    blocks = re.findall(r"```python\n(.*?)\n```", s, re.S)
    assert len(blocks) == 2
    flat = textwrap.dedent(opt)
    for blk in blocks:
        lines = [l.rstrip() for l in blk.split("\n")]
        assert 1 <= len(lines) <= 12
        for l in lines:
            assert l in opt, l
    first = blocks[0].split("\n")
    start = [i for i, l in enumerate(opt.splitlines()) if l.strip() == first[0].strip()][0]
    assert [l.strip() for l in opt.splitlines()[start:start + len(first)]] == [l.strip() for l in first]
    m = re.search(r"lines (\d+)-(\d+) \(8 lines\)", s)
    assert opt.splitlines()[int(m.group(1)) - 1].strip() == first[0].strip()
    # the one test named on the shot list exists and uses the real zones
    assert "real_both_plans_in_same_band" in (ROOT / "tests" / "test_harm_optimizer.py").read_text()


def test_makefile_has_every_required_target():
    mk = (ROOT / "Makefile").read_text()
    for t in ("data:", "freeze:", "test:", "app:", "demo:", "api:"):
        assert re.search(rf"^{t}", mk, re.M), t
    assert "TODO" not in mk.split("api:")[0]  # data, freeze, test, app and demo are real targets


def test_reviews_template_has_three_reviewer_types_and_no_endorsement_claim():
    r = (ROOT / "docs" / "REVIEWS.md").read_text()
    for kind in ("non-expert", "programmer", "policy or energy"):
        assert kind in r
    assert "Never claim endorsement" in r and "endorse" not in r.replace("Never claim endorsement", "").lower().replace("endorsement.", "")
