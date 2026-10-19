## Spec amendments

The brief below is kept as written. These are the places where the build differs from it, with the date and the one-line reason. Details and numbers are in `docs/ASSUMPTIONS.md`.

| Date | Change | Why |
|---|---|---|
| 2026-10-18 | Two utilities, not one: district load is scaled from Duke Energy Carolinas (EIA-930 DUK) and Duke Energy Progress (CPLE + CPLW), each with its own reduction ratio | Both utilities shed load on Dec 24, 2022 and serve NC-08 counties; one balancing authority would scale DEP territory with the wrong demand |
| 2026-10-18 | Shed amounts (1,000 MW and 961 MW) come from the SC Office of Regulatory Staff report and the FERC-NERC Elliott report, not the NCUC docket | The two reports state the figures and were read; the docket was not |
| 2026-10-18 | Shared target band (T to T plus 2%, widened to at most 5%) replaces "Stage B holds exactly T*" | Exact equality is feasible but took about 34 s to solve against about 0.5 s for the band; load is also shed in blocks |
| 2026-10-18 | Zones are census tracts (`zone_mode: tract`); no substation zones | The HIFLD Open substation layer was not reachable; the copies found cover transmission-level (69 kV and up) substations only |
| 2026-10-18 | Hard exclusions are hospitals, nursing homes and water treatment only; fire, police and wastewater are display-only | Including fire and police would protect 42.6% of housing units, too much room taken from the optimizer |
| 2026-10-18 | Optional county-share cap (default off) added as a toggle and a sensitivity row | The harm-weighted plan put 88% of its cut in one county |
| 2026-10-18 | The demo grid is pre-solved at `make freeze`, not at app start | The 10-20% presets take 2-3 s each, and the first capped solve exceeded the 2 s limit |
| 2026-10-19 | The reduction slider has four stops only: Elliott (default), 10%, 15%, 20% | Every stop is pre-solved and instant; off-grid stops fell back to a nearest result |
| 2026-10-19 | The optional node (spec Phase 5) and its firmware folder are out of this submission | The hardware prototype is still in progress |
| 2026-10-19 | "07:00" means the hour ending 07:00 (06:00-07:00); the NREL load hour was moved to match, giving D_NC08 = 1,686.7 MW and T_NC08 = 91.93 MW | EIA labels each hour by its END (confirmed against EIA's bulk files); the first build used 07:00-08:00 load by mistake |
| 2026-10-19 | The "load-only baseline" is replaced by a set of 200 equivalent load-only plans; the left map shows the typical one and a strip chart shows where the vulnerability-aware plan falls | A single load-only baseline is arbitrary (a 0.02% change in inputs flipped half its zones), so no single baseline can anchor the comparison |
| 2026-10-19 | Added a winter demand model and the panel "Why forecasts aren't enough" (not in the brief); the empty `nodes/` stubs were deleted | Shows that a validated temperature model still missed the Elliott morning by 12.6%; the stubs were unused |

---

You are building **METRIC-Grid**. One-sentence purpose: METRIC-Grid helps emergency planners and community stakeholders compare how load-only and vulnerability-aware outage scenarios could distribute risk across North Carolina's 8th Congressional District (NC-08).

**Primary user:** a county emergency planner who wants to know whether two technically equal outage scenarios could impose very different consequences on vulnerable communities, and leaves with a short list of zones to prioritize for outreach, warming centers, and backup power. Secondary: state utility-policy staff, consumer advocates, community organizations, local officials, journalists, students. Not utility operators (needs private feeder data) and not residents (no household prediction). It is a Congressional App Challenge submission due 12:00 pm EDT, October 26, 2026. I am a high-school student with FRC programming experience. Build it as a real, runnable, offline-capable project with tests. Less scope, more proof.

## What it is, in one paragraph

When a utility can't meet demand it sheds load by opening breakers at substations. On December 24, 2022 (Winter Storm Elliott), Duke Energy Carolinas began shedding at 6:14 a.m. and shed about 1,000 MW; rotating outages across the Carolinas affected roughly 500,000 customers. Publicly described procedures protect critical facilities but publish no community-vulnerability layer. METRIC-Grid takes the observed regional demand curve from that morning (EIA-930), public census vulnerability data, and published interruption-cost figures, and solves two plans held to the same target: a load-only baseline and a harm-weighted plan. It shows them side by side on a map of synthetic analysis zones with every assumption exposed. An optional single ESP32 node demonstrates a measurement path (watts, indoor temperature, wall-power timestamps). It is a planning simulator, not an operational dispatcher and not Duke's method, and the app says so.

## Non-negotiable rules

1. Every number in the UI traces to a named source in a provenance drawer; allocated or inferred values carry an "estimated" or "modeled" badge.
2. Call Voronoi cells **"synthetic analysis zones generated around public infrastructure points; not actual feeder boundaries."** Never "service areas." If substation data is unavailable, zones are census tracts, labeled as such.
3. The baseline is **"load-only baseline"** with a defined objective (below). Never describe it as what Duke does.
4. **District scaling first.** Never allocate DUK balancing-authority demand or the Carolinas-wide Elliott reduction into NC-08. Compute `D_NC08 = D_DUK * W_NC08 / W_DUK_territory` with a consistent modeled weight W, then `T_NC08 = D_NC08 * r`. Label both as modeled district estimates. The UI must say: "The Elliott regional event anchors this scenario. NC-08 load and required reduction are modeled district-scale estimates, not observed utility circuit values."
5. **Equal feasible target.** Stage A finds the minimum feasible reduction `T*` ≥ `T_NC08`; Stage B holds the weighted plan to exactly `T*`. No arbitrary epsilon. An infeasible request (target exceeds unprotected load) must produce an explanation with the maximum feasible value, not a crash.
6. Critical facilities are **hard exclusions** (`x_i = 0`), not weights, applied conservatively at zone level; the UI says this may protect more modeled load than necessary and that public facility datasets may be incomplete.
7. Do not fabricate data. If a source is unreachable, stop, say exactly what failed and what the fallback is, document it in `docs/ASSUMPTIONS.md`, and only then continue. Never silently substitute synthetic data.
8. The app must run with networking disabled after `make data` has frozen the inputs. No live API calls at runtime.
9. No claims of predicting failures, sensing the grid, verifying zones, or controlling utility equipment. Do not use the words "privacy-preserving," "federated learning," "AI optimizer," "conventional plan," "circuit," "feeder," "service area," "neighborhood demand," "least harm," or "outage plan." Use: load-only baseline; synthetic analysis zone; estimated zone load; modeled district estimate; lowest modeled harm; planning scenario.
10. Keep `docs/AI_DISCLOSURE.md` current (name every AI tool used, including Claude and Perplexity): for every file, note whether it was AI-scaffolded, AI-assisted, or written by me, with one line on what I changed. The rules require full AI disclosure and that I can explain every module.

## Stack

Python 3.11+, Streamlit, GeoPandas, shapely, scipy, PuLP (CBC), pandas, pyarrow, pydeck, pytest. Optional node: FastAPI + SQLite; Arduino C++ on Adafruit Feather ESP32 V2; `python-kasa`. `requirements.txt`, `Makefile` with `make data`, `make freeze`, `make test`, `make app`, `make demo`, `make api`. Ask before adding anything else.

## Repo layout

```
metric-grid/
  README.md
  CHANGELOG.md
  requirements.txt
  Makefile
  config.yaml                  # every constant, with a source comment
  data/raw/                    # gitignored downloads
  data/frozen/                 # committed, dated, small: the only runtime inputs
  src/metric_grid/
    config.py
    ingest/  district.py eia930.py acs.py svi.py lodes.py resstock.py hifld.py facilities.py freeze.py
    geometry/  zones.py allocate.py
    model/  load_allocation.py harm.py optimizer.py sensitivity.py scenarios.py
    app/  streamlit_app.py components/ provenance.py
    nodes/  api.py db.py aggregate.py kasa_read.py fake_node.py      # optional
  firmware/metric_node/  metric_node.ino README.md secrets.example.h  # optional
  tests/
  docs/  DATA_SOURCES.md ASSUMPTIONS.md AI_DISCLOSURE.md VIDEO_SHOTLIST.md
```

## Phase 0: scaffold (STOP for review)

Create the layout, `config.yaml` with placeholders and source comments (including `state_fips: "37"`, `district: "08"`, `balancing_authority: "DUK"`, `ba_counties: [...]`; never hard-code these anywhere else so the same code runs for any single-BA district), README with the one-paragraph description and the rules above, the four docs files, and the Makefile targets as stubs. Show me the tree.

## Phase 1: district and census (STOP)

1. **NC-08 boundary and tracts.** Census TIGER/Line 2024 `tl_2024_us_cd119.zip` filtered to `STATEFP=='37' and CD119FP=='08'`; NC tracts `tl_2024_37_tract.zip`; keep tracts with centroid inside or ≥50% area overlap. Save GeoJSON. Print tract count and counties.
2. **ACS 5-year (latest).** Census API, key from env `CENSUS_API_KEY`. Tract level: B25001 housing units, B25034 year built, B25040 heating fuel (compute `share_electric_heat` = electricity / occupied units), B19013 median income, B25003 tenure. Do **not** compute a separate age-65+ term for the harm model; SVI already contains it. You may pull B01001 for display only.
3. **CDC/ATSDR SVI 2022** NC tract CSV. Keep `RPL_THEMES` and the four theme percentiles. Document -999 handling (treat as missing, warn, never zero-fill).
4. **LEHD LODES WAC** latest year, block → tract: `C000` total jobs; CNS05 manufacturing, CNS07 retail, CNS16 health. For sector cost mix and commercial allocation.
5. **Critical facilities.** Hospitals, nursing homes, water treatment plants, fire and police stations within NC-08 from HIFLD Open if accessible, else OpenStreetMap via a one-time Overpass pull. Save as points with a `facility_type`. These become exclusions in Phase 3.

Tests: stable tract count, clean GEOID joins, no silent NaN fills. Show me the joined tract table summary.

## Phase 2: demand and load profiles (STOP)

1. **EIA-930.** API v2 `https://api.eia.gov/v2/electricity/rto/region-data/data/`, env `EIA_API_KEY`, `respondent=DUK`, `type=D`, hourly, 2022-12-22 to 2022-12-26. Fallback: the EIA-930 bulk CSV for 2022 H2. Save the series; identify the 2022-12-24 06:00–08:00 window. Record in ASSUMPTIONS.md that DUK is a balancing authority (most of NC plus upstate SC), far larger than NC-08, and that zone demand is therefore estimated.
2. **Default reduction ratio.** Per NCUC Docket M-100 Sub 163, DEC shed ~1,000 MW beginning 06:14. Default `r` = 1,000 ÷ DUK demand at 07:00. Cite the docket in config. `T_NC08` is computed in Phase 3 after district scaling; it is never the regional MW.
3. **NREL ResStock / ComStock** county-level timeseries aggregates from the public `nrel-pds-building-stock` S3 bucket for NC-08 counties, coldest week of the AMY2018 weather year, residential and commercial. List the bucket to find real paths; do not guess. If this fails after a reasonable attempt: flat weights (housing units; LODES jobs), documented prominently.
4. **NOAA.** KCLT hourly temperature for Dec 23–25, 2022, display only.

Show me the demand curve and the weights summary.

## Phase 3: zones, allocation, freeze (STOP)

1. **Zones.** Try the HIFLD Open ArcGIS REST Electric Substations layer. Some HIFLD layers now require authenticated access; if this one does, log it and set `zone_mode: tract`. If available: inspect the schema, filter distribution substations (document the filter), `scipy.spatial.Voronoi`, clip to NC-08, drop slivers. Stable `zone_id`.
2. **Area-weighted join** of tract attributes into zones: sums for housing units, occupied units, electric-heat units, jobs by sector; area-weighted means for SVI percentiles and median income. Flag each zone's `protected = True` if it contains any critical facility.
3. **District scaling, then allocation** (`model/load_allocation.py`). Compute weight `W_z = Σ(housing units × ResStock per-unit load at 07:00) + Σ(jobs × ComStock per-job load)` for NC-08 and, with the identical method, for the list of DUK-served counties (document the list). `D_NC08 = D_DUK(07:00) × W_NC08 / W_DUK`. `T_NC08 = D_NC08 × r`. Then `L_i = D_NC08 × W_i / W_NC08` per zone so `Σ L_i = D_NC08` (test). Every `L_i`, `D_NC08`, `T_NC08` carries `source: "modeled district estimate"`.
4. **`make freeze`.** Write the final zone GeoDataFrame, the demand window, constants, and dataset dates to `data/frozen/` as small parquet/GeoJSON/JSON. From here on the app reads only `data/frozen/`. Add a test that the app imports and renders with network disabled (monkeypatch `socket`).

Show me a map of zones colored by `L_i`, with protected zones outlined.

## Phase 4: model, app, tests (STOP)

1. **Harm (`model/harm.py`), two quantities with units, stored as separate columns:**
   - `N_i` = occupied households (ACS B25003); `SVI_i` = RPL_THEMES; `EHeat_i` = share electric heat; `J_i,sector` = LODES jobs.
   - `H_human_i = N_i * (w_s * SVI_i + w_e * EHeat_i)` [households × dimensionless]; defaults `w_s=0.7, w_e=0.3`, documented as judgment calls.
   - `H_econ_i = N_i * c_res * h + Σ_sector J_i,sector * c_sector * h` [dollars]; `c` from LBNL ICE Calculator 2.0 report with page cites; `h = 1`.
   - `Hhat_human_i = H_human_i / max_j H_human_j`; `Hhat_econ_i = H_econ_i / max_j H_econ_j`.
   - `H_i(alpha) = alpha * Hhat_human_i + (1 - alpha) * Hhat_econ_i`, alpha from the UI, default 0.5.
   - Missing SVI/ACS: warn visibly, exclude from normalization, never zero-fill. Write the full formula, symbols, sources, normalization and missing-data rules to ASSUMPTIONS.md so one zone can be reproduced by hand; add a test that recomputes one zone from raw inputs.
2. **Optimizer (`model/optimizer.py`), two-stage, PuLP/CBC, deterministic:**
   - Binary `x_i`; fixed `x_i = 0` where `protected`.
   - **Stage A (load-only baseline):** minimize `Σ x_i L_i` s.t. `Σ x_i L_i ≥ T_NC08`. Record `T* = optimum`. Tie-break: fewest zones, then lowest zone_id.
   - **Stage B (vulnerability-aware):** minimize `Σ x_i H_i(alpha)` s.t. `Σ x_i L_i = T*` (within solver tolerance, e.g. 1e-6 relative). Same tie-break.
   - If `T_NC08 > Σ_unprotected L_i`: return an `Infeasible` result carrying the maximum feasible value; the UI explains it; a test covers it.
   - `solve()` returns selected zones, `T_NC08`, `T*`, Σ L shed, Σ H_human, Σ H_econ, and per-zone components. Deterministic (fixed CBC options) and under one second for a few hundred zones; assert both.
   - **Demo safety net:** wrap `solve()` in `st.cache_data` keyed on (alpha, target, weights). At app startup, pre-solve a grid of alpha ∈ {0, 0.25, 0.5, 0.75, 1} × target ∈ {10, 15, 20}% and keep it in memory. If a live solve errors or exceeds 2 s, show the nearest pre-solved result with a visible "showing nearest pre-computed setting" note. Never invent named scenarios; the only preset is the Elliott-anchored district scenario.
3. **Sensitivity (`model/sensitivity.py`).** Re-solve over a grid of alpha ∈ {0, 0.25, 0.5, 0.75, 1} and w_svi ∈ {0.5, 0.7, 0.9}; report which zones are selected in every setting, in some, in none. Also re-solve with flat allocation weights to show how much the allocation assumption moves the answer.
4. **Scenarios (`model/scenarios.py`).** T at 10/15/20% of NC-08 load; zones cut in all vs. only the worst.
5. **Streamlit app**, one page, in this order:
   - Title; "Same target, different burden."; "Public-data planning simulator, not an operational switching tool."; scenario date; dataset version; a visible "Modeled scenario" badge; the district-scaling sentence from rule 4.
   - Scenario: "Winter Storm Elliott, Dec 24 2022, 07:00" (default; frozen).
   - Required reduction slider (% of modeled NC-08 load; MW shown). Above the maps, four numbers: requested target, T* under each plan (identical), modeled human-impact change, modeled economic-impact change. Alpha slider with labels "human harm ↔ economic cost."
   - **Two maps, same extent, same zoom, same colorblind-safe scale (no red/green), same T***: left "Load-only baseline", right "Harm-weighted plan". Shed zones dark; protected zones hatched/outlined; hover shows zone_id, L_i (est.), svi, heat, econ, H_i. Under each: MW shed, overshed, est. customers affected, electric-heat households affected, est. interruption cost.
   - **Flip strip**: zones whose status differs between plans, each with an auto-generated one-liner from its components ("kept in weighted plan: SVI 0.91, 62% electric heat; cut instead: zone 114, 0.12 SVI, 3 customers").
   - **Zone detail card** (click or select): inputs, the formula with this zone's numbers substituted, badges "zone: synthetic", "load: estimated".
   - Zone lookup from a **fixed list of demo locations** in config (no live geocoder). Show status under both plans.
   - Sensitivity panel (always/sometimes/never table) and stress-test expander.
   - **Planning-implications card**, built only from values already computed: zones selected in every sensitivity setting; vulnerability factors driving the difference; estimated households and jobs affected; critical facilities excluded; result sensitivity; fixed-text follow-ups ("consider outreach", "backup-power planning", "resilience-hub siting", "request feeder data"). Never a switching recommendation.
   - Methods / provenance drawer: every source with URL, dataset date, model date, every proxy, the three honesty labels.
   - "Reset demo" button that restores all defaults.
   - If `nodes` is enabled in config: a node panel reading `data/node_aggregates.parquet` (hourly aggregates only), showing latest watts, temp, heartbeat age, offline count. Hidden otherwise.
6. **Tests (`tests/`)**: zone loads sum to `D_NC08`; both plans shed exactly `T*` and `T*` is minimal; protected zones never selected; determinism; alpha=1 and alpha=0 reproduce documented components; missing data raises a visible error; map totals equal optimizer totals; three toy problems with known answers (protected zone cheapest; plans differ; request infeasible); infeasible target returns explanation not crash; one-zone hand recomputation; offline start from clean clone.

Show me both maps at the default scenario and `pytest -q` output.

## Phase 5 (optional; only if Phase 4 is done and green, and only started after Oct 19): node

Gate: ships in the video only if by Oct 20 it completes five consecutive clean cycles of detect wall-power loss → keep accurate time → continue logging → reconnect → upload each cached reading exactly once. Otherwise remove it from the demo.

1. **FastAPI + SQLite.** `readings(node_id, ts_utc, temp_f, wall_power, watts NULL, uploaded_at)`, `nodes(node_id, zone_id, label)`. `POST /readings` accepts a list, idempotent on (node_id, ts_utc). `aggregate.py` writes hourly per-zone aggregates to `data/node_aggregates.parquet`; the app never reads raw rows. Pseudonymous node IDs; no addresses stored; a `DELETE /nodes/{id}` endpoint.
2. **`kasa_read.py`**: discover the plug, read emeter watts, write to the API as `watts`. No `apply_plan` switching in the core; a separate `demo_switch.py` with `--dry-run` may exist, documented as demo-only.
3. **Firmware** for **Adafruit Feather ESP32 V2** (built-in LiPo charger, power path, VBUS sense): libraries WiFi, HTTPClient, OneWire, DallasTemperature, RTClib, LittleFS, Adafruit_SSD1306, Adafruit_GFX, ArduinoJson. DS18B20 on a GPIO with 4.7k pull-up; DS3231 and SSD1306 on I2C; wall-power = VBUS sense pin. Loop: wake → read temp and VBUS → RTC time → append `ts,temp_f,wall_power` to `/log.csv` → OLED shows temp, "WALL POWER: ON/OFF", "LAST SYNC n MIN" or "OFFLINE n LOGGED" → Wi-Fi (10 s timeout) → if connected: NTP→RTC once per boot, POST entire backlog, on 200 truncate → deep sleep 60 s. `#define DEMO_MODE` disables sleep. README with wiring, board setup, `secrets.h`, expected serial output. Note that the Feather replaces the earlier TP4056/divider design for safety.
4. **`fake_node.py`** simulator for UI development only; never in the video.

Acceptance: reconnect uploads cached readings exactly once with timestamps preserved (test with a fake server).

## Phase 6: polish (STOP)

- README: what it is, honest limits, screenshots, how to run offline, data sources and dates, assumptions, prior work (Shah et al. 2023 doi 10.1088/2634-4505/acd4e7; UT Austin equity-informed resilience; arXiv 2406.17877; 2204.06543; 2402.04444; 2407.18989; 2404.11520; NCUC M-100 Sub 163; FERC/NERC Elliott report), AI disclosure summary, open-source list with purpose, version 2.0 (utility feeder data; network constraints; cumulative-burden fairness; consent-based sensor pilot; thermal model; stochastic scenarios).
- `docs/VIDEO_SHOTLIST.md` with the exact UI states to record, including the 8–12 lines of optimizer code to show and the one test to run on camera.
- `make demo` loads the frozen scenario and opens the app. Confirm from a clean clone with networking disabled.
- Useful empty, loading, infeasible, and missing-data states; tooltips for SVI, ICE, synthetic zone, feasible target; no horizontal scroll at the recording resolution.
- A `docs/REVIEWS.md` for three external reviews (a non-expert, a programmer, a policy/energy person) with the changes made; never claim endorsement.

## Working style

One phase at a time; at each STOP give a short summary: what you verified, what failed, what you need me to decide. Small readable functions with docstrings; I must be able to explain every file to a judge. One CHANGELOG line per meaningful step, and update AI_DISCLOSURE.md in the same commit. Cap workarounds for a dead data source at ~20 minutes, then fall back and document. Start with Phase 0.
