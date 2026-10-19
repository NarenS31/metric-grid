"""District scaling (spec rule 4): never allocate BA demand or the regional reduction into the district directly.

    D_NC08 = sum_g  D_g * W_district_in_g / W_g       (D_g: the hour ending 07:00)        (modeled district estimate)
    T_NC08 = sum_g  D_NC08_g * r_g,   r_g = shed_g / D_g
with a consistent modeled weight W = housing_units * kW/unit + jobs * kW/job.
"""
import pandas as pd


def weight(housing_units, jobs, kw_per_unit: float, kw_per_job: float):
    """Modeled weight W (kW) from housing units and jobs. Works on scalars or Series."""
    return housing_units * kw_per_unit + jobs * kw_per_job


def group_weights(counties: pd.DataFrame, kw_per_unit: float, kw_per_job: float) -> pd.Series:
    """W_g = sum over counties of share * W_county, indexed by group key. `counties` needs share, group, housing_units, jobs_total."""
    w = weight(counties["housing_units"], counties["jobs_total"], kw_per_unit, kw_per_job) * counties["share"]
    return w.groupby(counties["group"]).sum()


def district_weights_by_group(tracts: pd.DataFrame, counties: pd.DataFrame, state_fips: str,
                              kw_per_unit: float, kw_per_job: float) -> pd.Series:
    """W_district_in_g: tract weights, split across groups by each tract's county share. tracts need GEOID, housing_units, jobs_total."""
    t = tracts.assign(geoid5=tracts["GEOID"].str[:5], W=weight(tracts["housing_units"], tracts["jobs_total"], kw_per_unit, kw_per_job))
    shares = counties[counties["geoid5"].str.startswith(state_fips)][["geoid5", "group", "share"]]
    m = t.merge(shares, on="geoid5", how="left")
    if m["group"].isna().any():
        raise ValueError(f"district counties not in any footprint: {sorted(m[m['group'].isna()]['geoid5'].unique())}")
    return (m["W"] * m["share"]).groupby(m["group"]).sum()


def district_scaling(demand_mw: dict, shed_mw: dict, w_district: pd.Series, w_group: pd.Series) -> dict:
    """Return D_NC08, T_NC08 (MW) and per-group parts. All values are modeled district estimates."""
    parts = {}
    for g, d in demand_mw.items():
        wd = float(w_district.get(g, 0.0))
        d_g = d * wd / float(w_group[g])
        r_g = shed_mw[g] / d
        parts[g] = {"D_group_mw": d, "r": r_g, "W_district": wd, "W_group": float(w_group[g]),
                    "share_of_group": wd / float(w_group[g]), "D_district_mw": d_g, "T_district_mw": d_g * r_g}
    D = sum(p["D_district_mw"] for p in parts.values())
    T = sum(p["T_district_mw"] for p in parts.values())
    return {"D_NC08_mw": D, "T_NC08_mw": T, "r_effective": T / D, "groups": parts, "source": "modeled district estimate"}


def override_shared(counties: pd.DataFrame, group: str) -> pd.DataFrame:
    """Extreme case for sensitivity: every shared county goes wholly to `group` (shares 1.0 / 0.0)."""
    c = counties.copy()
    c.loc[c["shared"], "share"] = (c.loc[c["shared"], "group"] == group).astype(float)
    return c[c["share"] > 0]


def run_scaling(cfg: dict, counties: pd.DataFrame, tracts: pd.DataFrame, demand_mw: dict, shed_mw: dict,
                kw_per_unit: float, kw_per_job: float) -> dict:
    """District scaling for one county->group table. `tracts` needs GEOID, housing_units, jobs_total."""
    wg = group_weights(counties, kw_per_unit, kw_per_job)
    wd = district_weights_by_group(tracts, counties, cfg["district"]["state_fips"], kw_per_unit, kw_per_job)
    out = district_scaling(demand_mw, shed_mw, wd, wg)
    out["W_NC08_kw"] = float(wd.sum())
    return out


def allocate_zone_loads(zones: pd.DataFrame, d_district_mw: float, kw_per_unit: float, kw_per_job: float) -> pd.DataFrame:
    """Add W_i (kW) and L_i (MW) per zone: L_i = D_NC08 * W_i / sum_j W_j, so sum L_i = D_NC08.

    Zones with missing housing units or jobs are an error here (no silent zero-fill).
    """
    if zones["housing_units"].isna().any() or zones["jobs_total"].isna().any():
        raise ValueError("zones with missing housing_units or jobs_total cannot be allocated load")
    z = zones.copy()
    z["W_kw"] = weight(z["housing_units"], z["jobs_total"], kw_per_unit, kw_per_job)
    z["L_mw"] = d_district_mw * z["W_kw"] / z["W_kw"].sum()
    z["L_source"] = "modeled district estimate"
    return z
