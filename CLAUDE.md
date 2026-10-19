# METRIC-Grid: project memory (full locked spec: docs/SPEC.md)

**Purpose:** helps emergency planners and community stakeholders compare how load-only and vulnerability-aware outage scenarios could distribute risk across NC's 8th Congressional District (NC-08). Congressional App Challenge entry, due 12:00 pm EDT Oct 26, 2026. Author is a high-school student: less scope, more proof, explainable code.

**Primary user:** a county emergency planner who wants to know whether two technically equal scenarios could burden vulnerable communities very differently, and leaves with zones to prioritize for outreach, warming centers, backup power. Not utility operators, not residents.

**Anchor:** Winter Storm Elliott, Dec 24 2022, the hour ending 07:00 (06:00-07:00; EIA labels hours by their end) (DEC shed 1,000 MW from 06:14; DEP shed up to 961 MW; sources in docs/DATA_SOURCES.md). Planning simulator, not a dispatcher, not Duke's method.

## 10 non-negotiable rules
1. Every UI number traces to a named source in the provenance drawer; allocated/inferred values get an "estimated" or "modeled" badge.
2. Voronoi cells = "synthetic analysis zones generated around public infrastructure points; not actual feeder boundaries." If no substation data, zones are census tracts, labeled so.
3. Baseline = "load-only baseline" with a defined objective; never described as what Duke does.
4. District scaling first (amended 2026-10-18 for two utilities, DEC and DEP): `D_NC08 = sum_g D_g * W_NC08_in_g / W_g`, then `T_NC08 = sum_g D_NC08_g * r_g`. Never allocate BA demand or the regional reduction into NC-08 directly. UI must say: "The Elliott regional event anchors this scenario. NC-08 load and required reduction are modeled district-scale estimates, not observed utility circuit values."
5. Shared target band (amended 2026-10-18, replaces exact `T*`): both plans must cut between `T_NC08` and `T_NC08 + delta` (delta = 2% by default, widened to 5% if needed; UI says "both plans cut between X and Y MW"). Stage A (load-only baseline) minimizes MW cut, Stage B minimizes harm, ties: fewest zones then lowest zone_id. Infeasible request returns explanation + max feasible value, never a crash.
6. Critical facilities are hard exclusions (`x_i = 0`) at zone level; UI notes this may over-protect and facility data may be incomplete.
7. Never fabricate data. If a source fails: stop, state what failed and the fallback, document in docs/ASSUMPTIONS.md, then continue. No silent synthetic substitution.
8. App runs offline from `data/frozen/` after `make data`/`make freeze`. No runtime API calls.
9. No claims of predicting failures, sensing the grid, verifying zones, or controlling utility equipment. **Banned words:** "privacy-preserving," "federated learning," "AI optimizer," "conventional plan," "circuit," "feeder," "service area," "neighborhood demand," "least harm," "outage plan." (Banned list quoted in this file and docs/SPEC.md is exempt from the lint test; the exact district-scaling sentence in rule 4 is required.) **Use:** load-only baseline; synthetic analysis zone; estimated zone load; modeled district estimate; lowest modeled harm; planning scenario.
10. Keep docs/AI_DISCLOSURE.md current: every AI tool (Claude, Claude Code, Perplexity), per-file status (AI-scaffolded / AI-assisted / author-written) and what the author changed.

UI copy rules: every dollar figure is labeled "2013 dollars". Anywhere vulnerability or cost results are shown, state plainly how many households each plan cuts (the harm-weighted plan cuts MORE households by default; see the numbers in the app): use `scenarios.plain_summary`; never imply it cuts fewer people. The demo grid is pre-solved at `make freeze` (data/frozen/presolved.json). Planning-implications card: "Vulnerable zones most often cut when only megawatts count" = among unprotected zones with SVI >= 0.75 or electric-heat share >= 50% (config `priority_list`), ranked by the share of the 200 load-only plans that cut them, plus whether the vulnerability-aware plan cuts each (`sensitivity.priority_list`, in sensitivity.json); the plan set is not a uniform sample, so frequencies are indicative; never a switching recommendation. Optional county-share cap (default OFF, `optimizer.county_cap`) is a toggle and a sensitivity row.

Every map draws the NC-08 district outline (data/frozen/district.geojson). Amendments to docs/SPEC.md live in this file and docs/ASSUMPTIONS.md.

Run the app with `make app` (port 8765); screenshots with `scripts/app_screenshots.py` (needs requirements-dev.txt). If the app looks stale after a code change, kill whatever holds port 8765 first.

There is no single load-only baseline: the app compares the vulnerability-aware plan with a frozen set of 200 equivalent load-only plans (model/loadonly.py) and shows the typical one on the left map. Never present one load-only plan, or the size of a gap, as precise. Rule 3's "load-only baseline" now means this set (docs/ASSUMPTIONS.md, "Baseline plan instability and the load-only plan set").

## Stack
Python 3.11, Streamlit, GeoPandas, shapely, PuLP (CBC), pandas, numpy, PyYAML (runtime; maps are inline SVG, no WebGL); pytest, matplotlib, requests, Playwright (dev). requirements.txt = exactly the app's runtime imports, pinned; requirements-dev.txt = tests, figures, data refresh; requirements-node.txt = unused node packages. Make targets: data, freeze, test, app, demo, api. Ask before adding anything else.

## Layout
`config.yaml` (every constant, source-commented; state/district/BA/counties only here), `data/raw` (gitignored), `data/frozen` (committed, only runtime inputs), `src/metric_grid/{config.py, frozen.py, figures.py, ingest/, geometry/, model/, train/, app/}` (train/ = build-time demand-model training, uses scikit-learn), `tests/`, `docs/`. The optional hardware node is out of this submission (the firmware folder was deleted 2026-10-19; node packages are in requirements-node.txt and nothing imports them). Do not recreate placeholder files for it.

## Working style
One phase at a time; STOP for review at each phase and report verified / failed / needs decision. Update CHANGELOG.md and docs/AI_DISCLOSURE.md every step (same commit). Small functions with docstrings. Cap dead-data-source workarounds at ~20 min, then fall back and document. Don't overwrite existing files without looking first.
