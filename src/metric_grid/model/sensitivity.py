"""Sensitivity runs (spec Phase 4.3).

Settings tested for the harm-weighted plan against the load-only baseline, all at the same target and band logic:
  * grid:   alpha in {0, .25, .5, .75, 1} x w_svi in {.5, .7, .9} (w_eheat = 1 - w_svi)         15 settings
  * band:   delta 1% and 5% (2% is the default grid point)
  * cost:   Small C&I interruption rate instead of Medium/Large
  * flat:   flat allocation weights (1 per housing unit + 1 per job instead of 5.43 kW/unit and 1.39 kW/job), L renormalized
            to the same D_NC08, which also changes the baseline
Zones are then classed: always cut by the weighted plan in every setting, sometimes, never (selectable but never cut),
or protected (never selectable).
"""
import pandas as pd

from metric_grid.model import harm, optimizer
from metric_grid.model.optimizer import Infeasible


def flat_loads(zones: pd.DataFrame, d_nc08_mw: float) -> pd.Series:
    """Flat allocation fallback: weight = housing units + jobs (1:1), scaled so the loads still sum to D_NC08."""
    w = zones["housing_units"] + zones["jobs_total"]
    return d_nc08_mw * w / w.sum()


def _plan_row(prefix: str, p) -> dict:
    return {f"{prefix}_mw": p.mw_shed, f"{prefix}_zones": p.n_zones, f"{prefix}_households": p.households,
            f"{prefix}_ehh": p.electric_heat_households, f"{prefix}_h_human": p.h_human, f"{prefix}_h_econ": p.h_econ}


def run_setting(zones: pd.DataFrame, cfg: dict, kw_per_job: float, d_nc08: float, target: float, name: str, alpha: float,
                w_svi: float, band_pct: float, commercial_class: str | None = None, flat: bool = False,
                baseline_ids: list | None = None):
    """Solve one setting. Returns (row dict, PairResult)."""
    z = zones.copy()
    if flat:
        z["L_mw"] = flat_loads(z, d_nc08)
    zh = harm.compute_harm(z, cfg, kw_per_job, w_svi=w_svi, w_eheat=1 - w_svi, commercial_class=commercial_class)
    r = optimizer.solve(zh, target, alpha, band_pct=band_pct, widen_pct=tuple(cfg["optimizer"]["band_widen_pct"]),
                        load_tol_mw=cfg["optimizer"]["load_tol_mw"], baseline_ids=None if flat else baseline_ids)
    if isinstance(r, Infeasible):
        return {"setting": name, "alpha": alpha, "w_svi": w_svi, "solved": False}, r
    b, w = r.baseline, r.weighted
    row = {"setting": name, "alpha": alpha, "w_svi": w_svi, "band_pct": band_pct, "band_used_pct": r.delta_pct_used,
           "commercial_class": commercial_class or cfg["harm"]["ice"]["commercial_class"], "flat": flat, "solved": True,
           **_plan_row("baseline", b), **_plan_row("weighted", w),
           "zones_differ": len(r.zones_that_differ()),
           "human_change_pct": 100 * (w.h_human - b.h_human) / b.h_human,
           "econ_change_pct": 100 * (w.h_econ - b.h_econ) / b.h_econ,
           "households_change": w.households - b.households,
           "households_change_pct": 100 * (w.households - b.households) / b.households,
           "ehh_change_pct": 100 * (w.electric_heat_households - b.electric_heat_households) / b.electric_heat_households,
           "baseline_zone_ids": b.zone_ids, "weighted_zone_ids": w.zone_ids}
    return row, r


def full_sensitivity(zones: pd.DataFrame, cfg: dict, kw_per_job: float, d_nc08: float, target: float) -> dict:
    """Run every setting; return {rows: DataFrame, classes: {always, sometimes, never, protected}, default_baseline_ids}."""
    o, h = cfg["optimizer"], cfg["harm"]
    a0, w0, pct0 = h["alpha_default"], h["w_svi"], o["band_pct"]
    base_row, base = run_setting(zones, cfg, kw_per_job, d_nc08, target, "default", a0, w0, pct0)
    base_ids = base.baseline.zone_ids
    rows = []
    for alpha in o["alpha_grid"]:
        for w in o["w_svi_grid"]:
            rows.append(run_setting(zones, cfg, kw_per_job, d_nc08, target, "grid", alpha, w, pct0, baseline_ids=base_ids)[0])
    for pct in o["band_sensitivity_pct"]:
        if pct != pct0:
            rows.append(run_setting(zones, cfg, kw_per_job, d_nc08, target, f"band {pct:g}%", a0, w0, pct)[0])
    rows.append(run_setting(zones, cfg, kw_per_job, d_nc08, target, "Small C&I cost rate", a0, w0, pct0, commercial_class="small",
                            baseline_ids=base_ids)[0])
    rows.append(run_setting(zones, cfg, kw_per_job, d_nc08, target, "flat allocation weights", a0, w0, pct0, flat=True)[0])
    df = pd.DataFrame(rows)
    solved = df[df["solved"]]
    cut_sets = [set(ids) for ids in solved["weighted_zone_ids"]]
    always = sorted(set.intersection(*cut_sets))
    ever = sorted(set.union(*cut_sets))
    prot = sorted(zones.loc[zones["protected"], "zone_id"].astype(int))
    never = sorted(set(zones["zone_id"].astype(int)) - set(ever) - set(prot))
    return {"rows": df, "classes": {"always": always, "sometimes": sorted(set(ever) - set(always)), "never": never, "protected": prot},
            "default_baseline_ids": base_ids, "default_row": base_row}


def spared_every_setting(zones: pd.DataFrame, result: dict, k: int = 5, min_alpha: float = 0.0) -> pd.DataFrame:
    """Zones the default load-only baseline cuts that the weighted plan never cuts, most vulnerable first.

    Considers every setting with alpha >= min_alpha (min_alpha=0 means all settings; a small positive value excludes the
    economic-only alpha = 0 settings, where harm is ignored by construction).
    """
    rows = result["rows"]
    rows = rows[rows["solved"] & (rows["alpha"] >= min_alpha)]
    ever = set().union(*[set(i) for i in rows["weighted_zone_ids"]])
    ids = [i for i in result["default_baseline_ids"] if i not in ever]
    s = zones[zones["zone_id"].isin(ids)].sort_values("RPL_THEMES", ascending=False)
    return s[["zone_id", "GEOID", "COUNTY", "RPL_THEMES", "share_electric_heat", "occupied_units", "L_mw"]].head(k)


def alpha_sweep(zones: pd.DataFrame, cfg: dict, kw_per_job: float, d_nc08: float, target: float) -> pd.DataFrame:
    """Default band and weights; alpha in the configured grid. Percent changes are weighted vs baseline (negative = less harm)."""
    o, h = cfg["optimizer"], cfg["harm"]
    rows = []
    base_ids = None
    for alpha in o["alpha_grid"]:
        row, r = run_setting(zones, cfg, kw_per_job, d_nc08, target, "alpha sweep", alpha, h["w_svi"], o["band_pct"], baseline_ids=base_ids)
        base_ids = r.baseline.zone_ids
        rows.append(row)
    return pd.DataFrame(rows)


def delta_sensitivity(zones: pd.DataFrame, target_mw: float, alpha: float, band_pcts: list[float]) -> pd.DataFrame:
    """Band-width sensitivity on prepared zones (harm columns present): does the harm difference survive each delta?"""
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
