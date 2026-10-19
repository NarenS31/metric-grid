"""App data layer: frozen inputs, harm columns, pre-solved lookups, cached live solves, nearest-result fallback."""
import warnings

import numpy as np
import streamlit as st

from metric_grid import frozen
from metric_grid.config import load_config
from metric_grid.model import harm, loadonly, scenarios
from metric_grid.model.harm import MissingDataWarning


@st.cache_resource(show_spinner=False)
def load_all() -> dict:
    """Everything the page reads, loaded once: constants, zones (with harm columns), pre-solved grid, sensitivity, figures."""
    cfg, consts, zones = load_config(), frozen.load_constants(), frozen.load_zones()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", MissingDataWarning)
        zh = harm.compute_harm(zones, cfg, consts["kw_per_job"])
    lo_all = frozen.load_loadonly()
    lo_sets = lo_all["sets"]
    lo_metrics = {k: loadonly.plan_metrics(zh, v["plans"]) for k, v in lo_sets.items()}
    lo_counts = {}
    for k, v in lo_sets.items():
        c = {}
        for plan in v["plans"]:
            for i in plan:
                c[i] = c.get(i, 0) + 1
        lo_counts[k] = c
    return {"cfg": cfg, "consts": consts, "zones": zones, "zh": zh, "warnings": [str(w.message) for w in caught],
            "lo_sets": lo_sets, "loadonly_method": lo_all["method"], "lo_metrics": lo_metrics, "lo_counts": lo_counts,
            "presolved": frozen.load_presolved(), "sens": frozen.load_sensitivity(), "sweep": frozen.load_alpha_sweep(),
            "district": frozen.load_district(), "panel": frozen.load_demand_panel(), "facilities": frozen.load_facilities(), "demand": frozen.load_demand()}


def pct_options(consts: dict, cfg: dict) -> list[float]:
    """Slider stops: the Elliott-anchored target first (the default), then the configured presets. No off-grid stops, so every
    stop is pre-solved and instant."""
    elliott = 100 * consts["T_NC08_mw"] / consts["D_NC08_mw"]
    return [elliott] + sorted(cfg["optimizer"]["target_pcts"])


def target_for(pct: float, consts: dict) -> tuple[str, float]:
    """(pre-solved key, MW) for a slider percentage. The first option is the Elliott target and uses T_NC08 exactly."""
    elliott = 100 * consts["T_NC08_mw"] / consts["D_NC08_mw"]
    if abs(pct - elliott) < 1e-9:
        return "elliott", consts["T_NC08_mw"]
    return (f"{pct:g}", consts["D_NC08_mw"] * pct / 100)


def nearest_presolved(alpha: float, target_mw: float, consts: dict, presolved: list[dict], cap: bool = False) -> dict:
    """Closest solved pre-computed record by alpha and target (target distance in points of modeled load).

    Prefers records with the same county-cap setting; falls back to any solved record."""
    D = consts["D_NC08_mw"]
    ok = [r for r in presolved if r["solved"] and r["cap"] == cap] or [r for r in presolved if r["solved"]]
    return min(ok, key=lambda r: abs(r["alpha"] - alpha) + abs(r["target_mw"] - target_mw) / D * 100 / 10)


def get_view(alpha: float, pct: float, cap_on: bool) -> dict:
    """Result for the current controls, from the pre-solved grid (every slider stop is pre-solved, so nothing is solved live).

    If the exact setting is missing or was infeasible, shows the nearest pre-solved result with a visible note that gives the
    reason. The result carries the matching load-only plan set key, so the page can show the whole distribution.
    """
    A = load_all()
    consts, cfg = A["consts"], A["cfg"]
    key, target = target_for(pct, consts)
    cap = cfg["optimizer"]["county_cap"]["max_share"] if cap_on else None
    exact = [r for r in A["presolved"] if r["target_key"] == key and abs(r["alpha"] - alpha) < 1e-9 and r["cap"] == (cap is not None)]
    if exact and exact[0]["solved"]:
        return {"pair": scenarios.record_to_pair(exact[0]), "record": exact[0], "source": "pre-solved", "note": None,
                "cap_applied": cap is not None, "infeasible": False}
    near = nearest_presolved(alpha, target, consts, A["presolved"], cap is not None)
    infeasible = bool(exact and not exact[0]["solved"])
    if infeasible:
        note = (f"This target cannot be met: {exact[0]['reason']} (maximum feasible reduction {exact[0]['max_feasible_mw']:.1f} MW). "
                f"Showing the nearest pre-computed setting (alpha {near['alpha']:.2f}, {near['target_mw']:.0f} MW target).")
    else:
        note = (f"Showing nearest pre-computed setting (alpha {near['alpha']:.2f}, {near['target_mw']:.0f} MW target) because this "
                "setting is not pre-computed.")
    return {"pair": scenarios.record_to_pair(near), "record": near, "source": "nearest", "note": note, "cap_applied": bool(near["cap"]),
            "infeasible": infeasible}
