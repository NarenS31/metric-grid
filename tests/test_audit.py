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


NUM_ALLOW = {"0", "1", "2", "5", "10", "23", "0,", "2013", "2022", "65", "08", "08.", "861", "930"}  # label facts, deep-link example, dataset names


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
    assert "Same power cut. Different people in the dark." in s
    assert f"{default_pair.baseline.electric_heat_households - default_pair.weighted.electric_heat_households:,.0f} fewer electric-heat homes" in s
    assert f"cuts {default_pair.weighted.households - default_pair.baseline.households:,.0f} MORE households" in s
    import pandas as pd
    rows = pd.DataFrame(frozen.load_sensitivity()["rows"])
    assert f"{int((rows['human_change_pct'] < 0).sum())} of {len(rows)} settings beat the typical plan on human harm" in s
    top = frozen.load_sensitivity()["priority_list"][0]["zone_id"]
    assert f"I tried {len(rows)} settings" in s and f"(zone {top} is open)" in s
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


# ---------------- housekeeping decisions (2026-10-19) ----------------

def _runtime_third_party_imports() -> set[str]:
    out = set()
    files = list((ROOT / "src/metric_grid/app").glob("*.py")) + list((ROOT / "src/metric_grid/model").glob("*.py")) + [
        ROOT / "src/metric_grid/frozen.py", ROOT / "src/metric_grid/config.py"]
    for f in files:
        for n in ast.walk(ast.parse(f.read_text())):
            mods = [a.name.split(".")[0] for a in n.names] if isinstance(n, ast.Import) else (
                [n.module.split(".")[0]] if isinstance(n, ast.ImportFrom) and n.module and n.level == 0 else [])
            out |= {m for m in mods if m not in sys.stdlib_module_names and m != "metric_grid"}
    return out


def _requirement_names(path: str) -> list[str]:
    lines = [l.split("#")[0].strip() for l in (ROOT / path).read_text().splitlines()]
    return [l for l in lines if l and not l.startswith("-r")]


def test_requirements_txt_is_exactly_the_runtime_imports_and_pinned():
    reqs = _requirement_names("requirements.txt")
    assert all(re.fullmatch(r"[A-Za-z0-9_.\-]+==[0-9][A-Za-z0-9_.]*", r) for r in reqs), reqs
    names = {r.split("==")[0].lower().replace("pyyaml", "yaml") for r in reqs}
    names = {"PIL" if n == "pillow" else n for n in names}
    assert names == _runtime_third_party_imports()
    for unused in ("scipy", "pyarrow", "fastapi", "uvicorn", "httpx", "python-kasa", "pytest", "matplotlib", "requests", "playwright"):
        assert unused not in names


def test_dev_and_node_requirements_split():
    dev = {r.split("==")[0] for r in _requirement_names("requirements-dev.txt")}
    node = {r.split("==")[0] for r in _requirement_names("requirements-node.txt")}
    assert {"pytest", "matplotlib", "requests", "playwright"} <= dev
    assert node == {"fastapi", "uvicorn", "httpx", "python-kasa"} and "scipy" not in dev and "pyarrow" not in dev
    assert all("==" in r for r in _requirement_names("requirements-dev.txt") + _requirement_names("requirements-node.txt"))


def test_firmware_folder_removed_and_readme_notes_the_prototype():
    assert not (ROOT / "firmware").exists() and not any(f.startswith("firmware/") for f in tracked())
    readme = (ROOT / "README.md").read_text()
    assert "Optional hardware prototype (ESP32 outage + indoor temperature logger) is in progress and not part of this submission." in readme


def test_readme_notes_the_seven_clean_clone_skips():
    readme = (ROOT / "README.md").read_text()
    assert "skips 7" in readme and "run `make data` first" in readme


def test_no_ncuc_citation_and_prior_work_entries_are_verified_ones():
    readme = (ROOT / "README.md").read_text()
    assert "NCUC" not in readme and "M-100" not in readme
    for title in ("The inequitable distribution of power interruptions during the 2021 Texas winter storm Uri",
                  "Impact of power outages depends on who loses it: Equity-informed grid resilience planning via stochastic optimization",
                  "Equity-aware Load Shedding Optimization", "Sharing the Load: Considering Fairness in De-energization Scheduling",
                  "Equitable Networked Microgrid Topology Reconfiguration for Wildfire Risk Mitigation",
                  "Machine Learning for Fairness-Aware Load Shedding", "Equitably allocating wildfire resilience investments for power grids"):
        assert title in readme, title
    for ref in ("10.1088/2634-4505/acd4e7", "10.1016/j.seps.2024.102036", "2406.17877", "2204.06543", "2402.04444", "2407.18989", "2404.11520"):
        assert ref in readme, ref


