"""Harm model (spec Phase 4.1): two separate quantities with units, then a user-weighted blend.

    N_i        occupied households (ACS B25003_001)           SVI_i  RPL_THEMES (CDC/ATSDR SVI 2022)
    EHeat_i    share of occupied units heated by electricity   J_i,s  LODES jobs by sector
    H_human_i  = N_i * (w_s * SVI_i + w_e * EHeat_i)           [households x dimensionless]
    H_econ_i   = N_i * c_res * h + sum_s J_i,s * c_s * h        [US 2013 dollars]
    Hhat_*_i   = H_*_i / max_j H_*_j  (max over zones with data)
    H_i(alpha) = alpha * Hhat_human_i + (1 - alpha) * Hhat_econ_i

Missing data is never zero-filled: a zone with households but no SVI/EHeat gets NaN H_human, a visible warning, and is
excluded from the normalization maximum; the optimizer refuses to select NaN zones. A zone with 0 households has
H_human = 0 by definition (N_i = 0), which is not a fill.
"""
import warnings

import numpy as np
import pandas as pd

SECTOR_COLS = {"manufacturing": "jobs_manufacturing", "retail": "jobs_retail", "health": "jobs_health"}


class MissingDataWarning(UserWarning):
    """Raised (as a warning) when a zone lacks inputs the harm model needs."""


class MissingDataError(ValueError):
    """The optimizer was asked to price a zone whose harm is unknown."""


def commercial_cost_per_job(cfg: dict, kw_per_job: float, commercial_class: str | None = None) -> dict:
    """$ per job for h hours, by sector: ICE $/average-kW (one class for all sectors) x ComStock kW per job x h."""
    h = cfg["harm"]["h_hours"]
    if h != 1:
        raise ValueError("only h = 1 hour is supported (ICE inputs are the 1-hour column)")
    ice = cfg["harm"]["ice"]
    cls = commercial_class or ice["commercial_class"]
    per_kw = {"medium_large": ice["medium_large_ci_per_avg_kw_1h"], "small": ice["small_ci_per_avg_kw_1h"]}[cls]
    c = per_kw * kw_per_job * h
    return {"manufacturing": c, "retail": c, "health": c, "other": c}


def compute_harm(zones: pd.DataFrame, cfg: dict, kw_per_job: float, w_svi: float | None = None,
                 w_eheat: float | None = None, commercial_class: str | None = None) -> pd.DataFrame:
    """Return a copy of zones with N_households, EHeat, H_human, H_econ, Hhat_human, Hhat_econ (+ jobs_other, cost columns)."""
    ws = cfg["harm"]["w_svi"] if w_svi is None else w_svi
    we = cfg["harm"]["w_eheat"] if w_eheat is None else w_eheat
    h = cfg["harm"]["h_hours"]
    c_res = cfg["harm"]["ice"]["residential_per_household_1h"]
    c_job = commercial_cost_per_job(cfg, kw_per_job, commercial_class)
    z = zones.copy()
    z["N_households"] = z["occupied_units"]
    z["jobs_other"] = z["jobs_total"] - sum(z[c] for c in SECTOR_COLS.values())
    if (z["jobs_other"] < 0).any():
        raise ValueError("sector jobs exceed total jobs")

    base = z["N_households"] * (ws * z["RPL_THEMES"] + we * z["share_electric_heat"])
    z["H_human"] = np.where(z["N_households"] == 0, 0.0, base)  # 0 households -> 0 by definition; NaN only if N > 0
    bad = z[z["H_human"].isna()]
    if len(bad):
        warnings.warn(f"{len(bad)} zone(s) have households but no SVI/electric-heat data (zone_id {bad['zone_id'].tolist()}): "
                      "H_human is missing, they are excluded from normalization and cannot be selected.", MissingDataWarning)
    nodata_zero = z[z["svi_missing"] & (z["N_households"] == 0)] if "svi_missing" in z else z.iloc[0:0]
    if len(nodata_zero):
        ids = ", ".join(str(i) for i in nodata_zero["zone_id"])
        warnings.warn(f"Zone {ids} has no SVI data but 0 occupied households, so its H_human is 0 by definition (not a zero-fill); "
                      "it is included in normalization as 0 and shown grey on the maps.", MissingDataWarning)

    z["H_econ"] = (z["N_households"] * c_res * h
                   + sum(z[col] * c_job[s] * h for s, col in SECTOR_COLS.items()) + z["jobs_other"] * c_job["other"] * h)
    for q in ("human", "econ"):
        mx = z[f"H_{q}"].max()  # NaN skipped by pandas: normalization excludes missing zones
        z[f"Hhat_{q}"] = z[f"H_{q}"] / mx if mx > 0 else np.nan
    z.attrs["w_svi"], z.attrs["w_eheat"] = ws, we
    return z


def blend(z: pd.DataFrame, alpha: float) -> pd.Series:
    """H_i(alpha) = alpha * Hhat_human + (1 - alpha) * Hhat_econ (NaN where either is missing)."""
    if not 0 <= alpha <= 1:
        raise ValueError("alpha must be in [0, 1]")
    return alpha * z["Hhat_human"] + (1 - alpha) * z["Hhat_econ"]
