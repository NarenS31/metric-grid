# Assumptions and fallbacks

Judgment calls, proxies, data-source failures and the fallbacks used are recorded here before work continues past them (rule 7).

## Fixed design decisions
- DUK is an EIA balancing authority (most of NC plus upstate SC), far larger than NC-08. Zone demand is therefore estimated, never observed. (Detailed in Phase 2.)
- Harm weights `w_s = 0.7`, `w_e = 0.3` are judgment calls, varied in the sensitivity panel.
- Outage duration `h = 1` is a judgment call.
- Banned/required vocabulary is enforced by a lint test (Phase 4).

## Harm model (Phase 4.1)

Two separate quantities with units, stored as separate columns, then a user-weighted blend.

| Symbol | Meaning | Source |
|---|---|---|
| N_i | occupied households in zone i | ACS 2024 5-year B25003_001 |
| SVI_i | RPL_THEMES, 0 to 1 | CDC/ATSDR SVI 2022 (already contains age 65+, so no separate age term) |
| EHeat_i | occupied units heated by electricity / occupied units | ACS B25040_004 / B25040_001 |
| J_i,s | jobs in zone i | LODES 2023 (manufacturing CNS05, retail CNS07, health CNS16, other = total - those) |
| w_s, w_e | 0.7, 0.3 | judgment calls (config), varied in the sensitivity panel |
| c_res | $5.1 per household for a 1-hour interruption | LBNL ICE report LBNL-6941E, Table ES-1, p. xii (PDF p. 14); Table ES-2 non-summer morning also $5.1 (p. xiii, PDF p. 15). U.S. 2013 dollars, not inflated |
| c_job | $21.8 per average kW (Medium and Large C&I, 1 hour, same table) x 1.3911 kW per job = $30.33 per job | ICE Table ES-1; kW per job from ComStock NC / LODES NC jobs (Phase 2) |
| h | 1 hour | judgment call; only 1 is supported because the ICE inputs are the 1-hour column |

- H_human_i = N_i x (w_s x SVI_i + w_e x EHeat_i)    [households x dimensionless, "vulnerability-weighted households"]
- H_econ_i = N_i x c_res x h + sum over sectors of J_i,s x c_job x h    [dollars]
- Hhat_human_i = H_human_i / max_j H_human_j; Hhat_econ_i = H_econ_i / max_j H_econ_j (max over zones with data)
- H_i(alpha) = alpha x Hhat_human_i + (1 - alpha) x Hhat_econ_i, alpha from the UI, default 0.5.

**ICE limitation.** The report gives costs by customer size class (Small C&I under 50,000 kWh/yr; Medium and Large C&I), not by NAICS sector, so manufacturing, retail, health and other all use one commercial rate. Choosing the Medium and Large class is a judgment call (most commercial kW sits in larger customers); the Small C&I rate ($295.0 per average kW, 13.5x higher) is a sensitivity case: with it the harm-weighted plan's interruption-cost change goes from -43% to -54% and the plan is the same size (16 zones differ). Costs per average kW are applied to the ComStock kW at the cold 07:00 hour, which is above an annual-average kW, so economic cost per job is likely overstated. Dollars are 2013 dollars.

**Worked example (zone_id 141, GEOID 37179020305, Union County).** N = 2,959; SVI = 0.0890; EHeat = 0.2856; jobs = 571.
H_human = 2,959 x (0.7 x 0.0890 + 0.3 x 0.2856) = 437.8. H_econ = 2,959 x $5.1 + 571 x $30.33 = $15,091 + $17,316 = $32,407.
max H_human = 2,018.9, max H_econ = $267,572, so Hhat_human = 0.2169, Hhat_econ = 0.1211, and H(0.5) = 0.1690. A test recomputes a zone from raw inputs.

**Missing data.** A zone with households but no SVI or electric-heat value gets NaN H_human, a visible MissingDataWarning, is excluded from the normalization maximum, and the optimizer raises MissingDataError rather than price it. Zone 9 (GEOID 37007980000) has no SVI but 0 occupied households, so H_human = 0 by definition (N_i = 0), not by a zero-fill; it is included in normalization as 0, a warning says so, and its H_econ is positive because it has 431 jobs.

## Optimizer, shared target band (Phase 4.2; changes the spec's "T*" rule, decided 2026-10-18)

