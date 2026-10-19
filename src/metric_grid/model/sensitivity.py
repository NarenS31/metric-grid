"""Sensitivity runs (spec Phase 4.3), compared against the SET of equivalent load-only plans (model/loadonly.py).

Settings tested for the vulnerability-aware plan at the Elliott target:
  * grid:   alpha in {0, .25, .5, .75, 1} x w_svi in {.5, .7, .9} (w_eheat = 1 - w_svi)         15 settings
  * band:   delta 1% and 5% (2% is the default grid point)
  * cost:   Small C&I interruption rate instead of Medium/Large
  * cap:    county-share cap (no county takes more than max_share of the MW cut), both plans, with its own plan set
  * flat:   flat allocation weights (1 per housing unit + 1 per job instead of the modeled kW), L renormalized to the same
            D_NC08, with its own plan set
In every setting the load-only side is the plan set evaluated under that setting's harm weights and cost class; its TYPICAL plan
is the member closest to the median on all four displayed metrics (loadonly.typical_index). Each row also counts how many
of the N load-only plans the vulnerability-aware plan beats on each metric.
Zones are classed by how often the vulnerability-aware plan cuts them: always, sometimes, never (selectable but never cut),
or protected (never selectable).
"""
import collections

import pandas as pd

from metric_grid.model import harm, loadonly, optimizer
from metric_grid.model.optimizer import Infeasible


def flat_loads(zones: pd.DataFrame, d_nc08_mw: float) -> pd.Series:
    """Flat allocation fallback: weight = housing units + jobs (1:1), scaled so the loads still sum to D_NC08."""
    w = zones["housing_units"] + zones["jobs_total"]
    return d_nc08_mw * w / w.sum()


def _plan_row(prefix: str, p) -> dict:
    return {f"{prefix}_mw": p.mw_shed, f"{prefix}_zones": p.n_zones, f"{prefix}_households": p.households,
            f"{prefix}_ehh": p.electric_heat_households, f"{prefix}_h_human": p.h_human, f"{prefix}_h_econ": p.h_econ}


def run_setting(zones: pd.DataFrame, cfg: dict, kw_per_job: float, d_nc08: float, target: float, name: str, alpha: float,
                w_svi: float, band_pct: float, plans: list, commercial_class: str | None = None, flat: bool = False,
                county_cap: float | None = None):
    """Solve the vulnerability-aware plan for one setting and compare it with the load-only plan set `plans`.
    Returns (row dict, PairResult or Infeasible)."""
    z = zones.copy()
    if flat:
        z["L_mw"] = flat_loads(z, d_nc08)
    zh = harm.compute_harm(z, cfg, kw_per_job, w_svi=w_svi, w_eheat=1 - w_svi, commercial_class=commercial_class)
    M = loadonly.plan_metrics(zh, plans)
    ti = loadonly.typical_index(M)
    r = optimizer.solve(zh, target, alpha, band_pct=band_pct, widen_pct=tuple(cfg["optimizer"]["band_widen_pct"]),
                        load_tol_mw=cfg["optimizer"]["load_tol_mw"], baseline_ids=plans[ti], county_cap=county_cap)
    if isinstance(r, Infeasible):
        return {"setting": name, "alpha": alpha, "w_svi": w_svi, "solved": False}, r
    b, w = r.baseline, r.weighted
    dist = loadonly.distribution_summary(M, {"households": w.households, "electric_heat_households": w.electric_heat_households,
                                             "h_human": w.h_human, "h_econ": w.h_econ})
    row = {"setting": name, "alpha": alpha, "w_svi": w_svi, "band_pct": band_pct, "band_used_pct": r.delta_pct_used,
           "commercial_class": commercial_class or cfg["harm"]["ice"]["commercial_class"], "flat": flat,
           "county_cap": county_cap, "solved": True, **_plan_row("baseline", b), **_plan_row("weighted", w),
           "zones_differ": len(r.zones_that_differ()),
           "human_change_pct": 100 * (w.h_human - b.h_human) / b.h_human,
           "econ_change_pct": 100 * (w.h_econ - b.h_econ) / b.h_econ,
           "households_change": w.households - b.households,
           "households_change_pct": 100 * (w.households - b.households) / b.households,
           "ehh_change_pct": 100 * (w.electric_heat_households - b.electric_heat_households) / b.electric_heat_households,
           "n_plans": dist["n"], "beats_human": dist["h_human"]["n_plans_more"], "beats_ehh": dist["electric_heat_households"]["n_plans_more"],
           "beats_cost": dist["h_econ"]["n_plans_more"], "more_households_than": dist["households"]["n_plans_fewer"],
           "typical_index": ti, "baseline_zone_ids": b.zone_ids, "weighted_zone_ids": w.zone_ids}
    return row, r


