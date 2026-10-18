# METRIC-Grid

METRIC-Grid helps emergency planners and community stakeholders compare how load-only and vulnerability-aware outage scenarios could distribute risk across North Carolina's 8th Congressional District (NC-08).

Congressional App Challenge submission (due 12:00 pm EDT, October 26, 2026).

## What it is

When a utility can't meet demand it sheds load by opening breakers at substations. On December 24, 2022 (Winter Storm Elliott), Duke Energy Carolinas began shedding at 6:14 a.m. and shed about 1,000 MW; rotating outages across the Carolinas affected roughly 500,000 customers. Publicly described procedures protect critical facilities but publish no community-vulnerability layer. METRIC-Grid takes the observed regional demand curve from that morning (EIA-930), public census vulnerability data, and published interruption-cost figures, and solves two plans held to the same target: a load-only baseline and a harm-weighted plan. It shows them side by side on a map of synthetic analysis zones with every assumption exposed. An optional single ESP32 node demonstrates a measurement path (watts, indoor temperature, wall-power timestamps). It is a planning simulator, not an operational dispatcher and not Duke's method, and the app says so.

**Primary user:** a county emergency planner who wants to know whether two technically equal scenarios could impose very different consequences on vulnerable communities, and leaves with a short list of zones to prioritize for outreach, warming centers, and backup power.

**Not for:** utility operators (would need private feeder data) or residents (no household prediction).

## Rules the project holds itself to

1. Every number in the UI traces to a named source in a provenance drawer; allocated or inferred values carry an "estimated" or "modeled" badge.
2. Zones are "synthetic analysis zones generated around public infrastructure points; not actual feeder boundaries." If substation data is unavailable, zones are census tracts, labeled as such.
3. The baseline is the "load-only baseline" with a defined objective. It is not a description of what Duke does.
4. District scaling comes first: `D_NC08 = D_DUK * W_NC08 / W_DUK_territory`, then `T_NC08 = D_NC08 * r`. Both are modeled district estimates. *The Elliott regional event anchors this scenario. NC-08 load and required reduction are modeled district-scale estimates, not observed utility circuit values.*
5. Equal feasible target: Stage A finds the minimum feasible reduction `T*` ≥ `T_NC08`; Stage B holds the weighted plan to exactly `T*`. Infeasible requests produce an explanation with the maximum feasible value.
6. Critical facilities are hard exclusions (`x_i = 0`) at zone level. This may protect more modeled load than necessary, and public facility datasets may be incomplete.
7. No fabricated data. If a source fails, the failure and fallback are documented in `docs/ASSUMPTIONS.md` before continuing.
8. After `make data` and `make freeze`, the app runs fully offline from `data/frozen/`.
9. No claims of predicting failures, sensing the grid, verifying zones, or controlling utility equipment. A vocabulary lint test will enforce the project's banned-terms list (kept in `tests/`, Phase 4).
10. `docs/AI_DISCLOSURE.md` is kept current for every file.

## Status

Phase 0 (scaffold) complete. Nothing is implemented yet; Makefile targets are stubs.

## Layout

See `docs/` for `DATA_SOURCES.md`, `ASSUMPTIONS.md`, `AI_DISCLOSURE.md`, `VIDEO_SHOTLIST.md`.
