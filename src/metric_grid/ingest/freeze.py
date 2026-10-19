"""Phase 3.4 `make freeze`: write the only runtime inputs to data/frozen/ from data/raw/processed/.

Outputs: district.geojson (NC-08 outline), zones.geojson (zones + attributes + L_i), facilities.geojson, demand_groups.csv, temp_kclt.csv, constants.json,
and model outputs presolved.json, sensitivity.json, scenarios.json, alpha_sweep.json.
"""
import json
from datetime import datetime, timezone

import geopandas as gpd
import pandas as pd

from metric_grid.config import load_config
from metric_grid.frozen import FROZEN
from metric_grid.geometry import zones as zmod
from metric_grid.ingest import eia930, footprints
from metric_grid.ingest.common import PROCESSED
from metric_grid.model import load_allocation as la
from metric_grid.model import scenarios as scen
from metric_grid.model import sensitivity as sens

SIMPLIFY_DEG = 0.0001  # ~10 m: keeps files small; geometry is for display, areas are not recomputed from it

DATASETS = [  # provenance list for the app's drawer (vintage per source; full notes in docs/DATA_SOURCES.md)
    {"name": "Census TIGER/Line 2024 (cd119, tracts)", "vintage": "2024", "url": "https://www2.census.gov/geo/tiger/TIGER2024/"},
    {"name": "Census ACS 5-year", "vintage": "2020-2024", "url": "https://api.census.gov/data/2024/acs/acs5"},
    {"name": "CDC/ATSDR Social Vulnerability Index", "vintage": "2022", "url": "https://svi.cdc.gov/"},
    {"name": "LEHD LODES8 WAC", "vintage": "2023", "url": "https://lehd.ces.census.gov/data/lodes/LODES8/"},
    {"name": "OpenStreetMap critical facilities via Overpass (coverage incomplete)", "vintage": "pulled 2026-10-18", "url": "https://overpass-api.de/"},
    {"name": "EIA-930 hourly demand (DUK, CPLE, CPLW)", "vintage": "2022-12-22..26", "url": "https://api.eia.gov/v2/electricity/rto/region-data/data/"},
    {"name": "EIA Form 861 (county to utility/BA assignment)", "vintage": "2024", "url": "https://www.eia.gov/electricity/data/eia861/"},
    {"name": "NREL End-Use Load Profiles, ResStock/ComStock AMY2018 release 2 (cold week 2018-01-01..07)", "vintage": "2024 release", "url": "https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/"},
    {"name": "SC Office of Regulatory Staff, DEC/DEP December 2022 outage report (shed amounts)", "vintage": "2023", "url": "https://ors.sc.gov/"},
    {"name": "FERC-NERC staff report on Winter Storm Elliott (shed amounts)", "vintage": "Nov 2023", "url": "https://www.ferc.gov/sites/default/files/2024-02/24_Winter-Storm_Elliot_0207_UPDATE.pdf"},
    {"name": "LBNL interruption cost estimates (ICE Calculator 2.0 report LBNL-6941E), 2013 dollars", "vintage": "2015", "url": "https://eta-publications.lbl.gov/sites/default/files/lbnl-6941e.pdf"},
    {"name": "EIA-930 bulk files, Dec 2017 to Dec 2018 (demand-model training history)", "vintage": "2017-2019", "url": "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/"},
    {"name": "KCLT and KRDU hourly temperature via Iowa Environmental Mesonet, winters 2018-2025 (demand-model inputs)", "vintage": "Dec 2017 to Feb 2025", "url": "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"},
    {"name": "KCLT ASOS temperature via Iowa Environmental Mesonet (display only)", "vintage": "2022-12-23..25", "url": "https://mesonet.agron.iastate.edu/"},
]


