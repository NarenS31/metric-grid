"""Scenarios (spec Phase 4.4) and plain-language summaries that never hide who is cut.

Scenarios: T at 10/15/20% of modeled NC-08 load. For each plan: zones cut in all three scenarios vs only in the worst (20%).
"""
import pandas as pd

from metric_grid.model import harm, optimizer
from metric_grid.model.optimizer import Infeasible, PairResult, PlanResult


def plain_summary(r: PairResult) -> str:
    """One honest sentence comparing the plans. States the household count change next to the vulnerability numbers,
    in whichever direction it goes (the harm-weighted plan can cut MORE households and still lower modeled harm)."""
    b, w = r.baseline, r.weighted
    dh = w.households - b.households
    human = 100 * (w.h_human - b.h_human) / b.h_human
    econ = 100 * (w.h_econ - b.h_econ) / b.h_econ
    people = (f"cuts {abs(dh):,.0f} MORE households ({100 * dh / b.households:+.0f}%)" if dh > 0 else
              f"cuts {abs(dh):,.0f} fewer households ({100 * dh / b.households:+.0f}%)" if dh < 0 else "cuts the same number of households")
    human_txt = f"{abs(human):.0f}% {'fewer' if human < 0 else 'more'} vulnerability-weighted households"
    econ_txt = f"{abs(econ):.0f}% {'lower' if econ < 0 else 'higher'} modeled interruption cost (2013 dollars)"
    return f"The vulnerability-aware plan {people} than the load-only baseline, but {human_txt} and {econ_txt}."


def run_scenarios(zones: pd.DataFrame, cfg: dict, kw_per_job: float, d_nc08: float, alpha: float | None = None) -> dict:
    """Solve both plans at each configured percent of D_NC08. Returns {rows, cut_in_all, only_worst, results}."""
    o = cfg["optimizer"]
    alpha = cfg["harm"]["alpha_default"] if alpha is None else alpha
    zh = harm.compute_harm(zones, cfg, kw_per_job)
    results, rows = {}, []
    for pct in o["target_pcts"]:
        target = d_nc08 * pct / 100
        r = optimizer.solve(zh, target, alpha, band_pct=o["band_pct"], widen_pct=tuple(o["band_widen_pct"]), load_tol_mw=o["load_tol_mw"])
        results[pct] = r
        if isinstance(r, Infeasible):
            rows.append({"target_pct": pct, "target_mw": target, "solved": False, "reason": r.reason})
            continue
        b, w = r.baseline, r.weighted
        rows.append({"target_pct": pct, "target_mw": target, "solved": True, "band_hi_mw": r.band_hi_mw, "baseline_mw": b.mw_shed,
                     "weighted_mw": w.mw_shed, "baseline_zones": b.n_zones, "weighted_zones": w.n_zones,
                     "baseline_households": b.households, "weighted_households": w.households,
                     "human_change_pct": 100 * (w.h_human - b.h_human) / b.h_human,
                     "econ_change_pct": 100 * (w.h_econ - b.h_econ) / b.h_econ, "zones_differ": len(r.zones_that_differ())})
    ok = [p for p in o["target_pcts"] if not isinstance(results[p], Infeasible)]
    worst = max(ok)
    out = {"rows": pd.DataFrame(rows), "results": results, "worst_pct": worst, "cut_in_all": {}, "only_worst": {}}
    for plan in ("baseline", "weighted"):
        sets = {p: set(getattr(results[p], plan).zone_ids) for p in ok}
        out["cut_in_all"][plan] = sorted(set.intersection(*sets.values()))
        out["only_worst"][plan] = sorted(sets[worst] - set().union(*[sets[p] for p in ok if p != worst]))
    return out


def _plan_dict(p) -> dict:
    return {"zone_ids": p.zone_ids, "mw_shed": p.mw_shed, "overshed_mw": p.overshed_mw, "households": p.households,
            "electric_heat_households": p.electric_heat_households, "jobs": p.jobs, "h_human": p.h_human, "h_econ": p.h_econ}


