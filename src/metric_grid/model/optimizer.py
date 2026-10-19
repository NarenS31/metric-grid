"""Two-plan optimizer (PuLP/CBC), shared target band, deterministic.

Both plans pick zones x_i in {0,1}, with x_i = 0 for protected zones, so that the zone load shed lies in the SAME band
    T_NC08 <= sum x_i L_i <= T_NC08 + delta,        delta = band_pct of T_NC08.
Stage A (load-only baseline):      minimize sum x_i L_i                (least overshed, optimal within load_tol_mw = 10 kW).
Stage B (vulnerability-aware):     minimize sum x_i H_i(alpha)         (lowest modeled harm).
Optional county-share cap (off by default): no single county may take more than `county_cap` of the total MW cut, applied to
both plans equally (a response to cumulative-burden concentration).
Ties are broken by fewest zones, then lowest zone_id (two solves per plan). If the band has no solution it is
widened through the configured steps (max 5%); if still empty, or the target exceeds the unprotected load, solve() returns
an Infeasible result carrying the maximum feasible reduction.
"""
import time
from dataclasses import dataclass, field

import pandas as pd
import pulp

from metric_grid.model.harm import MissingDataError, blend

CBC_SEED = 12345


@dataclass
class Infeasible:
    """The requested target cannot be met by unprotected zones (or no subset fits even the widest band)."""
    requested_mw: float
    max_feasible_mw: float
    reason: str


@dataclass
class PlanResult:
    """One plan's choice and totals."""
    name: str
    zone_ids: list
    mw_shed: float
    overshed_mw: float
    n_zones: int
    households: float
    electric_heat_households: float
    jobs: float
    h_human: float          # vulnerability-weighted households
    h_econ: float           # interruption cost, US 2013 dollars for h hours


@dataclass
class PairResult:
    """Both plans plus the band they share."""
    target_mw: float
    band_lo_mw: float
    band_hi_mw: float
    delta_pct_used: float
    widened: bool
    alpha: float
    baseline: PlanResult
    weighted: PlanResult
    solve_seconds: float
    zone_table: pd.DataFrame = field(repr=False, default=None)

    def zones_that_differ(self) -> list:
        return sorted(set(self.baseline.zone_ids) ^ set(self.weighted.zone_ids))


def _solver(max_seconds: float, gap_abs: float):
    return pulp.PULP_CBC_CMD(msg=False, threads=1, timeLimit=max_seconds, gapAbs=gap_abs, gapRel=0.0,
                             options=[f"randomCbcSeed {CBC_SEED}", f"randomSeed {CBC_SEED}"])


def _build_problem(ids, L, protected, lo, hi, county_of=None, cap=None):
    """The shared constraint set: binary x_i, x_i = 0 for protected zones, lo <= sum L_i x_i <= hi, optional county cap."""
    prob = pulp.LpProblem("shed", pulp.LpMinimize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in ids}
    for i in ids:
        if protected[i]:
            prob += x[i] == 0  # hard exclusion (PuLP ignores upBound on Binary variables, so state it as a constraint)
    load = pulp.lpSum(L[i] * x[i] for i in ids)
    prob += load >= lo
    prob += load <= hi
    if cap is not None:  # county c: sum_{i in c} L_i x_i <= cap * sum_i L_i x_i  (linear, so no extra variables)
        for c in sorted(set(county_of.values())):
            prob += pulp.lpSum(L[i] * x[i] for i in ids if county_of[i] == c) <= cap * load
    return prob, x


def solve_one(ids, L, protected, lo, hi, objective, max_seconds, gap_abs, county_of=None, cap=None):
    """One solve of `objective` inside [lo, hi] (no tie-break stage). Returns the sorted selected ids, or None."""
    prob, x = _build_problem(ids, L, protected, lo, hi, county_of, cap)
    prob += pulp.lpSum(objective[i] * x[i] for i in ids)
    prob.solve(_solver(max_seconds, gap_abs))
    if pulp.LpStatus[prob.status] != "Optimal":
        return None
    return sorted(i for i in ids if x[i].value() is not None and x[i].value() > 0.5)