def scaling_cases(cfg, tracts, demand, shed, kwu, kwj) -> list[dict]:
    """Default result plus sensitivity rows (shared-county rules, DEP at its level during that hour)."""
    cs = pd.read_csv(PROCESSED / "county_groups.csv", dtype={"geoid5": str})
    eq = pd.read_csv(PROCESSED / "county_groups_equal.csv", dtype={"geoid5": str})
    shed_dep600 = {**shed, "DEP": 600.0}
    cases = [("default: customer_spread, max shed (DEC 1,000 / DEP 961 MW)", cs, shed),
             ("DEP shed at its ~600 MW level early in that hour (DEC 1,000)", cs, shed_dep600),
             ("shared counties split equally", eq, shed),
             ("shared counties wholly DEC", la.override_shared(cs, "DEC"), shed),
             ("shared counties wholly DEP", la.override_shared(cs, "DEP"), shed)]
    rows = []
    for name, c, sh in cases:
        r = la.run_scaling(cfg, c, tracts, demand, sh, kwu, kwj)
        rows.append({"case": name, "D_NC08_mw": r["D_NC08_mw"], "T_NC08_mw": r["T_NC08_mw"], "r_effective": r["r_effective"]})
    return rows


def freeze() -> dict:
    """Build zones, scale demand to the district, allocate L_i, write data/frozen/. Returns the constants dict."""
    cfg = load_config()
    joined = gpd.read_file(PROCESSED / "tracts_joined.geojson")
    fac = gpd.read_file(PROCESSED / "facilities.geojson")
    zones = zmod.build_zones(cfg, joined, fac)

    res = json.loads((PROCESSED / "resstock_nc_per_unit.json").read_text())
    nc_jobs = footprints.county_jobs(footprints.FIPS_STATE[cfg["district"]["state_fips"]], cfg)["jobs_total"].sum()
    kwu, kwj = res["kw_per_unit"], res["comstock_kw_nc"] / nc_jobs

    eia = pd.read_csv(PROCESSED / "eia930_demand.csv", parse_dates=["period_utc"])
    eia["local_time"] = eia["period_utc"].dt.tz_convert(cfg["scenario"]["local_tz"])
    wide = eia930.group_demand(eia, cfg)
    rr = eia930.reduction_ratios(wide, cfg)
    demand = {k: v["demand_mw_0700"] for k, v in rr.items()}
    shed = {k: v["shed_mw"] for k, v in rr.items()}

    cs = pd.read_csv(PROCESSED / "county_groups.csv", dtype={"geoid5": str})
    tr = joined[["GEOID", "housing_units", "jobs_total"]]
    sc = la.run_scaling(cfg, cs, tr, demand, shed, kwu, kwj)
    zones = la.allocate_zone_loads(zones, sc["D_NC08_mw"], kwu, kwj)

    FROZEN.mkdir(parents=True, exist_ok=True)
    out = zones.copy()
    out["geometry"] = out.geometry.simplify(SIMPLIFY_DEG, preserve_topology=True)
    out.to_crs(4326).to_file(FROZEN / "zones.geojson", driver="GeoJSON")
    dist = gpd.read_file(PROCESSED / "district.geojson")
    dist["geometry"] = dist.geometry.simplify(SIMPLIFY_DEG, preserve_topology=True)
    dist[["STATEFP", "CD119FP", "geometry"]].to_file(FROZEN / "district.geojson", driver="GeoJSON")
    f = fac.copy()
    f["protected"] = f["facility_type"].isin(cfg["facilities"]["protected_types"])
    f.to_file(FROZEN / "facilities.geojson", driver="GeoJSON")
    wide.assign(local_time=wide["local_time"].astype(str)).to_csv(FROZEN / "demand_groups.csv", index=False)
    pd.read_csv(PROCESSED / "kclt_temp.csv").to_csv(FROZEN / "temp_kclt.csv", index=False)

    consts = {
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scenario": cfg["scenario"], "district": cfg["district"],
        "zone_mode": cfg["zones"]["zone_mode"], "zone_note": zmod.ZONE_NOTE,
        "n_zones": int(len(zones)), "n_protected": int(zones["protected"].sum()),
        "protected_types": cfg["facilities"]["protected_types"], "display_only_types": cfg["facilities"]["display_only_types"],
        "kw_per_unit": kwu, "kw_per_job": kwj, "commercial_scope": cfg["weights"]["commercial_scope"],
        "D_NC08_mw": sc["D_NC08_mw"], "T_NC08_mw": sc["T_NC08_mw"], "r_effective": sc["r_effective"],
        "W_NC08_kw": sc["W_NC08_kw"], "groups": sc["groups"],
        "r_definition": "each utility's maximum firm load shed that morning / its demand in the hour ending 07:00 (06:00-07:00); not a snapshot of the shed in that hour",
        "sensitivity": scaling_cases(cfg, tr, demand, shed, kwu, kwj),
        "protected_load_mw": float(zones.loc[zones["protected"], "L_mw"].sum()),
        "sources": {"zone_load": "modeled district estimate", "D_NC08": "modeled district estimate", "T_NC08": "modeled district estimate"},
        "datasets": DATASETS,
    }
    (FROZEN / "constants.json").write_text(json.dumps(consts, indent=2, default=str))
    write_model_outputs(cfg, zones, kwj, consts)
    return consts