def presolve_grid(zones: pd.DataFrame, cfg: dict, kw_per_job: float, d_nc08: float, t_nc08: float) -> list[dict]:
    """Demo safety net: solve both plans for alpha in the grid x (the Elliott target and each % preset), with the county cap
    OFF and ON, at default weights. Written to data/frozen/ by `make freeze` (spec deviation: the spec solves at app start;
    the 10-20% presets take 2-3 s each and the first capped solve can exceed the app's 2 s limit)."""
    o = cfg["optimizer"]
    zh = harm.compute_harm(zones, cfg, kw_per_job)
    targets = [("elliott", t_nc08)] + [(str(p), d_nc08 * p / 100) for p in o["target_pcts"]]
    out = []
    for cap in (None, o["county_cap"]["max_share"]):
        for key, T in targets:
            base_ids = None
            for alpha in o["alpha_grid"]:
                r = optimizer.solve(zh, T, alpha, band_pct=o["band_pct"], widen_pct=tuple(o["band_widen_pct"]),
                                    load_tol_mw=o["load_tol_mw"], baseline_ids=base_ids, county_cap=cap)
                rec = {"target_key": key, "alpha": alpha, "target_mw": T, "cap": cap is not None}
                if isinstance(r, Infeasible):
                    rec.update(solved=False, reason=r.reason, max_feasible_mw=r.max_feasible_mw)
                else:
                    base_ids = r.baseline.zone_ids if cap is None else None
                    rec.update(solved=True, band_lo_mw=r.band_lo_mw, band_hi_mw=r.band_hi_mw, delta_pct_used=r.delta_pct_used,
                               widened=r.widened, baseline=_plan_dict(r.baseline), weighted=_plan_dict(r.weighted),
                               zones_differ=r.zones_that_differ(), solve_seconds=r.solve_seconds, summary=plain_summary(r))
                out.append(rec)
    return out


def county_breakdown(zones: pd.DataFrame, plan) -> pd.DataFrame:
    """Per-county totals for one plan's cut zones: zones, MW, share of the cut, households, mean SVI. `zones` needs COUNTY."""
    t = zones[zones["zone_id"].isin(plan.zone_ids)]
    g = t.groupby("COUNTY").agg(zones=("zone_id", "count"), mw=("L_mw", "sum"), households=("occupied_units", "sum"),
                                mean_svi=("RPL_THEMES", "mean"))
    g["share_of_cut"] = g["mw"] / g["mw"].sum()
    return g.sort_values("mw", ascending=False)


def pair_to_record(r: PairResult, target_key: str, alpha: float, cap: bool = False) -> dict:
    """Plain-dict form of a solved pair (same shape as presolved.json records), for caching and JSON."""
    return {"target_key": target_key, "alpha": alpha, "target_mw": r.target_mw, "cap": cap, "solved": True, "band_lo_mw": r.band_lo_mw,
            "band_hi_mw": r.band_hi_mw, "delta_pct_used": r.delta_pct_used, "widened": r.widened,
            "baseline": _plan_dict(r.baseline), "weighted": _plan_dict(r.weighted), "zones_differ": r.zones_that_differ(),
            "solve_seconds": r.solve_seconds, "summary": plain_summary(r)}


def record_to_pair(rec: dict) -> PairResult:
    """Rebuild a PairResult from a solved record (presolved.json or pair_to_record)."""
    def plan(name, d):
        return PlanResult(name, list(d["zone_ids"]), d["mw_shed"], d["overshed_mw"], len(d["zone_ids"]), d["households"],
                          d["electric_heat_households"], d["jobs"], d["h_human"], d["h_econ"])
    return PairResult(rec["target_mw"], rec["band_lo_mw"], rec["band_hi_mw"], rec["delta_pct_used"], rec["widened"], rec["alpha"],
                      plan("load-only baseline", rec["baseline"]), plan("harm-weighted plan", rec["weighted"]),
                      rec.get("solve_seconds", 0.0))