def _solve_stage(ids, L, protected, lo, hi, objective, tol, max_seconds, county_of=None, cap=None):
    """Minimize `objective` inside [lo, hi] to within `tol`, then break ties: fewest zones, then lowest zone_ids.

    Two solves: (1) the primary objective; (2) among solutions within `tol` of it, minimize M*count + sum(zone_id) with
    M larger than any possible zone_id sum, which is exactly "fewest zones, then lowest ids". Returns selected ids or None.
    """
    prob, x = _build_problem(ids, L, protected, lo, hi, county_of, cap)
    prob += pulp.lpSum(objective[i] * x[i] for i in ids)
    prob.solve(_solver(max_seconds, tol))
    if pulp.LpStatus[prob.status] != "Optimal":
        return None
    best = pulp.value(prob.objective)

    big = float(sum(ids) + 1)
    prob, x = _build_problem(ids, L, protected, lo, hi, county_of, cap)
    prob += pulp.lpSum(objective[i] * x[i] for i in ids) <= best + tol
    prob += pulp.lpSum((big + i) * x[i] for i in ids)  # big*count + sum(ids)
    prob.solve(_solver(max_seconds, 0.5))  # objective is integer-valued, so a 0.5 gap is exact
    if pulp.LpStatus[prob.status] != "Optimal":
        return None
    return sorted(i for i in ids if x[i].value() is not None and x[i].value() > 0.5)


def _summarize(name, zones: pd.DataFrame, chosen: list, target: float) -> PlanResult:
    s = zones[zones["zone_id"].isin(chosen)]
    mw = float(s["L_mw"].sum())
    return PlanResult(name, list(chosen), mw, mw - target, len(chosen), float(s["N_households"].sum()),
                      float(s["heat_electricity"].sum()), float(s["jobs_total"].sum()),
                      float(s["H_human"].sum()), float(s["H_econ"].sum()))


def solve(zones: pd.DataFrame, target_mw: float, alpha: float, band_pct: float = 2.0,
          widen_pct: tuple = (3.0, 4.0, 5.0), max_seconds: float = 10.0, load_tol_mw: float = 0.01,
          baseline_ids: list | None = None, county_cap: float | None = None) -> "PairResult | Infeasible":
    """Solve both plans in one shared band. `zones` needs zone_id, L_mw, protected, H_human, H_econ, Hhat_human,
    Hhat_econ, N_households, heat_electricity, jobs_total (see harm.compute_harm). The baseline does not depend on alpha or
    the harm weights, so callers may pass `baseline_ids` (e.g. the typical load-only plan from loadonly.py) to skip Stage A;
    the caller is responsible for it matching the cap and band in use. `county_cap` (e.g. 0.5) needs a `COUNTYFP` column."""
    t0 = time.perf_counter()
    z = zones.sort_values("zone_id").reset_index(drop=True)
    free = z[~z["protected"]]
    max_feasible = float(free["L_mw"].sum())
    if target_mw > max_feasible:
        return Infeasible(target_mw, max_feasible, f"Requested {target_mw:.1f} MW exceeds the {max_feasible:.1f} MW of load in "
                          "unprotected zones. Reduce the requested target or review the protected-zone rule.")
    H = blend(z, alpha)
    unpriced = z[~z["protected"] & H.isna()]
    if len(unpriced):
        raise MissingDataError(f"zone_id {unpriced['zone_id'].tolist()} have unknown harm (missing SVI/ACS) and cannot be selected")
    ids = [int(i) for i in z["zone_id"]]
    county_of = dict(zip(ids, z["COUNTYFP"])) if county_cap is not None else None
    if county_cap is not None and not 0 < county_cap <= 1:
        raise ValueError("county_cap must be in (0, 1]")
    L = dict(zip(ids, z["L_mw"]))
    prot = dict(zip(ids, z["protected"]))
    Hd = dict(zip(ids, H.fillna(0.0)))  # protected zones may be NaN; they are fixed to 0 so the value is never used
    steps = [band_pct] + [w for w in widen_pct if w > band_pct]
    for pct in steps:
        lo, hi = target_mw, target_mw * (1 + pct / 100)
        a = list(baseline_ids) if baseline_ids is not None else _solve_stage(ids, L, prot, lo, hi, L, load_tol_mw, max_seconds, county_of, county_cap)
        if a is None or not lo - 1e-9 <= sum(L[i] for i in a) <= hi + 1e-9:
            continue  # no baseline plan fits this band (or the supplied one does not): try the next widening step
        b = _solve_stage(ids, L, prot, lo, hi, Hd, 1e-4, max_seconds, county_of, county_cap)
        if b is None:
            continue
        return PairResult(target_mw, lo, hi, pct, pct != band_pct, alpha, _summarize("typical load-only plan" if baseline_ids is not None else "load-only baseline", z, a, target_mw),
                          _summarize("harm-weighted plan", z, b, target_mw), time.perf_counter() - t0, z)
    return Infeasible(target_mw, max_feasible, f"No combination of unprotected zones lands within {target_mw:.1f} to "
                      f"{target_mw * (1 + steps[-1] / 100):.1f} MW (band widened up to {steps[-1]:.0f}%)"
                      f"{f' with no county above {county_cap:.0%} of the cut' if county_cap is not None else ''}. "
                      f"Maximum feasible reduction is {max_feasible:.1f} MW.")
