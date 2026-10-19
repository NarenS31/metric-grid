# Video shot list

Target length: 3 minutes or less (confirm the current Congressional App Challenge video rules before recording). Record the browser at **1440 x 900**; the page is taller than the window, so scroll slowly between states. Start the app with `make demo`, and kill anything else on port 8765 first.

Say it plainly: this is a **modeled planning scenario**, not Duke's method, not a prediction, not an operational tool. Never say the plan "protects" people or "picks who loses power".

## States to record, in order

| # | Time | App state (URL after `http://localhost:8765/`) | What is on screen | Say (in your own words) |
|---|---|---|---|---|
| 1 | 0:00-0:18 | default: no query | Top bar, headline "Same 92 MW cut. 4,545 fewer electric-heat households in the dark.", the honest line under it | Winter Storm Elliott, 2022; two utilities shed load; two plans, same MW band; the demand is the hour ending 07:00 (06:00-07:00). Read the honest line out loud, including "cuts 2,363 MORE households". |
| 2 | 0:18-0:40 | same, scroll to the two maps | Baseline vs vulnerability-aware map; hover one cut zone in each (tooltip: zone, county, load, SVI, electric heat, households); the hatched protected zones | Zones are census tracts, not utility boundaries. Dark = cut. Hatched = hospitals, nursing homes, water plants: never cut. |
| 3 | 0:40-0:58 | same, scroll to the metrics under the maps and the flip strip | MW cut, households, electric-heat households, vulnerability-weighted households, interruption cost (2013 dollars); "Where it lands" lines | More households cut, fewer vulnerable ones. Say the cut concentrates in one low-vulnerability county, and that the load-only baseline is one of many equal plans: the size of the gap moves, the direction does not. |
| 4 | 0:58-1:16 | `?alpha=1` then `?alpha=0` | alpha 1: human harm only. alpha 0: headline flips to "MORE electric-heat households" | The slider is a value judgment, not math. At alpha 0 the plan does worse on human harm: show it. |
| 5 | 1:16-1:28 | `?cap=1` | "No county takes more than 50% of either plan's cut" | One answer to concentration; it limits any county's share, it does not make the plan fair. |
| 6 | 1:28-1:50 | default, scroll to the three cards (zone 103 is open) | Where to plan first (6 zones, "cut at alpha 0" flags), Zone detail with the formula and its numbers, Example locations table (Central Cabarrus High School, Hemby Bridge Elementary, Robeson County Public Library) | A planner leaves with a short list for outreach and backup power. It is what the model spares across settings, not a finding about specific neighborhoods. The Cabarrus school's zone is CUT in the baseline and kept on in the vulnerability-aware plan, the Union school's zone is the reverse, and the library is kept on under both. Say they were chosen to illustrate differences. |
| 7 | 1:50-2:02 | same, "How robust is this?" card, then expand "Stress test" | 17 of 20 settings beat the baseline on human harm; the 3 that do not set alpha to 0; alpha trade-off figure | I tried 20 settings. Say which ones lose. |
| 8 | 2:02-2:25 | same, scroll to "Why forecasts aren't enough" | Predicted vs actual DUK+CPLE demand, Dec 22-26, Elliott morning marked; the sentence; the error-by-temperature table | A model trained on eight winters is typically within a few percent, yet it under-predicted the Elliott morning by about an eighth, and observed demand already excluded shed load. Forecasts are not enough: this is a modeled demand estimate, not a utility forecast, and it does not predict outages or available supply. |
| 9 | 2:25-2:33 | expand "Methods & sources" | The scaling sentence, r definition, band, protected-facility rule, sources table with URLs and dates | Every number is sourced; OpenStreetMap facilities are incomplete. |
| 10 | 2:33-2:50 | editor: `src/metric_grid/model/optimizer.py` lines 77-84, then line 91 (excerpt below) | The 9 lines | Same band for both plans; protected zones fixed to zero; one objective is load, the other is harm. |
| 11 | 2:50-3:00 | terminal | The one test below, five PASSED lines | Both plans land in the same band and never cut a protected zone, tested on the real zones. |

## Code to show on screen (src/metric_grid/model/optimizer.py)

First, lines 77-84 (8 lines): the model both plans share.

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

Then scroll to line 91 (1 line): the only thing that differs between the plans.

```python
prob += pulp.lpSum(objective[i] * x[i] for i in ids)
```

For the baseline `objective[i]` is each zone's load `L_i` (least MW above the target); for the vulnerability-aware plan it is the harm score `H_i(alpha)`. Both are solved inside the same band `lo`..`hi`.

## The one test to run on camera

```bash
.venv/bin/python -m pytest tests/test_harm_optimizer.py -k real_both_plans_in_same_band -v
```

Five PASSED lines (one per alpha). Do not run the whole suite on camera (about 40 seconds).

## Before recording

- `make test` is green; `make demo` opens the app; no other tab shows a different data version.
- Screenshots in `docs/figures/app_*.png` are current (`python scripts/app_screenshots.py` with the app running).
- Check every number you say against the screen, not memory. The numbers above come from the frozen model output.
