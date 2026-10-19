"""App data layer: frozen inputs, harm columns, pre-solved lookups, cached live solves, nearest-result fallback."""
import warnings

import streamlit as st

from metric_grid import frozen
from metric_grid.config import load_config
from metric_grid.model import harm, optimizer, scenarios
from metric_grid.model.harm import MissingDataWarning

SLOW_SECONDS = 2.0


@st.cache_resource(show_spinner=False)
def load_all() -> dict:
    """Everything the page reads, loaded once: constants, zones (with harm columns), pre-solved grid, sensitivity, figures."""
    cfg, consts, zones = load_config(), frozen.load_constants(), frozen.load_zones()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", MissingDataWarning)
        zh = harm.compute_harm(zones, cfg, consts["kw_per_job"])
    return {"cfg": cfg, "consts": consts, "zones": zones, "zh": zh, "warnings": [str(w.message) for w in caught],
            "presolved": frozen.load_presolved(), "sens": frozen.load_sensitivity(), "sweep": frozen.load_alpha_sweep(),
            "district": frozen.load_district(), "facilities": frozen.load_facilities(), "demand": frozen.load_demand()}


def pct_options(consts: dict, cfg: dict) -> list[float]:
    """Slider choices: the Elliott-anchored target first, then the presets and midpoints."""
    elliott = 100 * consts["T_NC08_mw"] / consts["D_NC08_mw"]
    presets = cfg["optimizer"]["target_pcts"]
    mids = [(a + b) / 2 for a, b in zip(presets, presets[1:])]
    return [elliott] + sorted(presets + mids)


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


@st.cache_data(show_spinner="Solving both plans…")
def _live_solve(alpha: float, target_mw: float, cap: float | None) -> dict:
    """Solve both plans live. Returns a plain dict (cacheable): record, or infeasible explanation, or error text."""
    A = load_all()
    o = A["cfg"]["optimizer"]
    try:
        r = optimizer.solve(A["zh"], target_mw, alpha, band_pct=o["band_pct"], widen_pct=tuple(o["band_widen_pct"]),
                            load_tol_mw=o["load_tol_mw"], max_seconds=1.5, county_cap=cap)
    except Exception as exc:  # shown as a visible note, never a crash
        return {"error": f"{type(exc).__name__}: {exc}"}
    if isinstance(r, optimizer.Infeasible):
        return {"infeasible": r.reason, "max_feasible_mw": r.max_feasible_mw}
    return {"record": scenarios.pair_to_record(r, "live", alpha, cap is not None), "elapsed": r.solve_seconds}


def get_view(alpha: float, pct: float, cap_on: bool) -> dict:
    """Result for the current controls: pre-solved when the setting is on the grid and the cap is off, live otherwise.

    Falls back to the nearest pre-solved result, with a visible note, if the live solve errors, is infeasible or takes > 2 s.
    """
    A = load_all()
    consts, cfg = A["consts"], A["cfg"]
    key, target = target_for(pct, consts)
    cap = cfg["optimizer"]["county_cap"]["max_share"] if cap_on else None
    pre = [r for r in A["presolved"] if r["target_key"] == key and abs(r["alpha"] - alpha) < 1e-9 and r["solved"]
           and r["cap"] == (cap is not None)]
    if pre:
        return {"pair": scenarios.record_to_pair(pre[0]), "source": "pre-solved", "note": None, "cap_applied": cap is not None}
    live = _live_solve(alpha, target, cap)
    if "record" in live and live["elapsed"] <= SLOW_SECONDS:
        return {"pair": scenarios.record_to_pair(live["record"]), "source": "live", "note": None, "cap_applied": cap is not None}
    near = nearest_presolved(alpha, target, consts, A["presolved"], cap is not None)
    why = (f"the live solve took {live['elapsed']:.1f} s" if "record" in live else live.get("infeasible") or live.get("error"))
    cap_txt = " The county cap is not applied in the pre-computed result." if cap is not None and not near["cap"] else ""
    note = (f"Showing nearest pre-computed setting (alpha {near['alpha']:.2f}, "
            f"{near['target_mw']:.0f} MW target) because {why}.{cap_txt}")
    return {"pair": scenarios.record_to_pair(near), "source": "nearest", "note": note, "cap_applied": bool(near["cap"])}
