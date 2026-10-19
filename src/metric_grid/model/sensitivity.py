"""Sensitivity runs. Phase 4 step 1-2 part: how much the shared band width delta changes the result.

(The alpha x w_svi grid and flat-weight re-solve from the spec are added with the app, Phase 4 step 3.)
"""
import pandas as pd

from metric_grid.model import optimizer


def delta_sensitivity(zones: pd.DataFrame, target_mw: float, alpha: float, band_pcts: list[float]) -> pd.DataFrame:
    """Solve both plans at each band width (no widening) and report whether the harm difference survives.

    `human_change_pct` / `econ_change_pct` = (weighted - baseline) / baseline, so negative means the harm-weighted plan
    imposes less modeled harm. A row with `solved == False` means that band had no solution.
    """
    rows = []
    for pct in band_pcts:
        r = optimizer.solve(zones, target_mw, alpha, band_pct=pct, widen_pct=())
        if isinstance(r, optimizer.Infeasible):
            rows.append({"band_pct": pct, "solved": False})
            continue
        b, w = r.baseline, r.weighted
        rows.append({"band_pct": pct, "solved": True, "band_lo_mw": r.band_lo_mw, "band_hi_mw": r.band_hi_mw,
                     "baseline_mw": b.mw_shed, "weighted_mw": w.mw_shed, "baseline_zones": b.n_zones,
                     "weighted_zones": w.n_zones, "zones_differ": len(r.zones_that_differ()),
                     "human_change_pct": 100 * (w.h_human - b.h_human) / b.h_human,
                     "econ_change_pct": 100 * (w.h_econ - b.h_econ) / b.h_econ})
    return pd.DataFrame(rows)
