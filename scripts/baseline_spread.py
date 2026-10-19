"""Dev check: how much does the choice of "the" load-only baseline matter?

Samples plans that all meet the same MW band as the shipped plans (random cost per zone), and reports where the shipped
load-only baseline and the vulnerability-aware plan fall in that distribution. Run: PYTHONPATH=src python scripts/baseline_spread.py
"""
import sys

import numpy as np
import pandas as pd

from metric_grid import frozen
from metric_grid.config import load_config
from metric_grid.model import harm
from metric_grid.model import optimizer as op


def main(n_samples: int = 120, seed: int = 0) -> int:
    cfg, z, c = load_config(), frozen.load_zones(), frozen.load_constants()
    zh = harm.compute_harm(z, cfg, c["kw_per_job"]).sort_values("zone_id").reset_index(drop=True)
    T = c["T_NC08_mw"]
    lo, hi = T, T * (1 + cfg["optimizer"]["band_pct"] / 100)
    ids = [int(i) for i in zh["zone_id"]]
    L, prot = dict(zip(ids, zh["L_mw"])), dict(zip(ids, zh["protected"]))
    S = zh.set_index("zone_id")

    def metrics(sel):
        s = S.loc[sel]
        return {"zones": len(sel), "mw": s["L_mw"].sum(), "households": s["N_households"].sum(),
                "electric_heat_hh": s["heat_electricity"].sum(), "vuln_weighted_hh": s["H_human"].sum(), "cost_2013$": s["H_econ"].sum()}

    rng, rows = np.random.default_rng(seed), []
    for _ in range(n_samples):
        obj = {i: L[i] * rng.uniform(0.5, 1.5) for i in ids}
        sel = op._solve_stage(ids, L, prot, lo, hi, obj, 1e-3, 10)
        if sel:
            rows.append(metrics(sel))
    d = pd.DataFrame(rows)
    pair = op.solve(zh, T, cfg["harm"]["alpha_default"])
    b, w = metrics(pair.baseline.zone_ids), metrics(pair.weighted.zone_ids)
    print(f"{len(d)} sampled plans in the band {lo:.1f} to {hi:.1f} MW")
    print(d.describe(percentiles=[0.05, 0.5, 0.95]).loc[["min", "5%", "50%", "95%", "max"]].round(0).to_string())
    print("shipped load-only baseline:", {k: round(v) for k, v in b.items()})
    print("vulnerability-aware plan  :", {k: round(v) for k, v in w.items()})
    for k, better in (("vuln_weighted_hh", ">"), ("electric_heat_hh", ">"), ("cost_2013$", ">"), ("households", "<")):
        share = (d[k] > w[k]).mean() if better == ">" else (d[k] < w[k]).mean()
        word = "MORE" if better == ">" else "FEWER"
        print(f"  {100 * share:.0f}% of sampled plans have {word} {k} than the vulnerability-aware plan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
