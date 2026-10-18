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

- **Two balancing authorities cover NC-08, not one.** DUK (Duke Energy Carolinas, DEC) and Duke Energy Progress (DEP, EIA-930 respondents CPLE + CPLW). Both are far larger than NC-08, so district demand is estimated by scaling (see Phase 3 prerequisite section), never observed.
- **EIA-930 series.** API v2 region-data, respondents DUK, CPLE and CPLW (one cached response each), type D, hourly, 2022-12-22 to 2022-12-26 (120 rows per respondent, no gaps). `period` is UTC; 07:00 local (EST) = 12:00 UTC. Check: demand peaks at 20,879 MW at 07:00 EST on 2022-12-24. The API was slow (~50 s) and returned one HTTP 504 during testing; the loader retries (4 attempts). The cached response is the output of the identical query. No bulk-CSV fallback was needed.
- **Observed demand caveat.** EIA demand at 07:00 is measured while DEC was already shedding load, so it is slightly below unconstrained demand. We use it as given (spec).
- **Reduction ratios** are per group, see the Phase 3 prerequisite section: r_DEC = 1,000 / 20,879 = 0.0479; r_DEP = 961 / 13,986 = 0.0687. These are regional ratios; T_NC08 is computed from district-scaled load, never from regional MW.
- **NREL data moved.** The `nrel-pds-building-stock` bucket now only holds `comstock/athena/`; the load-profile data lives in `oedi-data-lake` under `nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/` (found by listing the bucket). Releases used: `resstock_amy2018_release_2`, `comstock_amy2018_release_2`, upgrade 0 (baseline).
- **ResStock has no county aggregates in any release.** Residential per-unit load is therefore statewide NC: ResStock NC total kWh / `units_represented` (all five building types) = **5.43 kW per housing unit**, averaged over the 07:00 hour of the cold week. We apply the same per-unit value to every county (SC counties too, in Phase 3). Consequence: the residential part of W is proportional to housing units; ResStock only sets the residential-to-commercial ratio. Electric-heat share is not used in W (a possible refinement, not in the spec).
- **Cold week.** Coldest 7 days of AMY2018 from the Mecklenburg ComStock weather file: 2018-01-01 to 2018-01-07 (7-day mean -4.8 C, low -11.7 C = 11 F; Elliott morning at KCLT was ~10 F). AMY2018 is a different year from Elliott; this is a stated proxy. EULP timestamps are period-ending EST: the 07:00 hour is the rows stamped 07:15, 07:30, 07:45, 08:00; summed kWh over the hour = average kW; averaged over the 7 days.
- **Commercial per-job load uses the NC statewide ComStock total** (6,622 MW at that hour) / NC LODES 2023 jobs (4,760,483) = **1.39 kW per job**. Reason: ComStock county aggregates swing 5x per job (Mecklenburg 0.64, Robeson 3.49 kW/job; Robeson full-service restaurants alone are ~69 MW), which looks like county-model artifacts. County-scope is kept as a sensitivity (`weights.commercial_scope`). LODES jobs include sectors ComStock does not model (industry, government), so kW per job is a proxy.
- **NOAA KCLT.** NCEI Access Data Service returned HTTP 503 twice, so the fallback is the Iowa Environmental Mesonet archive of the same station's ASOS observations (display only; not used in any calculation). 72 hourly observations, 2022-12-23 to 25 local; the 07:52 observation on Dec 24 was 10 F. Rows with a missing temperature are dropped, not filled.
- **Data files are fetched with HTTP Range requests** (cold week only, ~0.3 MB per file) instead of full 15-40 MB files.

## Phase 3 prerequisite: two utilities, county assignment, district scaling (2026-10-18)

**Why two groups.** The SC Office of Regulatory Staff report (p.39, PDF p.49) and the FERC-NERC Elliott report (PDF p.71) both show Duke Energy Progress (DEP) also shed load on 2022-12-24. Four of NC-08's nine counties (Montgomery, Richmond, Robeson, Scotland) are DEP-only and two (Anson, Stanly) are shared with DEC. Using DUK alone would scale DEP territory by the wrong utility's demand.

**Sourced shed amounts (max firm load shed).**
- DEC 1,000 MW. ORS p.39: "a load shed of 400 MW was directed at 6:14 AM and implemented ... at 6:27 AM. Two (2) additional load shed requests of 300 MW each were implemented at 7:00 and 7:01 AM ... total load shed directive of 1,000 MW ... The amount of load shed was ultimately maintained at 1,000 MW." FERC-NERC PDF p.71: DEC "ordered 400 MW of firm load shed, later increasing it to 1,000 MW at 7:10 a.m."
- DEP 961 MW. FERC-NERC PDF p.71: "DEP ordered 600 MW of firm load shed at 6:25 a.m., but increased it to 800 MW at 7:10 a.m., up to a maximum of 961 MW by 7:56 a.m." ORS p.39: requests of 600 MW (6:25), 200 MW (7:10), 50 MW (7:43) and approximately 111 MW manual at transmission level (7:52), which sum to 961 MW. The two reports agree.
- **Timing caveat.** We use each utility's maximum shed. DEC had reached 1,000 MW by 7:01 (the reference hour). DEP was at about 600 MW at 07:00 and reached 961 MW at 7:56, so using 961 MW against 07:00 demand is generous to DEP. Using 600 MW instead lowers T_NC08 from 91.9 to about 78 MW (DEP term 36.8 -> 23.0 MW). Default stays at the maximum so both utilities use the same definition. The earlier "NCUC Docket M-100 Sub 163" citation was replaced by these two reports.

