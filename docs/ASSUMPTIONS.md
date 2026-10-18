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

## Data-source failures and fallbacks
See the Phase 1 section above (two items: TIGER file name, HIFLD -> OSM).