def full_sensitivity(zones: pd.DataFrame, cfg: dict, kw_per_job: float, d_nc08: float, target: float, sets: dict) -> dict:
    """Run every setting against its plan set. Returns {rows: DataFrame, classes, default_baseline_ids, default_plans, default_row}."""
    o, h = cfg["optimizer"], cfg["harm"]
    a0, w0, pct0 = h["alpha_default"], h["w_svi"], o["band_pct"]
    cap = o["county_cap"]["max_share"]
    free = sets[loadonly.set_key("elliott")]["plans"]
    capped = sets[loadonly.set_key("elliott", cap=True)]["plans"]
    flatp = sets[loadonly.set_key("elliott", flat=True)]["plans"]
    kw = dict(zones=zones, cfg=cfg, kw_per_job=kw_per_job, d_nc08=d_nc08, target=target)
    base_row, _ = run_setting(**kw, name="default", alpha=a0, w_svi=w0, band_pct=pct0, plans=free)
    rows = []
    for alpha in o["alpha_grid"]:
        for w in o["w_svi_grid"]:
            rows.append(run_setting(**kw, name="grid", alpha=alpha, w_svi=w, band_pct=pct0, plans=free)[0])
    for pct in o["band_sensitivity_pct"]:
        if pct != pct0:
            rows.append(run_setting(**kw, name=f"band {pct:g}%", alpha=a0, w_svi=w0, band_pct=pct, plans=free)[0])
    rows.append(run_setting(**kw, name="Small C&I cost rate", alpha=a0, w_svi=w0, band_pct=pct0, plans=free, commercial_class="small")[0])
    rows.append(run_setting(**kw, name="flat allocation weights", alpha=a0, w_svi=w0, band_pct=pct0, plans=flatp, flat=True)[0])
    rows.append(run_setting(**kw, name=f"county-share cap {cap:.0%}", alpha=a0, w_svi=w0, band_pct=pct0, plans=capped, county_cap=cap)[0])
    df = pd.DataFrame(rows)
    solved = df[df["solved"]]
    cut_sets = [set(ids) for ids in solved["weighted_zone_ids"]]
    always = sorted(set.intersection(*cut_sets))
    ever = sorted(set.union(*cut_sets))
    prot = sorted(zones.loc[zones["protected"], "zone_id"].astype(int))
    never = sorted(set(zones["zone_id"].astype(int)) - set(ever) - set(prot))
    return {"rows": df, "classes": {"always": always, "sometimes": sorted(set(ever) - set(always)), "never": never, "protected": prot},
            "default_baseline_ids": base_row["baseline_zone_ids"], "default_plans": free, "default_row": base_row}


def priority_list(zones: pd.DataFrame, result: dict, cfg: dict) -> pd.DataFrame:
    """"Vulnerable zones most often cut when only megawatts count".

    Among unprotected zones with SVI >= priority_list.svi_min OR electric-heat share >= priority_list.electric_heat_min (config),
    rank by the number of load-only plans (the default plan set) that cut the zone; ties: higher SVI, then lower zone_id. Keeps the
    top max_rows. `vuln_aware_cuts` says whether the vulnerability-aware plan cuts the zone in the default setting, and
    `vuln_aware_cut_settings` in how many of the sensitivity settings. The plan set is not a uniform sample, so frequencies are
    indicative. Built only from computed values; it is not a switching recommendation."""
    p = cfg["priority_list"]
    plans = result["default_plans"]
    counts = collections.Counter(int(i) for plan in plans for i in plan)
    rows = result["rows"]
    solved = rows[rows["solved"]]
    in_settings = collections.Counter(int(i) for ids in solved["weighted_zone_ids"] for i in ids)
    default_cuts = set(int(i) for i in result["default_row"]["weighted_zone_ids"])
    z = zones[~zones["protected"]]
    s = z[(z["RPL_THEMES"] >= p["svi_min"]) | (z["share_electric_heat"] >= p["electric_heat_min"])].copy()  # NaN never qualifies
    s["loadonly_cut_count"] = [counts.get(int(i), 0) for i in s["zone_id"]]
    s["loadonly_cut_share"] = s["loadonly_cut_count"] / len(plans)
    s["vuln_aware_cuts"] = [int(i) in default_cuts for i in s["zone_id"]]
    s["vuln_aware_cut_settings"] = [in_settings.get(int(i), 0) for i in s["zone_id"]]
    s["n_settings"] = len(solved)
    s = s.sort_values(["loadonly_cut_count", "RPL_THEMES", "zone_id"], ascending=[False, False, True]).head(p["max_rows"])
    return s[["zone_id", "GEOID", "COUNTY", "RPL_THEMES", "share_electric_heat", "occupied_units", "L_mw", "loadonly_cut_count",
              "loadonly_cut_share", "vuln_aware_cuts", "vuln_aware_cut_settings", "n_settings"]]


def alpha_sweep(zones: pd.DataFrame, cfg: dict, kw_per_job: float, d_nc08: float, target: float, sets: dict) -> pd.DataFrame:
    """Default band and weights; alpha in the configured grid, against the default plan set. Percent changes are the
    vulnerability-aware plan vs the typical load-only plan (negative = less modeled harm)."""
    o, h = cfg["optimizer"], cfg["harm"]
    plans = sets[loadonly.set_key("elliott")]["plans"]
    rows = [run_setting(zones, cfg, kw_per_job, d_nc08, target, "alpha sweep", alpha, h["w_svi"], o["band_pct"], plans)[0]
            for alpha in o["alpha_grid"]]
    return pd.DataFrame(rows)


def delta_sensitivity(zones: pd.DataFrame, target_mw: float, alpha: float, band_pcts: list[float]) -> pd.DataFrame:
    """Band-width sensitivity on prepared zones (harm columns present) against the single least-overshed plan (Stage A)."""
    rows = []
    for pct in band_pcts:
        r = optimizer.solve(zones, target_mw, alpha, band_pct=pct, widen_pct=())
        if isinstance(r, Infeasible):
            rows.append({"band_pct": pct, "solved": False})
            continue
        b, w = r.baseline, r.weighted
        rows.append({"band_pct": pct, "solved": True, "band_lo_mw": r.band_lo_mw, "band_hi_mw": r.band_hi_mw,
                     "baseline_mw": b.mw_shed, "weighted_mw": w.mw_shed, "baseline_zones": b.n_zones,
                     "weighted_zones": w.n_zones, "zones_differ": len(r.zones_that_differ()),
                     "human_change_pct": 100 * (w.h_human - b.h_human) / b.h_human,
                     "econ_change_pct": 100 * (w.h_econ - b.h_econ) / b.h_econ})
    return pd.DataFrame(rows)
