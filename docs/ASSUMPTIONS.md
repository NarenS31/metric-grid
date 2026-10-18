# Assumptions and fallbacks

Judgment calls, proxies, data-source failures and the fallbacks used are recorded here before work continues past them (rule 7).

## Fixed design decisions
- DUK is an EIA balancing authority (most of NC plus upstate SC), far larger than NC-08. Zone demand is therefore estimated, never observed. (Detailed in Phase 2.)
- Harm weights `w_s = 0.7`, `w_e = 0.3` are judgment calls, varied in the sensitivity panel.
- Outage duration `h = 1` is a judgment call.
- Banned/required vocabulary is enforced by a lint test (Phase 4).

## Harm model formula
TBD Phase 4: full formula, symbols, sources, normalization, missing-data rules, worked single-zone example.

## Phase 1 data decisions and fallbacks (2026-10-18)

- **TIGER congressional districts, file name deviation.** The spec names `tl_2024_us_cd119.zip`; that URL returns 404. The 2024 release publishes cd119 per state, so we use `tl_2024_37_cd119.zip` (same data, NC only). No fallback data involved.
- **Critical facilities: HIFLD Open not usable, OpenStreetMap fallback used.** `hifld.probe_hifld()` listed the public HIFLD ArcGIS REST root and found no hospital, nursing home, fire station or police layers (the hub site only serves a generic ArcGIS Hub page). Per spec, we did a one-time OpenStreetMap Overpass pull (cached in `data/raw/facilities/`). OSM is volunteer-mapped and incomplete, so facility exclusions can miss real facilities; the app must say so. Types: hospital, nursing_home, water_treatment (`man_made=water_works`), wastewater_treatment (`man_made=wastewater_plant`, added beyond the spec's "water treatment plants" because it is also critical infrastructure; drop it in config if you disagree), fire_station, police.
- **Whole tracts vs. partial overlap.** A tract is kept if its centroid is inside NC-08 or >=50% of its area overlaps it. 15 of 183 kept tracts are less than 99% inside the district and 1 is under 50% inside (kept by centroid). Tract attributes are used whole, so district totals include some people/jobs just outside the boundary. This is a stated approximation.
- **SVI -999 / missing.** The CDC sentinel -999 is converted to NaN with a visible warning. In NC-08 exactly one tract has no SVI: 37007980000 (Anson County), which has 0 housing units and 0 occupied units. It stays NaN; it is not zero-filled. Phase 4 must exclude it from normalization and warn visibly.
- **ACS negative sentinels** (e.g. -666666666 for suppressed median income) become NaN. One NC-08 tract has no median income (the same zero-population tract). `share_electric_heat` = B25040_004E / B25040_001E (occupied units); it is NaN where occupied units are 0.
- **ACS vintage:** 2024 5-year (2020-2024), the latest returning data on 2026-10-18. **LODES:** LODES8 NC WAC, JT00 (all jobs), year 2023, the latest file returning HTTP 200. WAC rows are blocks; the first 11 digits of `w_geocode` give the tract (no crosswalk needed). Every NC-08 tract has at least 31 jobs, so no LODES gaps.
- **Protected facility types (decided 2026-10-18).** Hard exclusions are hospitals, nursing homes and water treatment plants only. Fire stations, police stations and wastewater plants are display-only. Reason for fire and police: fire and police stations commonly have backup generation. Reason for wastewater: not in the spec's list; kept for map display. Tract-level check that drove this (tract = a proxy for zones; recheck in Phase 3 with real zones):

  | Option | Tracts protected | % of 183 | Housing units in protected tracts |
  |---|---|---|---|
  | (a) hospital + nursing home + water treatment | 26 | 14% | 46,255 (15.0%) |
  | (b) (a) + fire + police | 73 | 40% | 131,454 (42.6%) |
  | (b) + wastewater | 84 | 46% | 149,431 (48.4%) |

  Option (b) exceeds the ~35% limit, which would leave the optimizer too little room to show a difference between plans. The UI must still say exclusions are conservative and that facility data (OSM) may be incomplete.
- **B01001** (total population) is fetched for display only.

## Protected-facility decision (2026-10-18, owner decisions)

- **Protected (hard exclusion):** hospital, nursing_home, water_treatment. Set in `config.yaml` under `facilities.protected_types`.
- **Display-only:** fire_station, police, wastewater_treatment. They stay in `facilities.geojson` and are drawn on the map but never set `protected`. `wastewater_treatment` was dropped from the protected list by decision (it was added beyond the spec in Phase 1). Fire and police are display-only because fire and police stations commonly have backup generation, and because protecting them leaves the optimizer too little room (below).
- **Headroom check** (183 NC-08 tracts, 308,920 housing units, OSM facilities joined to tracts by point-in-polygon; 4 of the 164 OSM points fall outside every kept tract and are not counted):

| Option | Protected tracts | Housing units in protected tracts |
|---|---|---|
| (a) hospitals + nursing homes + water treatment | 26 (14.2%) | 46,255 (15.0%) |
| (b) (a) + fire + police | 73 (39.9%) | 131,454 (42.6%) |

  (b) exceeds the ~35% ceiling, so (a) is the default. Fire stations alone cover 51 tracts (30.5% of housing units). For reference, the earlier list with wastewater would have protected 47 tracts (27.0%).
- **Whole-tract attributes for partial tracts** stay as documented in the Phase 1 section. These counts are tract-level; the zone-level `protected` flag in Phase 3 will differ if zones are substation cells, and must be re-checked against the same ~35% ceiling.
- OSM facility data is incomplete, so a protected tract can miss a real facility and the app must say so (rule 6).

## Phase 2 data decisions and fallbacks (2026-10-18)

- **DUK is Duke Energy Carolinas (DEC)**, an EIA balancing authority covering most of NC plus upstate SC, far larger than NC-08. Zone demand is therefore estimated by district scaling (D_NC08 = D_DUK x W_NC08 / W_DUK), never observed.
- **EIA-930 series.** API v2 region-data, respondent DUK, type D, hourly, 2022-12-22 to 2022-12-26 (120 rows, no gaps). `period` is UTC; 07:00 local (EST) = 12:00 UTC. Check: demand peaks at 20,879 MW at 07:00 EST on 2022-12-24. The API was slow (~50 s) and returned one HTTP 504 during testing; the loader retries (4 attempts). The cached response is the output of the identical query. No bulk-CSV fallback was needed.
- **Observed demand caveat.** EIA demand at 07:00 is measured while DEC was already shedding load, so it is slightly below unconstrained demand. We use it as given (spec).
- **Default r = 1,000 MW / 20,879 MW = 0.04790** (4.79%). 1,000 MW is the approximate DEC shed per NCUC Docket M-100 Sub 163. This is a regional ratio; T_NC08 is computed later from district-scaled load, never from regional MW.
- **NREL data moved.** The `nrel-pds-building-stock` bucket now only holds `comstock/athena/`; the load-profile data lives in `oedi-data-lake` under `nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/` (found by listing the bucket). Releases used: `resstock_amy2018_release_2`, `comstock_amy2018_release_2`, upgrade 0 (baseline).
- **ResStock has no county aggregates in any release.** Residential per-unit load is therefore statewide NC: ResStock NC total kWh / `units_represented` (all five building types) = **5.43 kW per housing unit**, averaged over the 07:00 hour of the cold week. We apply the same per-unit value to every county (SC counties too, in Phase 3). Consequence: the residential part of W is proportional to housing units; ResStock only sets the residential-to-commercial ratio. Electric-heat share is not used in W (a possible refinement, not in the spec).
- **Cold week.** Coldest 7 days of AMY2018 from the Mecklenburg ComStock weather file: 2018-01-01 to 2018-01-07 (7-day mean -4.8 C, low -11.7 C = 11 F; Elliott morning at KCLT was ~10 F). AMY2018 is a different year from Elliott; this is a stated proxy. EULP timestamps are period-ending EST: the 07:00 hour is the rows stamped 07:15, 07:30, 07:45, 08:00; summed kWh over the hour = average kW; averaged over the 7 days.
- **Commercial per-job load uses the NC statewide ComStock total** (6,622 MW at that hour) / NC LODES 2023 jobs (4,760,483) = **1.39 kW per job**. Reason: ComStock county aggregates swing 5x per job (Mecklenburg 0.64, Robeson 3.49 kW/job; Robeson full-service restaurants alone are ~69 MW), which looks like county-model artifacts. County-scope is kept as a sensitivity (`weights.commercial_scope`). LODES jobs include sectors ComStock does not model (industry, government), so kW per job is a proxy.
- **NOAA KCLT.** NCEI Access Data Service returned HTTP 503 twice, so the fallback is the Iowa Environmental Mesonet archive of the same station's ASOS observations (display only; not used in any calculation). 72 hourly observations, 2022-12-23 to 25 local; the 07:52 observation on Dec 24 was 10 F. Rows with a missing temperature are dropped, not filled.
- **Data files are fetched with HTTP Range requests** (cold week only, ~0.3 MB per file) instead of full 15-40 MB files.

## Data-source failures and fallbacks
See the Phase 1 section above (TIGER file name, HIFLD -> OSM) and the Phase 2 section (NREL bucket move, no ResStock county data, NCEI -> IEM for display temperature).
