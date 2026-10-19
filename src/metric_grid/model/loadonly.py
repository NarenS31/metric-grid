"""The load-only plan SET: many equivalent ways to meet the same MW target, instead of one arbitrary "baseline".

Why: with ~157 selectable zones, huge numbers of zone sets land inside the MW band, so the single plan that "cuts the least
MW, then fewest zones, then lowest ids" is decided by tiny numerical differences (a 0.02% change in load weights flipped 3 of
its 6 zones). A fair comparison puts the vulnerability-aware plan against the whole set of plans a load-only rule could pick.

Definition. A load-only plan is any set of unprotected zones whose load lies in [T, T * (1 + near_opt_pct/100)]: it meets the
target and overshoots by at most near_opt_pct of the target (optimal or near-optimal for the load-only objective "cut as
little MW as needed"). With the county cap on, the cap applies to these plans too.

Generation (deterministic). Plan 0 is the exact optimum of the load-only objective (the old baseline). Further plans come from
one CBC solve each of  min sum_i c_i x_i  inside the same band, where the cost per zone is c_i = L_i * u_i with u_i drawn from
a fixed-seed generator (uniform on [1 - spread, 1 + spread]). Each draw is a different "preference" among equivalent zones;
duplicates are discarded, so plans are distinct. This is a wide, reproducible cross-section of the near-optimal set, not a
uniform sample of it (uniform sampling of subset-sum slices is not practical); the stability check in
scripts/loadonly_stability.py re-runs it with other seeds to show the distribution is not an artifact of the seed.

The TYPICAL plan is the member closest to the median on all four displayed metrics (see typical_index), chosen deterministically.
"""
import numpy as np
import pandas as pd

from metric_grid.model import optimizer as op

SEED = 20261019
SPREAD = 0.5
METRICS = ["households", "electric_heat_households", "h_human", "h_econ"]


def _arrays(zones: pd.DataFrame):
    z = zones.sort_values("zone_id").reset_index(drop=True)
    ids = [int(i) for i in z["zone_id"]]
    return z, ids, dict(zip(ids, z["L_mw"])), dict(zip(ids, z["protected"]))


def sample_plans(zones: pd.DataFrame, target_mw: float, band_pct: float, near_opt_pct: float, n_plans: int = 200,
                 seed: int = SEED, county_cap: float | None = None, spread: float = SPREAD, max_seconds: float = 10.0,
                 max_tries_factor: int = 6) -> dict:
    """Generate up to n_plans distinct load-only plans (see module docstring). Returns {plans, tries, lo_mw, hi_mw}."""
    z, ids, L, prot = _arrays(zones)
    lo = target_mw
    hi = target_mw * (1 + min(band_pct, near_opt_pct) / 100)
    county_of = dict(zip(ids, z["COUNTYFP"])) if county_cap is not None else None
    plans, seen = [], set()
    first = op._solve_stage(ids, L, prot, lo, hi, L, 0.01, max_seconds, county_of, county_cap)  # the optimum of the load-only objective
    if first is None:
        return {"plans": [], "tries": 0, "lo_mw": lo, "hi_mw": hi}
    plans.append(first)
    seen.add(tuple(first))
    rng = np.random.default_rng(seed)
    tries = 0
    while len(plans) < n_plans and tries < n_plans * max_tries_factor:
        tries += 1
        u = rng.uniform(1 - spread, 1 + spread, size=len(ids))
        sel = op.solve_one(ids, L, prot, lo, hi, {i: L[i] * u[k] for k, i in enumerate(ids)}, max_seconds, 0.01, county_of, county_cap)
        if sel and tuple(sel) not in seen:
            seen.add(tuple(sel))
            plans.append(sel)
    return {"plans": plans, "tries": tries, "lo_mw": lo, "hi_mw": hi}


def plan_matrix(zones: pd.DataFrame, plans: list[list[int]]) -> tuple[np.ndarray, list[int]]:
    """Membership matrix (n_plans x n_zones, zone_id order) and the zone ids."""
    ids = sorted(int(i) for i in zones["zone_id"])
    col = {i: k for k, i in enumerate(ids)}
    B = np.zeros((len(plans), len(ids)))
    for r, p in enumerate(plans):
        for i in p:
            B[r, col[i]] = 1.0
    return B, ids


