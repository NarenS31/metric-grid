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
| c_job | $21.8 per average kW (Medium and Large C&I, 1 hour, same table) x 1.3354 kW per job = $29.11 per job | ICE Table ES-1; kW per job from ComStock NC / LODES NC jobs (Phase 2) |
| h | 1 hour | judgment call; only 1 is supported because the ICE inputs are the 1-hour column |

- H_human_i = N_i x (w_s x SVI_i + w_e x EHeat_i)    [households x dimensionless, "vulnerability-weighted households"]
- H_econ_i = N_i x c_res x h + sum over sectors of J_i,s x c_job x h    [dollars]
- Hhat_human_i = H_human_i / max_j H_human_j; Hhat_econ_i = H_econ_i / max_j H_econ_j (max over zones with data)
- H_i(alpha) = alpha x Hhat_human_i + (1 - alpha) x Hhat_econ_i, alpha from the UI, default 0.5.

**ICE limitation.** The report gives costs by customer size class (Small C&I under 50,000 kWh/yr; Medium and Large C&I), not by NAICS sector, so manufacturing, retail, health and other all use one commercial rate. Choosing the Medium and Large class is a judgment call (most commercial kW sits in larger customers); the Small C&I rate ($295.0 per average kW, 13.5x higher) is a sensitivity case: with it the harm-weighted plan's interruption-cost change goes from -39% to -50% and the plan is the same (16 zones differ). Costs per average kW are applied to the ComStock kW in the cold-week hour ending 07:00, which is above an annual-average kW, so economic cost per job is likely overstated. Dollars are 2013 dollars.

**Worked example (zone_id 141, GEOID 37179020305, Union County).** N = 2,959; SVI = 0.0890; EHeat = 0.2856; jobs = 571.
H_human = 2,959 x (0.7 x 0.0890 + 0.3 x 0.2856) = 437.8. H_econ = 2,959 x $5.1 + 571 x $29.11 = $15,091 + $16,623 = $31,714.
max H_human = 2,018.9, max H_econ = $257,195, so Hhat_human = 0.2169, Hhat_econ = 0.1233, and H(0.5) = 0.1701. A test recomputes a zone from raw inputs.

**Missing data.** A zone with households but no SVI or electric-heat value gets NaN H_human, a visible MissingDataWarning, is excluded from the normalization maximum, and the optimizer raises MissingDataError rather than price it. Zone 9 (GEOID 37007980000) has no SVI but 0 occupied households, so H_human = 0 by definition (N_i = 0), not by a zero-fill; it is included in normalization as 0, a warning says so, and its H_econ is positive because it has 431 jobs.

## Optimizer, shared target band (Phase 4.2; changes the spec's "T*" rule, decided 2026-10-18)