def test_spec_has_amendments_table_with_every_required_change():
    spec = (ROOT / "docs" / "SPEC.md").read_text()
    head = spec.split("You are building")[0]
    assert head.startswith("## Spec amendments")
    for needle in ("Two utilities", "Shared target band", "census tracts", "county-share cap", "hospitals, nursing homes and water treatment",
                   "pre-solved at `make freeze`", "four stops only"):
        assert needle in head, needle
    assert len(re.findall(r"\| 2026-10-\d\d \|", head)) >= 6  # each row dated


def test_readme_demand_numbers_match_the_panel_file():
    readme = (ROOT / "README.md").read_text()
    p = frozen.load_demand_panel()
    e = p["elliott"]
    for v in (f"{p['typical_mape_pct']:.1f}%", f"{abs(e['gap_pct']):.1f}%", f"{e['predicted_mw']:,.0f} MW predicted", f"{e['actual_mw']:,.0f} MW actual"):
        assert v in readme, v


def test_hour_ending_wording_is_used_wherever_the_reference_hour_is_named():
    """After the 2026-10-19 correction the reference hour is "the hour ending 07:00 (06:00-07:00)"; no bare 'demand at 07:00'."""
    import re
    for f in ("README.md", "docs/VIDEO_SHOTLIST.md", "config.yaml", "CLAUDE.md"):
        text = (ROOT / f).read_text()
        assert not re.search(r"(?i)demand at 07:00|at 07:00 EST|07:00 reference hour", text), f
    assert "hour ending 07:00" in (ROOT / "README.md").read_text() + (ROOT / "docs/VIDEO_SHOTLIST.md").read_text()
    c = frozen.load_constants()
    assert "hour ending 07:00" in c["r_definition"] and "hour ending 07:00" in c["scenario"]["name"]


# ---------------- load-only plan set commitments (2026-10-19) ----------------

def test_readme_states_the_plan_set_and_its_range_from_the_model():
    readme = (ROOT / "README.md").read_text()
    rec = [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0.5 and not r["cap"]][0]
    d = rec["loadonly"]
    e = d["electric_heat_households"]
    assert f"{d['n']} equivalent load-only plans" in readme and "typical load-only plan" in readme
    assert f"{e['min']:,.0f} to {e['max']:,.0f}" in readme
    assert f"MORE total households ({rec['weighted']['households'] - rec['baseline']['households']:+,.0f} vs the typical plan, and more than {d['households']['n_plans_fewer']} of {d['n']} plans)" in readme


def test_docs_describe_the_plan_set_and_the_spec_row_exists():
    a = (ROOT / "docs" / "ASSUMPTIONS.md").read_text()
    assert "## Baseline plan instability and the load-only plan set" in a and "fixed seed 20261019" in a
    assert "closest to the median on all four displayed measures" in a and "NOT a uniform sample" in a
    spec = (ROOT / "docs" / "SPEC.md").read_text().split("You are building")[0]
    assert "set of 200 equivalent load-only plans" in spec
    assert "no single baseline" in (ROOT / "CLAUDE.md").read_text().lower() or "no single load-only baseline" in (ROOT / "CLAUDE.md").read_text()


def test_app_screenshots_are_compressed():
    shots = sorted((ROOT / "docs" / "figures").glob("app_*.png"))
    assert len(shots) >= 6
    for p in shots:
        assert p.stat().st_size < 300_000, (p.name, p.stat().st_size)


def test_loadonly_plans_file_is_present_and_small_enough_to_commit():
    f = ROOT / "data" / "frozen" / "loadonly_plans.json"
    assert f.exists() and f.stat().st_size < 1_000_000


def test_shotlist_names_the_frequency_priority_card():
    text = (ROOT / "docs" / "VIDEO_SHOTLIST.md").read_text()
    assert "Vulnerable zones most often cut when only megawatts count" in text
    assert "Where to plan first" not in text


def test_one_optimum_statement_appears_exactly_once():
    text = (ROOT / "docs" / "ASSUMPTIONS.md").read_text()
    assert text.count("no distribution of equivalent vulnerability-aware plans was generated") == 1