def _dump(name: str, obj) -> None:
    def conv(o):
        return o.item() if hasattr(o, "item") else str(o)
    (FROZEN / name).write_text(json.dumps(obj, indent=1, default=conv))


def write_model_outputs(cfg: dict, zones: gpd.GeoDataFrame, kw_per_job: float, consts: dict) -> None:
    """Plan sets, the pre-solved demo grid, the sensitivity table, the 10/15/20% scenarios and the alpha sweep -> data/frozen/."""
    from metric_grid.model import loadonly

    z = pd.DataFrame(zones.drop(columns="geometry"))
    D, T = consts["D_NC08_mw"], consts["T_NC08_mw"]
    sets = loadonly.build_sets(z, cfg, kw_per_job, D, T)
    lo = cfg["optimizer"]["loadonly"]
    _dump("loadonly_plans.json", {"method": {"n_plans": lo["n_plans"], "near_opt_pct": lo["near_opt_pct"], "seed": lo["seed"], "spread": lo["spread"],
                                             "text": loadonly.__doc__.split("\n\n")[1] + " " + loadonly.__doc__.split("\n\n")[2]},
                                  "sets": sets})
    _dump("presolved.json", scen.presolve_grid(z, cfg, kw_per_job, D, T, sets))
    res = sens.full_sensitivity(z, cfg, kw_per_job, D, T, sets)
    prio = sens.priority_list(z, res, cfg)
    _dump("sensitivity.json", {"rows": res["rows"].to_dict("records"), "classes": res["classes"],
                               "default_baseline_ids": res["default_baseline_ids"], "priority_list": prio.to_dict("records")})
    sc = scen.run_scenarios(z, cfg, kw_per_job, D, sets)
    _dump("scenarios.json", {"rows": sc["rows"].to_dict("records"), "cut_in_all": sc["cut_in_all"], "only_worst": sc["only_worst"],
                             "worst_pct": sc["worst_pct"]})
    _dump("alpha_sweep.json", sens.alpha_sweep(z, cfg, kw_per_job, D, T, sets).to_dict("records"))
    from metric_grid import figures  # matplotlib, only needed at freeze time

    figures.alpha_tradeoff_figure(FROZEN / "alpha_tradeoff.png", compact=True)
    figures.alpha_tradeoff_figure()  # docs copy


if __name__ == "__main__":
    c = freeze()
    print(f"zones {c['n_zones']}, protected {c['n_protected']}, D_NC08 {c['D_NC08_mw']:.1f} MW, T_NC08 {c['T_NC08_mw']:.1f} MW")