Both plans use the same band: T_NC08 <= sum x_i L_i <= T_NC08 + delta, delta = 2% of T_NC08 (1.84 MW at T_NC08 = 91.93 MW), x_i = 0 for protected zones. The UI says "both plans cut between X and Y MW" and reports each plan's actual MW.
- **Stage A (load-only baseline):** minimize sum x_i L_i inside the band (least overshed). **Stage B (vulnerability-aware):** minimize sum x_i H_i(alpha) inside the same band. Ties: fewest zones, then lowest zone_id.
- If the band has no solution it is widened through 3%, 4%, 5% and the width used is reported; if still empty, or the target exceeds the unprotected load, the result is Infeasible with the maximum feasible reduction (unprotected load) and an explanation.
- **Tolerance.** Stage A is least-overshed within 10 kW (`load_tol_mw: 0.01`); loads within 10 kW count as tied and then go to the fewest-zones and lowest-zone_id rules. A 0.1 kW tolerance made the solve about 10 s.
- **Why a band (the reason differs from the first assumption; the experiment numbers here are from the first run, before the hour-ending correction, and the conclusion does not depend on them).** The check done before this change found that exact equality (sum within 1e-6 of Stage A's optimum) is NOT infeasible: with 157 selectable zones, a subset-sum count finds about 5 x 10^12 subsets at 0.1 kW resolution (about 5 x 10^16 per MW), and Stage A's optimum overshoots T_NC08 by only 5 to 13 kW. Solving Stage B under exact equality with CBC also returned a plan different from Stage A's (10 zones vs 6; harm sum 1.100 vs 2.411 in normalized units). The real problem is run time: that solve took about 34 s, against about 0.5 s for the band, and the 2% band loses nothing (harm sum 1.017, lower than the equality solve). The band is kept because load is shed in discrete blocks and operators cannot hit an exact MW, and because it is about 60 times faster.
- **Run time.** Default scenario (T_NC08, 183 zones): about 0.5 to 0.6 s for both plans. The 10, 15 and 20% presets take 2 to 3 s (Stage A's tie-break solve dominates); the app must pre-solve those, see Phase 4 step 5. Tests assert under 2 s for the default.
- **Bug found by tests:** PuLP ignores `upBound` on Binary variables, so an early version selected protected zones. The hard exclusion is now an explicit `x_i == 0` constraint and tests cover it.

**Default scenario result (alpha = 0.5, band 91.93 to 93.77 MW), against the load-only plan set (N = 200):**

| | Typical load-only plan | Range over the 200 load-only plans | Vulnerability-aware plan |
|---|---|---|---|
| MW cut (overshoot) | 92.25 (0.32) | 91.93 to 92.85 | 92.20 (0.27) |
| Zones cut | 11 | | 10 |
| Households | 15,413 | 13,387 to 17,458 | 17,956 |
| Electric-heat households | 8,896 | 6,874 to 11,454 | 5,484 |
| Vulnerability-weighted households | 7,741 | 4,784 to 11,116 | 2,053 (-73% vs typical) |
| Interruption cost (1 h, 2013$) | $417,615 | $260,199 to $731,161 | $264,733 (-37% vs typical) |

The vulnerability-aware plan has fewer electric-heat households than all 200 of 200 load-only plans, fewer vulnerability-weighted households than 200 of 200, lower interruption cost than 199 of 200, and MORE total households cut than 200 of 200 (+2,543 vs the typical plan). 21 zones differ from the typical plan; the vulnerability-aware plan's mean SVI is 0.03 vs 0.49. Alpha sweep: at alpha 0 (economic only) the weighted plan imposes +52% human harm while changing economic cost by -65%; at alpha 1 it changes human harm by -83% and cost by +9% (all vs the typical plan).

## Sensitivity, scenarios, pre-solved grid (Phase 4 steps 3-4; all in data/frozen/)

**Spec deviation (approved 2026-10-18): the demo safety-net grid is pre-solved at `make freeze`, not at app startup.** The 10/15/20% presets take 2 to 3 s per solve, so solving 15 points at startup would take about 40 s. `presolved.json` holds 20 points: alpha {0, .25, .5, .75, 1} x targets {Elliott T_NC08, 10%, 15%, 20% of D_NC08}; the Elliott row is added because it is the default scenario. The app falls back to the nearest point (with a visible "showing nearest pre-computed setting" note) if a live solve errors or exceeds 2 s.

**Sensitivity settings (20, vulnerability-aware plan vs the TYPICAL load-only plan of each setting's plan set, at T_NC08 = 91.9 MW):** alpha {0, .25, .5, .75, 1} x w_svi {.5, .7, .9} (15); band 1% and 5% (2% is in the grid); Small C&I cost rate; flat allocation weights (1 per housing unit + 1 per job instead of the modeled kW, renormalized to the same D_NC08; it has its own plan set); county-share cap 50% (below; it has its own plan set). In every setting the load-only side is the plan set evaluated under that setting's harm weights and cost class, and each row also counts how many of the 200 plans the vulnerability-aware plan beats.
- **Zone classes by the weighted plan's cuts:** always cut in every setting: 0. Sometimes: 36. Never cut although selectable: 121. Protected (never selectable): 26. The most frequently cut zones are 144 and 178 (16 of 20 settings each).
- **Human harm:** the weighted plan has fewer vulnerability-weighted households than the typical plan in 17 of 20 settings (-52% to -91%), and fewer than 200 to 200 of the 200 plans in the 17 settings with alpha > 0. It is HIGHER (+50% to +54%) in the 3 alpha = 0 settings, where human harm is ignored by construction. **Electric-heat households:** fewer than 188 to 200 of 200 plans in those settings. **Interruption cost:** lower than the typical plan in 16 of 20 settings; higher where alpha is high (alpha 0.75, w_svi 0.5: +5%, alpha 1, w_svi 0.5: +10%, alpha 1, w_svi 0.7: +9%, alpha 1, w_svi 0.9: +9%); cost-beating counts range from 72 to 200 of 200.
- **Households:** the weighted plan cuts MORE total households than the typical plan in 20 of 20 settings (+109 to +2,543; +2,543, +16%, in the default setting). Every UI place that shows vulnerability or cost results states this next to those numbers (`scenarios.plain_summary` says "MORE" or "fewer" as the data says).
- **Band 1% / 2% / 5%:** identical plans. **Small C&I cost rate:** same plan, interruption cost change -48% instead of -37%. **Flat allocation:** human harm -79%, cost -7%, +2,421 households vs its typical plan; the allocation assumption matters for sizes, not for direction.
- **Priority list ("Vulnerable zones most often cut when only megawatts count"), the definition used by the planning-implications card.** Among unprotected zones with SVI >= 0.75 OR electric-heat share >= 50% (config `priority_list`; judgment calls), rank by how many of the 200 default load-only plans cut the zone (ties: higher SVI, then lower zone id); show the top 10 and whether the vulnerability-aware plan cuts the zone (default setting; the app also gives the number of the 20 settings). A zone with no SVI never qualifies on SVI. **Weakness:** the 200 plans are a deterministic, near-optimal set, not a uniform sample of all load-only plans, so the frequencies are indicative, not exact; the card says so. No zone is cut by more than 12% of the plans, so this is a list to read, not a ranking to trust to the last place.

  | Zone | County | SVI | Electric-heat share | Households | Cut by load-only plans | Vulnerability-aware plan cuts it |
  |---|---|---|---|---|---|---|
  | 69 | Montgomery | 0.37 | 92% | 621 | 24 of 200 | No |
  | 87 | Robeson | 0.91 | 70% | 842 | 22 of 200 | No |
  | 86 | Robeson | 0.99 | 72% | 1,215 | 19 of 200 | No |
  | 85 | Richmond | 0.82 | 78% | 1,790 | 19 of 200 | No |
  | 17 | Cabarrus | 0.05 | 61% | 1,539 | 19 of 200 | No |
  | 111 | Scotland | 0.97 | 73% | 2,246 | 18 of 200 | No |
  | 66 | Montgomery | 0.94 | 76% | 1,892 | 18 of 200 | No |
  | 122 | Stanly | 0.50 | 70% | 1,502 | 18 of 200 | No |
  | 64 | Mecklenburg | 0.19 | 63% | 945 | 18 of 200 | No |
  | 159 | Union | 1.00 | 59% | 1,241 | 17 of 200 | No |
- **Where the cuts land (default).** Typical load-only plan: Stanly 3 zones (25.5 MW, 28%, 4,017 households, mean SVI 0.61), Montgomery 2 zones (16.3 MW, 18%, 2,441 households, mean SVI 0.76), Anson 2 zones (12.9 MW, 14%, 1,996 households, mean SVI 0.52), Mecklenburg 1 zone (12.8 MW, 14%, 2,250 households, mean SVI 0.04), Union 1 zone (11.5 MW, 12%, 2,074 households, mean SVI 0.04), Cabarrus 1 zone (7.5 MW, 8%, 1,539 households, mean SVI 0.05), Scotland 1 zone (5.9 MW, 6%, 1,096 households, mean SVI 0.83). Vulnerability-aware: Union 9 zones (81.5 MW, 88%, 15,910 households, mean SVI 0.04), Mecklenburg 1 zone (10.7 MW, 12%, 2,046 households, mean SVI 0.01). The weighted plan concentrates its cuts in one county with very low vulnerability, which is a fairness concern of its own (cumulative burden on one place), and it is a version 2.0 item.

**Scenarios (alpha 0.5, vs the typical plan of each target's set):**

| Target | MW | Zones cut (typical / vulnerability-aware) | Households (typical / vulnerability-aware) | Human harm | Interruption cost (2013$) | Plans it cuts more total households than |
|---|---|---|---|---|---|---|
| 10% of D_NC08 | 168.7 | 18 / 18 | 28,407 / 30,405 | -70% | -39% | 193 of 200 |
| 15% of D_NC08 | 253.0 | 29 / 28 | 42,569 / 46,076 | -66% | -31% | 199 of 200 |
| 20% of D_NC08 | 337.3 | 36 / 38 | 56,861 / 61,359 | -63% | -25% | 200 of 200 |

Zones cut in all three scenarios: typical plans 3, weighted 18. Zones cut only in the 20% scenario: typical 22, weighted 10.

**Alpha sweep (`docs/figures/alpha_tradeoff.png`, T_NC08, default weights, vs the typical plan):**

| alpha | Human harm change | Interruption cost change | Households cut change |
|---|---|---|---|
| 0 | +52% | -65% | +2,286 (+15%) |
| 0.25 | -61% | -51% | +1,339 (+9%) |
| 0.5 | -73% | -37% | +2,543 (+16%) |
| 0.75 | -81% | -7% | +1,802 (+12%) |
| 1 | -83% | +9% | +1,232 (+8%) |

**Dollar labeling.** Every dollar figure in the UI is labeled "2013 dollars" (ICE report dollars, not inflated).

## Baseline plan instability and the load-only plan set (found and addressed 2026-10-19)

**The problem.** Changing the load weights by about 0.2% (the NREL hour correction) left the vulnerability-aware plan unchanged but changed 3 of the 6 zones of the single "load-only baseline", and with them the headline (3,353 -> 4,545 fewer electric-heat households), the priority list, the cost count in the robustness card, and the example-location zones. With 157 selectable zones there are on the order of 10^16 zone sets per MW inside the band, so "the set that cuts the least MW, then fewest zones, then lowest ids" is decided by tiny numerical differences: one arbitrary member of a huge family of equally valid load-only plans.

**What the app does now.** It compares the vulnerability-aware plan with a SET of equivalent load-only plans:
- **Definition.** A load-only plan is any set of unprotected zones whose load lies in [T, T x 1.01] (it meets the target and overshoots by at most 1% of the target: optimal or near-optimal for the load-only objective). With the county cap on the cap applies to these plans too.
- **Generation (deterministic, `model/loadonly.py`).** Plan 0 is the exact optimum of the old load-only objective. The other 199 come from one CBC solve each of min sum c_i x_i inside the same band, with c_i = L_i x u_i and u_i drawn from a generator with fixed seed 20261019 (uniform on [0.5, 1.5]); duplicates are discarded. 200 distinct plans per setting (199 solves), 157 of the 157 selectable zones used, mean overlap between plans (Jaccard) 0.034. Plan sets are frozen by `make freeze` (`data/frozen/loadonly_plans.json`, nine sets: the four targets x cap off/on, plus the flat-allocation sensitivity).
- **Why it is representative, and what it is not.** Each random cost vector is a different "preference" among equivalent zones, so the set spreads over the whole near-optimal family (all selectable zones appear, plans overlap very little). It is NOT a uniform sample of that family (uniform sampling of subset-sum slices is not practical); a test checks that a fresh set with another seed has medians within 5%.
- **Typical plan.** The member closest to the median on all four displayed measures (households, electric-heat households, vulnerability-weighted households, interruption cost): distance = sum of |percentile rank - 0.5|, ties to the lowest index. (Choosing the plan closest to the median on human harm alone gave a plan at about the 85th percentile for electric-heat households and would have overstated the headline gap by about 1,400 households.) It is shown on the left map and is the plan the headline, the flip strip and the percent changes refer to.
- **Headline and range line.** "Same 92 MW cut. 3,412 fewer electric-heat households than the typical load-only plan." Under it: "Across 200 equivalent load-only plans, they cut 6,874-11,454 electric-heat households; the vulnerability-aware plan cut 5,484. It cuts MORE total households than 200 of 200."
- **Strip charts.** Four dot plots (electric-heat households, vulnerability-weighted households, cost, total households) show all 200 plans, the typical plan (diamond) and the vulnerability-aware plan (circle).
- **Every number that used to refer to "the baseline" now refers to the typical plan**, and the cut frequency of each zone (how many of the 200 plans cut it) is shown in tooltips, the flip strip, the zone detail and the example-locations table.

**Result.** Against the 200 plans (default setting): electric-heat households 6,874 to 11,454 (median 9,067) vs 5,484; vulnerability-weighted households 4,784 to 11,116 (median 7,680) vs 2,053; cost $260,199 to $731,161 (median $420,919) vs $264,733; total households 13,387 to 17,458 (median 15,516) vs 17,956. The directions are robust (the vulnerability-aware plan is outside the load-only range on three of the four measures and cuts MORE total households than every plan), while the size of any gap depends on which plan you compare with, which is why the page shows the range. `scripts/baseline_spread.py` is an earlier, simpler version of this check.

**The vulnerability-aware plan is one optimum.** It is a single optimum of its objective; no distribution of equivalent vulnerability-aware plans was generated, so only the load-only side is shown as a range.

**Remaining weaknesses.** The set depends on the near-optimality tolerance (1%) and the cost spread (0.5); the priority list's frequencies are indicative because the plan set is not a uniform sample; and example locations illustrate this particular typical plan.

## County-share cap (optional, default OFF; added 2026-10-18)

In the default scenario the typical load-only plan puts 28% of its cut in Stanly County and the weighted plan puts 88% in Union County. As a response to cumulative-burden concentration the optimizer has an optional constraint (`optimizer.county_cap`, enabled: false, max_share: 0.5): no single county may take more than 50% of the total MW cut. It is linear (county MW <= share x total MW cut), applied to BOTH plans equally, and changes the baseline too. Infeasible if the unprotected load is in too few counties (the result says so). Solve time about 1.3 s (the default without the cap is about 0.5 s). It limits concentration by county only; it does not make the weighted plan spread cuts to vulnerable counties.

**Default scenario with the cap ON (alpha 0.5, band 91.93 to 93.77 MW, T_NC08 = 91.9 MW; the cap applies to the load-only plans too, so the set is different):**

| | Typical load-only plan | Vulnerability-aware | Vulnerability-aware vs typical |
|---|---|---|---|
| MW cut | 92.25 | 91.95 | |
| Zones cut | 11 | 10 | |
| Households cut | 15,413 | 15,522 | +109 (+0.7%) MORE households |
| Electric-heat households | 8,896 | 5,468 | -3,428 |
| Vulnerability-weighted households | 7,741 | 2,316 | -70.1% |
| Interruption cost (2013 dollars) | $417,615 | $263,819 | -36.8% |

Counties (share of MW cut): typical plan Stanly 3 zones (25.5 MW, 28%, 4,017 households, mean SVI 0.61), Montgomery 2 zones (16.3 MW, 18%, 2,441 households, mean SVI 0.76), Anson 2 zones (12.9 MW, 14%, 1,996 households, mean SVI 0.52), Mecklenburg 1 zone (12.8 MW, 14%, 2,250 households, mean SVI 0.04), Union 1 zone (11.5 MW, 12%, 2,074 households, mean SVI 0.04), Cabarrus 1 zone (7.5 MW, 8%, 1,539 households, mean SVI 0.05), Scotland 1 zone (5.9 MW, 6%, 1,096 households, mean SVI 0.83). Weighted: Union 5 zones (45.6 MW, 50%, 8,946 households, mean SVI 0.04), Montgomery 2 zones (26.2 MW, 29%, 2,727 households, mean SVI 0.18), Mecklenburg 2 zones (18.8 MW, 20%, 3,600 households, mean SVI 0.02), Anson 1 zone (1.3 MW, 1%, 249 households, mean SVI 0.21). Against the 200 capped load-only plans, the vulnerability-aware plan has fewer vulnerability-weighted households than 200, fewer electric-heat households than 200, and more total households than 102.

The cap is a sensitivity row (`county-share cap 50%`) in the sensitivity table; the pre-solved demo grid also holds the capped results.

## App (Phase 4 step 5; `make app`)

- **Everything on the page is computed**: headline, honest line, flip-strip sentences, metrics and the robustness counts are built from model results and `data/frozen/` (tests compare the page text with the model output). The headline flips wording with the numbers: at alpha = 0 it reads "N MORE electric-heat households in the dark" and the honest line says "50% more vulnerability-weighted households".
- **Honesty line.** The sentence from `scenarios.plain_summary`, which says "cuts N MORE households" when that is what the numbers say, sits directly under the headline in every state. Dollar figures are labeled "2013 dollars".
- **Counts differ from the brief.** The robustness card computes its counts live from the sensitivity table: 17 of 20 settings beat the typical load-only plan on human harm (the 3 that do not set alpha to 0), 16 of 20 on cost, 20 of 20 cut more total households; against all 200 plans the numbers are on the card. (The brief said 16 of 19.)
- **Pre-solved grid is now 40 records** (cap OFF and ON x 5 alphas x Elliott/10/15/20%), because the first capped live solve took 2.2 s and tripped the 2 s limit. The reduction slider has only the four pre-solved stops (Elliott default, 10%, 15%, 20%), so normal use never solves live. The live-solve path remains as a safety net (if config adds a stop, or a lookup misses): when it errors, is infeasible, or takes over 2 s the app shows the nearest pre-solved result with a visible note.
- **Offline maps.** Streamlit's frontend falls back to Carto basemap tiles from the internet when no map style is given; a Playwright network log caught this. The maps use a blank inline style (a data: URL), and the browser check shows zero external requests. Maps have no basemap, so the zones and NC-08 outline are the only features.
- **Rendering bug.** `line_width_units="pixels"` drew huge solid lines in this deck.gl version; the maps use `line_width_min_pixels`. Protected zones are drawn with real diagonal hatch lines (deck.gl has no fill patterns).
- **Wording fix.** The brief's follow-up wording used a banned term, so the card says "request utility network data". The required rule-4 sentence contains one banned word and is shown verbatim, so the banned-word check exempts that exact sentence.
- **Not built:** the node panel (nodes are out of this submission; the empty `nodes/` stubs and the `nodes` config block were deleted 2026-10-19).
- **Dev tooling:** Playwright is in `requirements-dev.txt` only (not needed to run the app); `scripts/app_screenshots.py` makes `docs/figures/app_*.png` at 1440 px wide (the page is taller than 900 px, so the viewport grows to the content height) and checks horizontal scroll, external requests, console errors and banned words.

## Phase 6: demo locations, states, audit (2026-10-19)

- **Example locations (config `example_locations`; the app card is titled "Example locations").** Three public buildings, no home addresses, no live geocoder: Wolf Meadow Elementary School (Cabarrus, zone 23), Hemby Bridge Elementary School, Indian Trail (Union, zone 141) and the Robeson County Public Library, Lumberton (zone 100). **They were chosen to illustrate differences between the plans**, not at random: in the default scenario the baseline cuts zone 23 and the vulnerability-aware plan spares it, the vulnerability-aware plan cuts zone 141 and the baseline does not, and zone 100 is kept on under both. The school locations are the OpenStreetMap record's name, street address and centroid (pulled via Overpass on 2026-10-19; each point lies inside its zone, which a test checks); the library's coordinates are the US Census Geocoder result for its street address (benchmark Public_AR_Current, 2026-10-19), and that the address is the library is from public knowledge, so the author should verify it. A school near the author's own was deliberately not used. Each location is reported as the status of the census tract zone it sits in. (An earlier set of three buildings was replaced because all three read "kept on" under both plans.)
- **Zone detail opens on the top priority zone** (the first row of the priority list, read from sensitivity.json, not typed).
- **States.** Empty (no zone selected; `?zone=0`), loading (live solves show a spinner), infeasible (an orange note with the model's reason and the maximum feasible MW, plus the nearest pre-computed result), missing data (zone 9 has no SVI: a visible data note and a grey zone), missing frozen files (the page says to run `make data` and `make freeze`; no stack trace). Tests cover each.
- **Tooltips** for SVI, ICE, census tract zone and target band are native hover text (definitions in `app/copy.py`; the band tooltip fills its percentages from config).
- **Audit (`tests/test_audit.py`).** Banned-word check over every tracked text file (exempt: the brief, CLAUDE.md and the files that define the banned list; the required rule-4 sentence is removed before checking); AI_DISCLOSURE lists every tracked file; no model numbers typed into app strings (only label facts such as years and dataset names); README table and shot-list numbers match the model; the shot-list code excerpt matches optimizer.py line for line.
- **App figure** in the robustness card is a compact version with larger type (data/frozen/alpha_tradeoff.png); the wide version is docs/figures/alpha_tradeoff.png.

## Housekeeping decisions (2026-10-19)

- **Requirements.** `requirements.txt` has only what the app imports at runtime (streamlit, geopandas, shapely, pandas, numpy, pydeck, pulp, PyYAML), pinned. `requirements-dev.txt` adds pytest, matplotlib, requests and Playwright. `requirements-node.txt` holds the unused node packages (fastapi, uvicorn, httpx, python-kasa). scipy and pyarrow are unused by any code and are listed only as comments in the dev file. A fresh environment built from `requirements.txt` alone renders the app (checked).
- **Citations.** The NCUC docket citation was removed. Each remaining prior-work entry's title and authors were confirmed from arXiv or Crossref records (the "UT Austin" entry was identified through the university's news release and confirmed in Crossref: Toplu-Tutay, Hasenbein, Kutanoglu, 2024). They were not read in full by the assistant; the author should read them before describing them in the video.
- **Hardware prototype.** The three empty firmware placeholders and the throwaway test sketches were deleted; the README has a one-line note that the prototype is in progress and not part of this submission.

## Winter demand model (branch `demand-model`; added 2026-10-19)

A modeled demand estimate: hourly DUK and CPLE demand from temperature and calendar. **Not a utility forecast; it does not predict outages or available supply.** The app shows it as the panel "Why forecasts aren't enough" (precomputed curve only; no scikit-learn at runtime; hidden if `data/frozen/demand_panel.json` is missing). The panel sentence says the ~1,961 MW shed was the maximum reached by 7:56 a.m. and was still ramping up during the hour ending 07:00 (about 400 MW of DEC from 6:27 and 600 MW of DEP from 6:50 were in effect), not an amount already excluded from that hour's demand.

**Data.** EIA-930 hourly demand for DUK and CPLE (CPLW is not included), winters 2018 to 2025 (winter Y = Dec Y-1, Jan Y, Feb Y; 8 winters, 17,328 hourly rows, `data/frozen/demand_training.csv.gz`, 185 KB). The EIA API's hourly region data starts at **2019-01-01**, so Dec 2017 to Dec 2018 come from EIA's own bulk CSV files (the spec's documented fallback; the same EIA-930 data); the API is used for Jan 2019 onward. On the 2,846 hours both cover (Jan-Feb 2019) the two sources are identical (MAE 0.0 MW, 100% exact), so mixing them adds no error. Temperature: Iowa Environmental Mesonet archive of NOAA ASOS reports, **KCLT** (Charlotte) for DUK and **KRDU** (Raleigh-Durham) for CPLE; each report is assigned to the nearest hour, gaps up to 3 hours are interpolated, longer gaps stay missing (a handful of hours: CPLE 24 missing in winter 2019, 4 missing temperature hours in each of 2020 and 2023). Nothing is zero-filled; rows with missing inputs are dropped from fitting and scoring.

**Hour convention (a correction to earlier wording).** EIA labels each hour by the UTC time at its **end**: the API `period` equals the bulk files' "UTC Time at End of Hour" on every overlapping hour (and is off by about 332 MW if shifted by one hour). So the "07:00 EST" demand used throughout this project (20,879 MW DUK) is the hour ending 07:00, that is 06:00 to 07:00 local. It also fits the ORS report's "6:00 to 7:00 AM" peak. Effect on the district scaling (applied 2026-10-19): the NREL load profile had been taken for 07:00-08:00; it now uses the matching 06:00-07:00 hour, which changed D_NC08 from 1,686.3 to 1,686.7 MW and T_NC08 from 91.91 to 91.93 MW. All wording in the app and docs now says "the hour ending 07:00 (06:00 to 07:00)".

**Design, fixed before the holdout was scored (and never changed after).** Features: heating degree-hours (HDH = max(0, 65 F minus temperature)), hour-ending, weekend, US federal holiday (observed), holiday week (Dec 24 to Jan 1), linear trend. Baseline: ordinary least squares on those features. Boosted: scikit-learn `HistGradientBoostingRegressor` (fixed seed, no early stopping) on temperature, HDH, calendar features and HDH lagged 3 hours. Selection: **leave-one-winter-out cross-validation on the training pool only**; the boosted model replaces the baseline only if its mean CV MAPE is lower by at least 0.5 percentage points (prefer the simple model if close). Holdout: **all of Dec 2022 (local)** is excluded from every fit, every CV fold and the selection, and scored once afterwards. Jan-Feb 2023 stay in the training pool. A test poisons the holdout demand and checks that CV numbers and the chosen model do not move.

**A bug found by a test, fixed after the first full run:** winter labels used the hour-end timestamp, so each winter held one stray Nov 30 hour and lacked its last Feb hour. This was a labeling error, not a modeling choice; the model design was not touched and the numbers moved by about 0.1 point or less.

**Leave-one-winter-out CV (training pool, 8 folds):**

| Model | DUK MAPE | CPLE MAPE | Mean MAPE | DUK MAE | CPLE MAE |
|---|---|---|---|---|---|
| Linear baseline | 5.03% | 7.88% | 6.45% | 619 MW | 561 MW |
| Boosted | 3.51% | 5.28% | 4.40% | 444 MW | 399 MW |

The gap (2.06 points) is well beyond the 0.5-point "close" threshold, so the **boosted model is the chosen one**, on CV evidence alone. Per-winter boosted MAPE ranges 2.9% to 3.9% (DUK) and 4.0% to 8.4% (CPLE; the worst fold is winter 2025).

**Holdout, Dec 2022 (boosted; MAE in MW, MAPE in %, bias = predicted minus actual; "storm days" = Dec 23 to 25, defined in advance):**

| Series | Slice | Hours | MAE | MAPE | Bias |
|---|---|---|---|---|---|
| DUK | all dec 2022 | 741 | 548 | 3.94% | -374 |
| CPLE | all dec 2022 | 741 | 402 | 5.02% | -245 |
| DUK+CPLE | all dec 2022 | 741 | 851 | 3.85% | -619 |
| DUK+CPLE | dec 2022 excluding storm days | 669 | 756 | 3.61% | -543 |
| DUK+CPLE | storm days dec 23 to 25 | 72 | 1,731 | 6.06% | -1,326 |

**The Elliott morning (Dec 24, 2022, hour ending 07:00 EST, about 10 F at KCLT and KRDU), boosted model:** DUK actual 20,879 MW, predicted 17,711 (-15.2%); CPLE actual 12,711, predicted 11,658 (-8.3%); **DUK+CPLE actual 33,590 MW, predicted 29,369 MW, error -4,221 MW (-12.6%)**. (The linear model, not chosen, scores 5.73% MAPE on all of Dec 2022 and -15.0% on the Elliott morning.)

**Honest reading.**
- Overall the model passes the ~5% gate: holdout MAPE 3.85% for DUK+CPLE (3.94% DUK, 5.02% CPLE, just above 5% alone), and 3.61% on the non-storm days.
- **It misses the Elliott morning badly**: it under-predicts by 4,221 MW (12.6%), and storm-day MAPE is 6.1% with a bias of -1,326 MW. Load shedding does not explain the miss, it makes it larger: shedding lowered the observed demand, so unconstrained demand was higher still (at most about 35,551 MW if the maxima of 1,000 and 961 MW are added back), and the model's shortfall against that would be about 17%.
- **Cause, from training data alone (no holdout):** out-of-fold CV error by temperature bin (boosted, DUK+CPLE) is -8.1% below 20 F (only 109 hours of training data), -4.1% at 20-25 F, -2.7% at 25-30 F, and under 2% above 30 F. Extreme cold is rare in the data, and the model is biased low there (the linear baseline is worse: -14.5% below 20 F). The coldest training hour is 10.9 F at KCLT; the Elliott morning (about 10 F, after a rapid fall) is at or just beyond the edge.
- Also unmodeled: the hour-before temperature trend (the fall was rapid), wind, and Christmas Eve behavior (Saturday plus holiday week are in the features, but there is no Christmas Eve-specific feature).

**Limits.** Two single-city temperatures stand in for two large territories; CPLW (Progress West) is excluded; no wind, humidity, solar or behind-the-meter effects; demand during load shedding is observed demand, not unconstrained demand; one holdout month, so the holdout MAPE is a single-sample estimate. The shipped model is trained on the pool (Dec 2022 excluded).

**Files.** `src/metric_grid/ingest/demand_history.py` (data), `src/metric_grid/train/demand.py` (features, models, protocol; scikit-learn, build time only), `data/frozen/demand_training.csv.gz`, `demand_training_report.json`, `demand_validation.json`, `tests/test_demand_model.py`; `make demand` rebuilds everything (network + EIA key), `make demand-train` retrains offline from the frozen table. scikit-learn is in `requirements-dev.txt` only: a boosted model would need a runtime dependency or a pickle, so an app panel would ship a precomputed curve instead.

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
- **EIA-930 series.** API v2 region-data, respondents DUK, CPLE and CPLW (one cached response each), type D, hourly, 2022-12-22 to 2022-12-26 (120 rows per respondent, no gaps; each hour is labelled by its END, see the demand-model section). `period` is UTC and is the END of the hour: the label 12:00 UTC is the hour ending 07:00 EST (06:00 to 07:00 local). Check: demand peaks at 20,879 MW in that hour on 2022-12-24. The API was slow (~50 s) and returned one HTTP 504 during testing; the loader retries (4 attempts). The cached response is the output of the identical query. No bulk-CSV fallback was needed.
- **Observed demand caveat.** EIA demand in the hour ending 07:00 is measured while DEC was already shedding load, so it is slightly below unconstrained demand. We use it as given (spec).
- **Reduction ratios** are per group, see the Phase 3 prerequisite section: r_DEC = 1,000 / 20,879 = 0.0479; r_DEP = 961 / 13,986 = 0.0687. These are regional ratios; T_NC08 is computed from district-scaled load, never from regional MW.
- **NREL data moved.** The `nrel-pds-building-stock` bucket now only holds `comstock/athena/`; the load-profile data lives in `oedi-data-lake` under `nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/` (found by listing the bucket). Releases used: `resstock_amy2018_release_2`, `comstock_amy2018_release_2`, upgrade 0 (baseline).
- **ResStock has no county aggregates in any release.** Residential per-unit load is therefore statewide NC: ResStock NC total kWh / `units_represented` (all five building types) = **5.26 kW per housing unit**, averaged over the hour ending 07:00 (06:00 to 07:00) of the cold week (it was 5.43 kW before the 2026-10-19 hour correction). We apply the same per-unit value to every county (SC counties too, in Phase 3). Consequence: the residential part of W is proportional to housing units; ResStock only sets the residential-to-commercial ratio. Electric-heat share is not used in W (a possible refinement, not in the spec).
- **Cold week.** Coldest 7 days of AMY2018 from the Mecklenburg ComStock weather file: 2018-01-01 to 2018-01-07 (7-day mean -4.8 C, low -11.7 C = 11 F; Elliott morning at KCLT was ~10 F). AMY2018 is a different year from Elliott; this is a stated proxy. EULP timestamps are period-ending EST: the matching reference hour (ending 07:00, i.e. 06:00 to 07:00) is the rows stamped 06:15, 06:30, 06:45, 07:00; summed kWh over the hour = average kW; averaged over the 7 days. (Until 2026-10-19 the 07:00 to 08:00 hour was used by mistake; the correction changed D_NC08 from 1,686.3 to 1,686.7 MW and T_NC08 from 91.91 to 91.93 MW, and, through tie-breaks, the baseline plan: see "Baseline plan instability".)
- **Commercial per-job load uses the NC statewide ComStock total** (6,357 MW in that hour) / NC LODES 2023 jobs (4,760,483) = **1.34 kW per job**. Reason: ComStock county aggregates swing 5x per job (Mecklenburg 0.64, Robeson 3.49 kW/job; Robeson full-service restaurants alone are ~69 MW), which looks like county-model artifacts. County-scope is kept as a sensitivity (`weights.commercial_scope`). LODES jobs include sectors ComStock does not model (industry, government), so kW per job is a proxy.
- **NOAA KCLT.** NCEI Access Data Service returned HTTP 503 twice, so the fallback is the Iowa Environmental Mesonet archive of the same station's ASOS observations (display only; not used in any calculation). 72 hourly observations, 2022-12-23 to 25 local; the 07:52 observation on Dec 24 was 10 F. Rows with a missing temperature are dropped, not filled.
- **Data files are fetched with HTTP Range requests** (cold week only, ~0.3 MB per file) instead of full 15-40 MB files.

## Phase 3 prerequisite: two utilities, county assignment, district scaling (2026-10-18)

**Why two groups.** The SC Office of Regulatory Staff report (p.39, PDF p.49) and the FERC-NERC Elliott report (PDF p.71) both show Duke Energy Progress (DEP) also shed load on 2022-12-24. Four of NC-08's nine counties (Montgomery, Richmond, Robeson, Scotland) are DEP-only and two (Anson, Stanly) are shared with DEC. Using DUK alone would scale DEP territory by the wrong utility's demand.

**Sourced shed amounts (max firm load shed).**
- DEC 1,000 MW. ORS p.39: "a load shed of 400 MW was directed at 6:14 AM and implemented ... at 6:27 AM. Two (2) additional load shed requests of 300 MW each were implemented at 7:00 and 7:01 AM ... total load shed directive of 1,000 MW ... The amount of load shed was ultimately maintained at 1,000 MW." FERC-NERC PDF p.71: DEC "ordered 400 MW of firm load shed, later increasing it to 1,000 MW at 7:10 a.m."
- DEP 961 MW. FERC-NERC PDF p.71: "DEP ordered 600 MW of firm load shed at 6:25 a.m., but increased it to 800 MW at 7:10 a.m., up to a maximum of 961 MW by 7:56 a.m." ORS p.39: requests of 600 MW (6:25), 200 MW (7:10), 50 MW (7:43) and approximately 111 MW manual at transmission level (7:52), which sum to 961 MW. The two reports agree.
- **Timing caveat.** We use each utility's maximum shed. DEC reached its 1,000 MW only at about 7:00 to 7:10, just after the reference hour (ending 07:00). DEP was at about 600 MW from 6:50 and reached 961 MW at 7:56, so using 961 MW against the hour-ending-07:00 demand is generous to DEP (and DEC). Using 600 MW for DEP instead lowers T_NC08 from 91.93 to 78.1 MW. Default stays at the maximum so both utilities use the same definition; the 600 MW DEP case is a sensitivity row in the frozen constants and the app.

**EIA-930 demand in the hour ending 07:00 local (EST), 2022-12-24.** DEC (DUK) 20,879 MW. DEP 13,986 MW = CPLE 12,711 + CPLW 1,275. EIA-861 lists DEP as one utility whose territory spans both Progress East and West, so DEP demand is CPLE + CPLW and is scaled over the whole DEP footprint; this avoids needing an east/west county list (no authoritative one was found; NC-08 DEP counties are all in CPLE). The spec's single `balancing_authority` became the `balancing_authorities` list in config (DUK -> CPLE + CPLW added together, which differs from the "[DUK, CPLE]" you suggested).

**Reduction ratios.** Definition: r_g = each utility's maximum firm load shed that morning / its demand in the hour ending 07:00 (06:00 to 07:00). It is not a snapshot of the shed in that hour. r_DEC = 1,000 / 20,879 = 0.04790. r_DEP = 961 / 13,986 = 0.06871. Observed demand is measured while shedding was already under way, so it is slightly below unconstrained demand.

**County -> group assignment (EIA Form 861, data year 2024; `Service_Territory_2024.xlsx` and the BA Code column of `Sales_Ult_Cust_2024.xlsx`; https://www.eia.gov/electricity/data/eia861/).**
- A county belongs to a group if any utility serving it is that group's own utility (DEC 5416, DEP 3046) or has the group's BA code. So co-ops and municipals inside a footprint count as that BA's load (EIA-930 BA demand includes them). 143 county-group rows: NC 52 DEC + 59 DEP, SC 19 DEC + 13 DEP (counties may appear in both).
- **Shared counties** (served by both): 24 county pairs statewide. Rule (default `customer_spread`): EIA-861 gives customers per utility and state, not per county, so each utility's customers are spread across the counties it serves in proportion to housing units, and a group's share of a county is its utilities' spread customers over the total. This is an approximation. Sensitivity cases: equal split; and every shared county wholly to DEC or wholly to DEP.
- Counties are assigned wholly to our two groups; load served by utilities in other BAs inside those counties is not separated out. The GA slice of the DUK BA and the SC counties are in the footprint only where Duke itself appears in EIA-861 for that state.
- W (consistent modeled weight, kW) = housing units x 5.258 kW/unit + LODES jobs x 1.335 kW/job (statewide values; the same values are used for SC counties). Housing units: ACS 2024 5-year counties; jobs: LODES 2023 (NC and SC WAC).

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

**District scaling result (modeled district estimates).** D_NC08 = sum over groups of D_g (hour ending 07:00) x W_NC08-in-g / W_g, T_NC08 = sum of D_NC08,g x r_g.

| Quantity | DEC | DEP | NC-08 |
|---|---|---|---|
| Group demand, hour ending 07:00 (MW) | 20,879 | 13,986 | |
| W of the group (MW) | 23,633 | 17,053 | |
| W of NC-08 inside the group (MW) | 1,303 | 653 | 1,956 |
| Share of group | 5.5% | 3.8% | |
| D_NC08 part (MW) | 1,151.4 | 535.3 | **1,686.7** |
| r_g | 0.04790 | 0.06871 | effective 0.0545 |
| T_NC08 part (MW) | 55.1 | 36.8 | **91.93** |

Sensitivity of the shared-county rule: customer_spread D 1687 / T 91.9 MW; equal split D 1673 / T 94.6 MW; shared -> all DEC D 1611 / T 87.6 MW; shared -> all DEP D 1550 / T 90.8 MW. T_NC08 stays within about 5% of the default.

## Phase 3: zones, allocation, freeze (2026-10-18)

- **Substation layer unavailable, zones are census tracts (`zone_mode: tract`).** The HIFLD Open Electric Substations layer is not reachable: the HIFLD ArcGIS org (`services1.arcgis.com/Hp6G80Pky0om7QvQ`) lists transmission lines but no substation layer, and the only substation copies found are third-party hosted and cover substations of 69 kV and above (transmission level, not distribution), so they would not make meaningful distribution zones. Per spec rule 2 the zones are census tracts, labeled "census tract zone (not a utility service boundary)". The Voronoi path is not implemented (`build_zones` raises NotImplementedError for `substation`). Consequence: a zone is a census tract, so zone sizes follow population, not electrical topology.
- **zone_id** is 1..183 in sorted-GEOID order (stable while the tract set is unchanged); GEOID is kept as a column. Tie-breaks use zone_id.
- **Whole tracts.** Zone geometry and attributes are whole tracts (decision 2026-10-18), including the parts outside NC-08. The area-weighted join (`geometry/allocate.py`) is implemented and tested for the substation case and for zones = tracts, but tract mode copies attributes as-is. Frozen geometry is simplified to ~10 m; areas are not recomputed from it.
- **Protected flags use option (a):** a zone is protected if it contains at least one hospital, nursing home or water treatment plant (OSM points). 26 of 183 zones are protected (hospital 12, nursing home 11, water treatment 4; some zones hold more than one type). Fire, police and wastewater points are counted per zone (`n_fire_station`, `n_police`, `n_wastewater_treatment`) for display only.
- **Protected-load check (zones, not tracts-as-proxy):** protected zones carry 278.7 MW = 16.5% of D_NC08 (15.0% of housing units). Unprotected zones hold 1,408.1 MW; T_NC08 (91.9 MW) is 6.5% of that. Well under the 35% limit, so the optimizer has room for the two plans to differ.
- **Load allocation.** W_i = housing units x 5.258 kW/unit + jobs x 1.335 kW/job; L_i = D_NC08 x W_i / sum_j W_j (so sum L_i = D_NC08 = 1,686.7 MW, tested). Every L_i is labeled "modeled district estimate". Average L_i = 9.2 MW (median 8.9, range 0.50 to 20.4 MW).
- **Zone 9 (GEOID 37007980000)** has 0 housing units, 431 jobs, no SVI or income. It keeps a small load (0.5 MW, from jobs) and `svi_missing = True`. Phase 4 must exclude it from SVI normalization and warn visibly; it must not be zero-filled.
- **Frozen files (`make freeze`).** `data/frozen/`: zones.geojson, facilities.geojson (protected flag), demand_groups.csv (DEC and DEP hourly), temp_kclt.csv, constants.json (D_NC08, T_NC08, per-utility parts, kW/unit and kW/job, sensitivity rows, dataset list, r definition). The app reads only these files (and the committed config.yaml).
- **App shell.** `streamlit_app.py` is only a Phase 3 shell (title, the district-scaling sentence, three numbers). A test renders it with socket connections blocked.

## Data-source failures and fallbacks
See the Phase 1 section above (TIGER file name, HIFLD -> OSM) the Phase 3 section (substation layer unavailable, tract zones), and the Phase 2 section (NREL bucket move, no ResStock county data, NCEI -> IEM for display temperature).