Both plans use the same band: T_NC08 <= sum x_i L_i <= T_NC08 + delta, delta = 2% of T_NC08 (1.84 MW at T_NC08 = 91.9 MW), x_i = 0 for protected zones. The UI says "both plans cut between X and Y MW" and reports each plan's actual MW.
- **Stage A (load-only baseline):** minimize sum x_i L_i inside the band (least overshed). **Stage B (vulnerability-aware):** minimize sum x_i H_i(alpha) inside the same band. Ties: fewest zones, then lowest zone_id.
- If the band has no solution it is widened through 3%, 4%, 5% and the width used is reported; if still empty, or the target exceeds the unprotected load, the result is Infeasible with the maximum feasible reduction (unprotected load) and an explanation.
- **Tolerance.** Stage A is least-overshed within 10 kW (`load_tol_mw: 0.01`); loads within 10 kW count as tied and then go to the fewest-zones and lowest-zone_id rules. A 0.1 kW tolerance made the solve about 10 s.
- **Why a band (the reason differs from the first assumption).** The check done before this change found that exact equality (sum within 1e-6 of Stage A's optimum) is NOT infeasible: with 157 selectable zones, a subset-sum count finds about 5 x 10^12 subsets at 0.1 kW resolution (about 5 x 10^16 per MW), and Stage A's optimum overshoots T_NC08 by only 5 to 13 kW. Solving Stage B under exact equality with CBC also returned a plan different from Stage A's (10 zones vs 6; harm sum 1.100 vs 2.411 in normalized units). The real problem is run time: that solve took about 34 s, against about 0.5 s for the band, and the 2% band loses nothing (harm sum 1.017, lower than the equality solve). The band is kept because load is shed in discrete blocks and operators cannot hit an exact MW, and because it is about 60 times faster.
- **Run time.** Default scenario (T_NC08, 183 zones): about 0.5 to 0.6 s for both plans. The 10, 15 and 20% presets take 2 to 3 s (Stage A's tie-break solve dominates); the app must pre-solve those, see Phase 4 step 5. Tests assert under 2 s for the default.
- **Bug found by tests:** PuLP ignores `upBound` on Binary variables, so an early version selected protected zones. The hard exclusion is now an explicit `x_i == 0` constraint and tests cover it.

**Default scenario result (alpha = 0.5, band 91.91 to 93.75 MW, 0.6 s):**

| | Load-only baseline | Harm-weighted plan |
|---|---|---|
| MW cut (overshoot) | 91.91 (0.01) | 92.10 (0.19) |
| Zones cut | 6 | 10 |
| Households | 15,443 | 17,956 |
| Electric-heat households | 8,837 | 5,484 |
| Vulnerability-weighted households | 7,860 | 2,053 (-74%) |
| Interruption cost (1 h, 2013$) | $478,888 | $271,958 (-43%) |

16 zones differ between the plans. The harm-weighted plan cuts more households but less vulnerable ones (mean SVI 0.03 vs 0.52). Band sensitivity (1%, 2%, 5%): identical plans, so the harm difference survives. Alpha sweep: at alpha 0 (economic only) the weighted plan imposes +50% human harm while saving 69% of economic cost; at alpha 1 it saves 83% of human harm and 2% of cost.

## Sensitivity, scenarios, pre-solved grid (Phase 4 steps 3-4; all in data/frozen/)

**Spec deviation (approved 2026-10-18): the demo safety-net grid is pre-solved at `make freeze`, not at app startup.** The 10/15/20% presets take 2 to 3 s per solve, so solving 15 points at startup would take about 40 s. `presolved.json` holds 20 points: alpha {0, .25, .5, .75, 1} x targets {Elliott T_NC08, 10%, 15%, 20% of D_NC08}; the Elliott row is added because it is the default scenario. The app falls back to the nearest point (with a visible "showing nearest pre-computed setting" note) if a live solve errors or exceeds 2 s.

**Sensitivity settings (20, weighted plan vs load-only baseline at T_NC08 = 91.9 MW):** alpha {0, .25, .5, .75, 1} x w_svi {.5, .7, .9} (15); band 1% and 5% (2% is in the grid); Small C&I cost rate; flat allocation weights (1 per housing unit + 1 per job instead of 5.43 and 1.39 kW, renormalized to the same D_NC08; this also changes the baseline); county-share cap 50% (below; also changes the baseline).
- **Zone classes by the weighted plan's cuts:** always cut in every setting: 0. Sometimes: 37. Never cut although selectable: 120. Protected (never selectable): 26. The most frequently cut zones are 144 and 178 (15 of 20 settings each).
- **Human harm:** the weighted plan has lower vulnerability-weighted households cut in 17 of 20 settings (-53% to -91%). It is HIGHER (+49% to +50%) in the three alpha = 0 settings, where human harm is ignored by construction. It beats the baseline on interruption cost in all 20 settings.
- **Households:** the weighted plan cuts MORE households in all 20 settings (+87 to +6,799; +2,513, +16%, in the default setting). Every UI place that shows vulnerability or cost results must say so plainly next to those numbers (`scenarios.plain_summary` builds the sentence from the numbers and says "MORE" or "fewer" as the data says).
- **Band 1% / 2% / 5%:** identical plans. **Small C&I cost rate:** same plan, interruption cost change -54% instead of -43%. **Flat allocation:** baseline 5 zones vs weighted 12 zones, human harm -61%, cost -26%, +6,799 households; so the allocation assumption matters, but the direction does not change.
- **Priority list ("where to plan first"), the definition used by the planning-implications card.** Since no zone is always cut, the list is the zones the default load-only baseline cuts that the vulnerability-aware plan spares in EVERY setting with alpha > 0, ordered by SVI. Six zones (`cut at alpha 0` marks the two that the economic-only settings do cut):

  | Zone | County | SVI | Electric-heat share | Households | Note |
  |---|---|---|---|---|---|
  | 8 | Anson | 0.91 | 67% | 1,498 | cut when alpha = 0 |
  | 23 | Cabarrus | 0.83 | 62% | 2,308 | |
  | 10 | Cabarrus | 0.64 | 62% | 3,178 | cut when alpha = 0 |
  | 32 | Cabarrus | 0.32 | 52% | 3,556 | |
  | 142 | Union | 0.29 | 24% | 2,429 | |
  | 12 | Cabarrus | 0.11 | 81% | 2,474 | |

  The card is built only from these computed values and fixed-text follow-ups (outreach, backup-power planning, resilience-hub siting, request utility circuit data); it is never a switching recommendation. The list is a statement about this model and its settings, not a verified finding about specific neighborhoods.
- **Where the cuts land (default).** Baseline: Cabarrus 4 zones (63.7 MW, 11,516 households, mean SVI 0.48), Anson 1 (8.7 MW, 1,498 households, SVI 0.91), Union 1 (19.6 MW, 2,429 households, SVI 0.29). Weighted: Union 9 zones (81.5 MW, 15,910 households, mean SVI 0.04) and Mecklenburg 1 (10.7 MW, 2,046 households, SVI 0.01). The weighted plan concentrates its cuts in one county with very low vulnerability, which is a fairness concern of its own (cumulative burden on one place), and it is a version 2.0 item.

**Scenarios (alpha 0.5):**

| Target | MW | Zones cut (baseline / weighted) | Households (baseline / weighted) | Human harm | Interruption cost (2013$) |
|---|---|---|---|---|---|
| 10% of D_NC08 | 168.6 | 11 / 18 | 26,824 / 30,405 | -69% | -43% |
| 15% | 252.9 | 17 / 27 | 41,422 / 46,247 | -62% | -39% |
| 20% | 337.3 | 23 / 38 | 52,950 / 61,216 | -62% | -36% |

Zones cut in all three scenarios: baseline 11, weighted 18. Zones cut only in the 20% scenario: baseline 8, weighted 11. The weighted plan cuts more households in every scenario.

**Alpha sweep (`docs/figures/alpha_tradeoff.png`, T_NC08, default weights):**

| alpha | Human harm change | Interruption cost change | Households cut change |
|---|---|---|---|
| 0 | +50% | -69% | +2,256 (+15%) |
| 0.25 | -64% | -54% | +215 (+1%) |
| 0.5 | -74% | -43% | +2,513 (+16%) |
| 0.75 | -81% | -17% | +1,772 (+12%) |
| 1 | -83% | -2% | +1,202 (+8%) |

**Dollar labeling.** Every dollar figure in the UI is labeled "2013 dollars" (ICE report dollars, not inflated).

## County-share cap (optional, default OFF; added 2026-10-18)

In the default scenario the baseline puts 69% of its cut in Cabarrus County and the weighted plan puts 88% in Union County. As a response to cumulative-burden concentration the optimizer has an optional constraint (`optimizer.county_cap`, enabled: false, max_share: 0.5): no single county may take more than 50% of the total MW cut. It is linear (county MW <= share x total MW cut), applied to BOTH plans equally, and changes the baseline too. Infeasible if the unprotected load is in too few counties (the result says so). Solve time about 1.3 s (the default without the cap is about 0.5 s). It limits concentration by county only; it does not make the weighted plan spread cuts to vulnerable counties.

**Default scenario with the cap ON (alpha 0.5, band 91.91 to 93.75 MW, T_NC08 = 91.9 MW):**

| | Baseline | Weighted | Weighted vs baseline |
|---|---|---|---|
| MW cut | 91.92 | 92.24 | |
| Zones cut | 6 | 10 | |
| Households cut | 15,197 | 16,891 | +1,694 (+11.1%) MORE households |
| Electric-heat households | | | -2,202 (fewer) |
| Vulnerability-weighted households | 5,556 | 2,266 | -59.2% |
| Interruption cost (2013 dollars) | $556,726 | $280,901 | -49.5% |

Counties (share of MW cut): baseline Cabarrus 3 zones 45.3 MW (49%), Mecklenburg 2 zones 27.1 MW (29%), Union 1 zone 19.6 MW (21%). Weighted: Union 5 zones 45.6 MW (49%), Mecklenburg 4 zones 32.5 MW (35%), Montgomery 1 zone 14.1 MW (15%).

Compared with the cap OFF numbers (weighted: 88% of cuts in Union; vulnerability-weighted households 2,053; cost $271,958; +2,513 households), the cap moves the baseline AWAY from the high-SVI Anson zone (baseline vulnerability-weighted households 7,860 -> 5,556, cost $478,888 -> $556,726), so the gap in human harm narrows from -74% to -59%, while the weighted plan is only slightly worse in absolute terms (2,053 -> 2,266). The weighted plan still cuts more households. The cap is a sensitivity row (`county-share cap 50%`) in the sensitivity table; the pre-solved demo grid stays cap-OFF.

## App (Phase 4 step 5; `make app`)

- **Everything on the page is computed**: headline, honest line, flip-strip sentences, metrics and the robustness counts are built from model results and `data/frozen/` (tests compare the page text with the model output). The headline flips wording with the numbers: at alpha = 0 it reads "N MORE electric-heat households in the dark" and the honest line says "50% more vulnerability-weighted households".
- **Honesty line.** The sentence from `scenarios.plain_summary`, which says "cuts N MORE households" when that is what the numbers say, sits directly under the headline in every state. Dollar figures are labeled "2013 dollars".
- **Counts differ from the brief.** The robustness card computes its counts live from the sensitivity table: now 17 of 20 settings beat the baseline on human harm (the 3 that do not set alpha to 0), 20 of 20 on cost, 20 of 20 cut more households. (The brief said 16 of 19; the county-cap row made it 20 settings.)
- **Pre-solved grid is now 40 records** (cap OFF and ON x 5 alphas x Elliott/10/15/20%), because the first capped live solve took 2.2 s and tripped the 2 s limit. Off-grid settings (the 7.5/12.5/17.5% slider stops) solve live; if that errors, is infeasible, or takes over 2 s the app shows the nearest pre-solved result with a visible note.
- **Offline maps.** Streamlit's frontend falls back to Carto basemap tiles from the internet when no map style is given; a Playwright network log caught this. The maps use a blank inline style (a data: URL), and the browser check shows zero external requests. Maps have no basemap, so the zones and NC-08 outline are the only features.
- **Rendering bug.** `line_width_units="pixels"` drew huge solid lines in this deck.gl version; the maps use `line_width_min_pixels`. Protected zones are drawn with real diagonal hatch lines (deck.gl has no fill patterns).
- **Wording fix.** The brief's follow-up "request feeder data" contains a banned word, so the card says "request utility network data". The rule-4 sentence contains "circuit" and is shown verbatim, so the banned-word check exempts that exact sentence.
- **Not built yet:** the fixed demo-location lookup and the node panel (nodes are disabled in config).
- **Dev tooling:** Playwright is in `requirements-dev.txt` only (not needed to run the app); `scripts/app_screenshots.py` makes `docs/figures/app_*.png` at 1440 px wide (the page is taller than 900 px, so the viewport grows to the content height) and checks horizontal scroll, external requests, console errors and banned words.

## Data-source failures and fallbacks
See
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
- **Timing caveat.** We use each utility's maximum shed. DEC had reached 1,000 MW by 7:01 (the reference hour). DEP was at about 600 MW at 07:00 and reached 961 MW at 7:56, so using 961 MW against 07:00 demand is generous to DEP. Using 600 MW instead lowers T_NC08 from 91.9 to about 78 MW (DEP term 36.8 -> 23.0 MW). Default stays at the maximum so both utilities use the same definition; the 600 MW DEP case is a sensitivity row in the frozen constants and the app. The earlier "NCUC Docket M-100 Sub 163" citation was replaced by these two reports.

**EIA-930 demand at 07:00 local (EST), 2022-12-24.** DEC (DUK) 20,879 MW. DEP 13,986 MW = CPLE 12,711 + CPLW 1,275. EIA-861 lists DEP as one utility whose territory spans both Progress East and West, so DEP demand is CPLE + CPLW and is scaled over the whole DEP footprint; this avoids needing an east/west county list (no authoritative one was found; NC-08 DEP counties are all in CPLE). The spec's single `balancing_authority` became the `balancing_authorities` list in config (DUK -> CPLE + CPLW added together, which differs from the "[DUK, CPLE]" you suggested).

**Reduction ratios.** Definition: r_g = each utility's maximum firm load shed that morning / its demand at 07:00. It is not a 07:00 snapshot of the shed. r_DEC = 1,000 / 20,879 = 0.04790. r_DEP = 961 / 13,986 = 0.06871. Observed demand is measured while shedding was already under way, so it is slightly below unconstrained demand.

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

## Phase 3: zones, allocation, freeze (2026-10-18)

- **Substation layer unavailable, zones are census tracts (`zone_mode: tract`).** The HIFLD Open Electric Substations layer is not reachable: the HIFLD ArcGIS org (`services1.arcgis.com/Hp6G80Pky0om7QvQ`) lists transmission lines but no substation layer, and the only substation copies found are third-party hosted and cover substations of 69 kV and above (transmission level, not distribution), so they would not make meaningful distribution zones. Per spec rule 2 the zones are census tracts, labeled "census tract zone (not a utility service boundary)". The Voronoi path is not implemented (`build_zones` raises NotImplementedError for `substation`). Consequence: a zone is a census tract, so zone sizes follow population, not electrical topology.
- **zone_id** is 1..183 in sorted-GEOID order (stable while the tract set is unchanged); GEOID is kept as a column. Tie-breaks use zone_id.
- **Whole tracts.** Zone geometry and attributes are whole tracts (decision 2026-10-18), including the parts outside NC-08. The area-weighted join (`geometry/allocate.py`) is implemented and tested for the substation case and for zones = tracts, but tract mode copies attributes as-is. Frozen geometry is simplified to ~10 m; areas are not recomputed from it.
- **Protected flags use option (a):** a zone is protected if it contains at least one hospital, nursing home or water treatment plant (OSM points). 26 of 183 zones are protected (hospital 12, nursing home 11, water treatment 4; some zones hold more than one type). Fire, police and wastewater points are counted per zone (`n_fire_station`, `n_police`, `n_wastewater_treatment`) for display only.
- **Protected-load check (zones, not tracts-as-proxy):** protected zones carry 278.8 MW = 16.5% of D_NC08 (15.0% of housing units). Unprotected zones hold 1,407.5 MW; T_NC08 (91.9 MW) is 6.5% of that. Well under the 35% limit, so the optimizer has room for the two plans to differ.
- **Load allocation.** W_i = housing units x 5.432 kW/unit + jobs x 1.391 kW/job; L_i = D_NC08 x W_i / sum_j W_j (so sum L_i = D_NC08 = 1,686.3 MW, tested). Every L_i is labeled "modeled district estimate". Average L_i = 9.2 MW (median 8.9, range 0.50 to 20.4 MW).
- **Zone 9 (GEOID 37007980000)** has 0 housing units, 431 jobs, no SVI or income. It keeps a small load (0.5 MW, from jobs) and `svi_missing = True`. Phase 4 must exclude it from SVI normalization and warn visibly; it must not be zero-filled.
- **Frozen files (`make freeze`).** `data/frozen/`: zones.geojson, facilities.geojson (protected flag), demand_groups.csv (DEC and DEP hourly), temp_kclt.csv, constants.json (D_NC08, T_NC08, per-utility parts, kW/unit and kW/job, sensitivity rows, dataset list, r definition). The app reads only these files (and the committed config.yaml).
- **App shell.** `streamlit_app.py` is only a Phase 3 shell (title, the district-scaling sentence, three numbers). A test renders it with socket connections blocked.

## Data-source failures and fallbacks
See the Phase 1 section above (TIGER file name, HIFLD -> OSM) the Phase 3 section (substation layer unavailable, tract zones), and the Phase 2 section (NREL bucket move, no ResStock county data, NCEI -> IEM for display temperature).
