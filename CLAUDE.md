# METRIC-Grid: project memory (full locked spec: docs/SPEC.md)

**Purpose:** helps emergency planners and community stakeholders compare how load-only and vulnerability-aware outage scenarios could distribute risk across NC's 8th Congressional District (NC-08). Congressional App Challenge entry, due 12:00 pm EDT Oct 26, 2026. Author is a high-school student: less scope, more proof, explainable code.

**Primary user:** a county emergency planner who wants to know whether two technically equal scenarios could burden vulnerable communities very differently, and leaves with zones to prioritize for outreach, warming centers, backup power. Not utility operators, not residents.

**Anchor:** Winter Storm Elliott, Dec 24 2022, 07:00 (DEC shed ~1,000 MW from 06:14). Planning simulator, not a dispatcher, not Duke's method.

## 10 non-negotiable rules
1. Every UI number traces to a named source in the provenance drawer; allocated/inferred values get an "estimated" or "modeled" badge.
2. Voronoi cells = "synthetic analysis zones generated around public infrastructure points; not actual feeder boundaries." If no substation data, zones are census tracts, labeled so.
3. Baseline = "load-only baseline" with a defined objective; never described as what Duke does.
4. District scaling first: `D_NC08 = D_DUK * W_NC08 / W_DUK`, then `T_NC08 = D_NC08 * r`. Never allocate DUK demand or the regional reduction into NC-08 directly. UI must say: "The Elliott regional event anchors this scenario. NC-08 load and required reduction are modeled district-scale estimates, not observed utility circuit values."
5. Equal feasible target: Stage A finds min feasible `T*` >= `T_NC08`; Stage B holds the weighted plan to exactly `T*`. Infeasible request returns explanation + max feasible value, never a crash.
6. Critical facilities are hard exclusions (`x_i = 0`) at zone level; UI notes this may over-protect and facility data may be incomplete.
7. Never fabricate data. If a source fails: stop, state what failed and the fallback, document in docs/ASSUMPTIONS.md, then continue. No silent synthetic substitution.
8. App runs offline from `data/frozen/` after `make data`/`make freeze`. No runtime API calls.
9. No claims of predicting failures, sensing the grid, verifying zones, or controlling utility equipment. **Banned words:** "privacy-preserving," "federated learning," "AI optimizer," "conventional plan," "circuit," "feeder," "service area," "neighborhood demand," "least harm," "outage plan." (Banned list quoted in this file and docs/SPEC.md is exempt from the lint test; the exact district-scaling sentence in rule 4 is required.) **Use:** load-only baseline; synthetic analysis zone; estimated zone load; modeled district estimate; lowest modeled harm; planning scenario.
10. Keep docs/AI_DISCLOSURE.md current: every AI tool (Claude, Claude Code, Perplexity), per-file status (AI-scaffolded / AI-assisted / author-written) and what the author changed.

## Stack
Python 3.11+, Streamlit, GeoPandas, shapely, scipy, PuLP (CBC), pandas, pyarrow, pydeck, pytest, requests, pyyaml. Node (later): FastAPI + SQLite, httpx, python-kasa, ESP32 Feather V2 firmware. Make targets: data, freeze, test, app, demo, api. Ask before adding anything else.

## Layout
`config.yaml` (every constant, source-commented; state/district/BA/counties only here), `data/raw` (gitignored), `data/frozen` (committed, only runtime inputs), `src/metric_grid/{config.py, ingest/, geometry/, model/, app/, nodes/}`, `tests/`, `docs/`, `firmware/`. Node code (server/, tools/, firmware/hw_test, real metric_node) is the author's own, arriving later: do not rewrite or move it; spec Phase 5 is superseded by it. firmware/bus_check*, i2c_scan are throwaway hardware tests: leave alone.

## Working style
One phase at a time; STOP for review at each phase and report verified / failed / needs decision. Update CHANGELOG.md and docs/AI_DISCLOSURE.md every step (same commit). Small functions with docstrings. Cap dead-data-source workarounds at ~20 min, then fall back and document. Don't overwrite existing files without looking first.
