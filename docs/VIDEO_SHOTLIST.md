# Video shot list

Target length: 3 minutes or less (confirm the current Congressional App Challenge video rules before recording). Record the browser at **1440 x 900**; the page is taller than the window, so scroll slowly between states. Start the app with `make demo`, and kill anything else on port 8765 first.

Say it plainly: this is a **modeled planning scenario**, not Duke's method, not a prediction, not an operational tool. Never say the plan "protects" people or "picks who loses power".

## States to record, in order

| # | Time | App state (URL after `http://localhost:8765/`) | What is on screen | Say (in your own words) |
|---|---|---|---|---|
| 1 | 0:00-0:18 | default: no query | The whole first screen, no scrolling: headline "Same power cut. Different people in the dark.", four tiles (92 MW cut by both plans; 3,412 fewer electric-heat homes in the dark; 73% less vulnerability-weighted harm; +2,543 more total homes cut), the controls bar, both maps | Winter Storm Elliott, 2022; two utilities shed load; the demand is the hour ending 07:00 (06:00-07:00). Many different megawatts-only plans meet the same MW target; we compare with 200 of them. Read the fourth tile out loud: the vulnerability-aware plan cuts MORE total homes. |
| 2 | 0:18-0:38 | same, the two maps | "Megawatts only (typical of 200 plans)" vs "Vulnerability-aware"; hover one cut zone in each (tooltip: zone, county, "cut in k of 200 megawatts-only plans", load, SVI, electric heat, households); the hatched protected zones | Zones are census tracts, not utility boundaries. Amber = cut, the same color on both maps; the map titles say which plan is which. Hatched = hospitals, nursing homes, water plants: never cut. The left plan is the typical one, not "the" baseline: there is no single baseline. |
| 3 | 0:38-0:58 | same, scroll to "Compared with 200 megawatts-only plans" | The honest lines (cuts 2,543 MORE households; MORE than 200 of 200) and four dot plots: grey dots = the 200 megawatts-only plans, light diamond = the typical one, blue circle = the vulnerability-aware plan | This is the main result: the blue dot is outside the grey cloud on electric-heat households and vulnerability-weighted households, lower on cost, and to the right (more) on total households. Say the last one out loud. |
| 4 | 0:58-1:12 | same, scroll to the flip list under the priority table | Expand "All 21 zones that differ between the two plans"; each line shows how often megawatts-only plans cut the zone | The vulnerability-aware plan concentrates its cut in one low-vulnerability county: say it. |
| 5 | 1:12-1:28 | `?alpha=1` then `?alpha=0` (or drag the slider to People at risk, then Business cost) | People at risk end: human harm only. Business cost end: the 73% tile flips sign and the sentence says "MORE electric-heat households" | The slider is a value judgment, not math. At the Business cost end the plan does worse on people at risk: show it. |
| 6 | 1:28-1:38 | `?cap=1` | "No county takes more than 50% of either plan's cut" | One answer to concentration; it limits any county's share, it does not make the plan fair. |
| 7 | 1:38-1:55 | default, scroll to the priority table, then "Look up a zone" (zone 69 is open) | Vulnerable zones most often cut when only megawatts count (10 zones, % of the 200 megawatts-only plans that cut each, and whether the vulnerability-aware plan cuts it), zone lookup with the formula, Example locations (Harrisburg Fire Department Station 3, Hemby Bridge Elementary, Robeson County Public Library) | A planner leaves with a short list for outreach and backup power: these are the zones the most load-only plans cut, not a finding about specific neighborhoods; the plan set is not a uniform sample, so the percentages are indicative. The fire station's zone is CUT in the typical load-only plan and kept on in the vulnerability-aware plan, the Union school's zone is the reverse, the library is kept on under both. They were chosen to illustrate differences: say so. |
| 8 | 1:55-2:05 | same, "How robust is this?" | 17 of 20 settings beat the typical plan on human harm; the 3 that do not set alpha to 0; counts against all 200 plans | I tried 20 settings. Say which ones lose, and that cost can come out higher at high alpha. |
| 9 | 2:05-2:25 | same, scroll to "Why forecasts aren't enough" | Predicted vs actual DUK+CPLE demand, Dec 22-26, Elliott morning marked; the sentence; the error-by-temperature table | A model trained on eight winters is typically within a few percent, yet it under-predicted the Elliott morning by about an eighth, and observed demand already excluded shed load. This is a modeled demand estimate, not a utility forecast, and it does not predict outages or available supply. |
| 10 | 2:25-2:32 | expand "Methods & sources" | The scaling sentence, the load-only comparison set, r definition, band, protected-facility rule, sources table | Every number is sourced; OpenStreetMap facilities are incomplete. |
| 11 | 2:32-2:50 | editor: `src/metric_grid/model/optimizer.py` lines 72-79, then line 89 (excerpt below) | The 9 lines | Same band for every plan; protected zones fixed to zero; the load-only plans and the vulnerability-aware plan differ only in the objective. |
| 12 | 2:50-3:00 | terminal | The one test below, five PASSED lines | Both plans land in the same band and never cut a protected zone, tested on the real zones. |

## Code to show on screen (src/metric_grid/model/optimizer.py)

First, lines 72-79 (8 lines): the model every plan shares.

```python
prob = pulp.LpProblem("shed", pulp.LpMinimize)
x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in ids}
for i in ids:
    if protected[i]:
        prob += x[i] == 0  # hard exclusion (PuLP ignores upBound on Binary variables, so state it as a constraint)
load = pulp.lpSum(L[i] * x[i] for i in ids)
prob += load >= lo
prob += load <= hi
```

Then scroll to line 89 (1 line): the objective, the only thing that differs between plans.

```python
prob += pulp.lpSum(objective[i] * x[i] for i in ids)
```

For the vulnerability-aware plan `objective[i]` is the harm score `H_i(alpha)`; the load-only plans use each zone's load `L_i` with a small random preference per zone (`model/loadonly.py`), which is how the 200 equivalent plans are generated. All are solved inside the same band `lo`..`hi`.

## The one test to run on camera

```bash
.venv/bin/python -m pytest tests/test_harm_optimizer.py -k real_both_plans_in_same_band -v
```

Five PASSED lines (one per alpha). Do not run the whole suite on camera (about 40 seconds on a quiet machine).

## Before recording

- `make test` is green; `make demo` opens the app; no other tab shows a different data version.
- Screenshots in `docs/figures/app_*.png` are current (`python scripts/app_screenshots.py` with the app running).
- Check every number you say against the screen, not memory. The numbers above come from the frozen model output.