def plan_metrics(zh: pd.DataFrame, plans: list[list[int]]) -> pd.DataFrame:
    """Per-plan totals under the weights in `zh` (harm.compute_harm output): mw, zones, households, electric-heat households,
    jobs, vulnerability-weighted households (h_human), interruption cost (h_econ)."""
    z = zh.sort_values("zone_id").reset_index(drop=True)
    B, _ = plan_matrix(z, plans)
    out = pd.DataFrame({"mw": B @ z["L_mw"].to_numpy(), "zones": B.sum(axis=1), "households": B @ z["N_households"].to_numpy(),
                        "electric_heat_households": B @ z["heat_electricity"].to_numpy(), "jobs": B @ z["jobs_total"].to_numpy(),
                        "h_human": B @ z["H_human"].fillna(0).to_numpy(), "h_econ": B @ z["H_econ"].to_numpy()})
    return out


def typical_index(metrics: pd.DataFrame) -> int:
    """Index of the TYPICAL plan: the member closest to the median on all four displayed metrics (households, electric-heat
    households, vulnerability-weighted households, interruption cost). Distance = sum over the metrics of |percentile rank - 0.5|;
    ties: lowest index. (Choosing on human harm alone gave a plan at about the 85th percentile for electric-heat households,
    which would overstate the gap in the headline.)"""
    cols = ["households", "electric_heat_households", "h_human", "h_econ"]
    ranks = metrics[cols].rank(pct=True, method="average")
    return int((ranks - 0.5).abs().sum(axis=1).to_numpy().argmin())


def distribution_summary(metrics: pd.DataFrame, weighted: dict) -> dict:
    """Where the vulnerability-aware plan falls among the load-only plans. `weighted` has the four metric values.
    For each metric: min, max, median over the set, the weighted plan's value, and n_more = how many load-only plans have MORE
    than the weighted plan (n_fewer = FEWER). 'n' is the number of plans."""
    out = {"n": int(len(metrics))}
    for m in METRICS:
        v = metrics[m].to_numpy()
        w = float(weighted[m])
        out[m] = {"min": float(v.min()), "max": float(v.max()), "median": float(np.median(v)), "weighted": w,
                  "n_plans_more": int((v > w).sum()), "n_plans_fewer": int((v < w).sum())}
    return out


def diversity(plans: list[list[int]]) -> dict:
    """How different the plans are: zones used at least once, and mean pairwise overlap (Jaccard) over the first 60 pairs-blocks."""
    sets = [set(p) for p in plans]
    used = set().union(*sets) if sets else set()
    sub = sets[:80]
    jac = [len(a & b) / len(a | b) for k, a in enumerate(sub) for b in sub[k + 1:]]
    return {"n_plans": len(plans), "zones_used": len(used), "mean_jaccard": float(np.mean(jac)) if jac else None}


def set_key(target_key: str, cap: bool = False, flat: bool = False) -> str:
    """Key of a plan set in data/frozen/loadonly_plans.json: '<target>|free', '<target>|cap' or 'elliott|flat'."""
    return f"{target_key}|{'flat' if flat else 'cap' if cap else 'free'}"


def build_sets(zones: pd.DataFrame, cfg: dict, kw_per_job: float, d_nc08: float, t_nc08: float) -> dict:
    """Plan sets for every setting the app pre-solves: targets (Elliott, 10, 15, 20%) x county cap off/on, plus the flat-allocation
    sensitivity at the Elliott target. Each entry: plans, typical_index (default harm weights), counts and band."""
    from metric_grid.model import harm
    from metric_grid.model.sensitivity import flat_loads

    o = cfg["optimizer"]
    lo = o["loadonly"]
    targets = [("elliott", t_nc08)] + [(str(p), d_nc08 * p / 100) for p in o["target_pcts"]]
    jobs = [(k, T, cap, False, zones) for cap in (None, o["county_cap"]["max_share"]) for k, T in targets]
    flat_zones = zones.copy()
    flat_zones["L_mw"] = flat_loads(flat_zones, d_nc08)
    jobs.append(("elliott", t_nc08, None, True, flat_zones))
    out = {}
    for key, T, cap, flat, zs in jobs:
        zh = harm.compute_harm(zs, cfg, kw_per_job)
        r = sample_plans(zh, T, o["band_pct"], lo["near_opt_pct"], lo["n_plans"], lo["seed"], cap, lo["spread"])
        M = plan_metrics(zh, r["plans"])
        out[set_key(key, cap is not None, flat)] = {
            "target_mw": T, "cap": cap is not None, "flat": flat, "n": len(r["plans"]), "tries": r["tries"], "lo_mw": r["lo_mw"],
            "hi_mw": r["hi_mw"], "typical_index": typical_index(M), "plans": r["plans"], "diversity": diversity(r["plans"])}
    return out