**EIA-930 demand at 07:00 local (EST), 2022-12-24.** DEC (DUK) 20,879 MW. DEP 13,986 MW = CPLE 12,711 + CPLW 1,275. EIA-861 lists DEP as one utility whose territory spans both Progress East and West, so DEP demand is CPLE + CPLW and is scaled over the whole DEP footprint; this avoids needing an east/west county list (no authoritative one was found; NC-08 DEP counties are all in CPLE). The spec's single `balancing_authority` became the `balancing_authorities` list in config (DUK -> CPLE + CPLW added together, which differs from the "[DUK, CPLE]" you suggested).

**Reduction ratios.** r_DEC = 1,000 / 20,879 = 0.04790. r_DEP = 961 / 13,986 = 0.06871. Observed demand is measured while shedding was already under way, so it is slightly below unconstrained demand.

**County -> group assignment (EIA Form 861, data year 2024; `Service_Territory_2024.xlsx` and the BA Code column of `Sales_Ult_Cust_2024.xlsx`; https://www.eia.gov/electricity/data/eia861/).**
- A county belongs to a group if any utility serving it is that group's own utility (DEC 5416, DEP 3046) or has the group's BA code. So co-ops and municipals inside a footprint count as that BA's load (EIA-930 BA demand includes them). 143 county-group rows: NC 52 DEC + 59 DEP, SC 19 DEC + 13 DEP (counties may appear in both).
- **Shared counties** (served by both): 24 county pairs statewide. Rule (default `customer_spread`): EIA-861 gives customers per utility and state, not per county, so each utility's customers are spread across the counties it serves in proportion to housing units, and a group's share of a county is its utilities' spread customers over the total. This is an approximation. Sensitivity cases: equal split; and every shared county wholly to DEC or wholly to DEP.
- Counties are assigned wholly to our two groups; load served by utilities in other BAs inside those counties is not separated out. The GA slice of the DUK BA and the SC counties are in the footprint only where Duke itself appears in EIA-861 for that state.
- W (consistent modeled weight, kW) = housing units x 5.432 kW/unit + LODES jobs x 1.391 kW/job (statewide values; the same values are used for SC counties). Housing units: ACS 2024 5-year counties; jobs: LODES 2023 (NC and SC WAC).

| NC-08 county | Group (share) | Matched via | EIA-861 utility numbers |
|---|---|---|---|
| Anson | DEC 0.53, DEP 0.47 | utility | 5416; 3046, 14717 |
| Cabarrus | DEC 1.00 | utility + co-op/muni BA code | 4150, 5416, 19435, 21632 |
| Mecklenburg | DEC 1.00 | utility + BA code | 5416, 9087, 19435, 21002, 21632 |
| Montgomery | DEP 0.90, DEC 0.10 | utility + BA code | 3046, 14717, 15671; 21632 |
| Richmond | DEP 1.00 | utility + BA code | 3046, 14717 |
| Robeson | DEP 1.00 | utility + BA code | 3046, 11291, 11318, 24889 |
| Scotland | DEP 1.00 | utility + BA code | 3046, 11291, 14717 |
| Stanly | DEC 0.67, DEP 0.33 | utility + BA code | 232, 5416, 19435; 3046, 14717 |
| Union | DEC 0.91, DEP 0.09 | utility + BA code | 5416, 12801, 19435; 14717 |

**District scaling result (modeled district estimates).** D_NC08 = sum over groups of D_g(07:00) x W_NC08-in-g / W_g, T_NC08 = sum of D_NC08,g x r_g.

| Quantity | DEC | DEP | NC-08 |
|---|---|---|---|
| Group demand at 07:00 (MW) | 20,879 | 13,986 | |
| W of the group (MW) | 24,457 | 17,642 | |
| W of NC-08 inside the group (MW) | 1,348 | 675 | 2,024 |
| Share of group | 5.5% | 3.8% | |
| D_NC08 part (MW) | 1,151.0 | 535.3 | **1,686.3** |
| r_g | 0.04790 | 0.06871 | effective 0.0545 |
| T_NC08 part (MW) | 55.1 | 36.8 | **91.9** |

Sensitivity of the shared-county rule: customer_spread D 1,686 / T 91.9 MW; equal split D 1,672 / T 94.6 MW; shared -> all DEC D 1,611 / T 87.6 MW; shared -> all DEP D 1,550 / T 90.8 MW. T_NC08 stays within about 5% of the default.

## Data-source failures and fallbacks
See the Phase 1 section above (TIGER file name, HIFLD -> OSM) and the Phase 2 section (NREL bucket move, no ResStock county data, NCEI -> IEM for display temperature).
