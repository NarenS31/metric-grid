"""Phase 3 tests: area-weighted join, protected flags, load allocation, frozen outputs, offline app render."""
import socket
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metric_grid import frozen
from metric_grid.config import ROOT, load_config
from metric_grid.geometry import zones as zmod
from metric_grid.geometry.allocate import area_weighted_join
from metric_grid.model import load_allocation as la

PROCESSED = ROOT / "data" / "raw" / "processed"


# ---------- logic tests (synthetic) ----------

def _tracts():
    return gpd.GeoDataFrame({"GEOID": ["A", "B"], "hu": [100.0, 50.0], "svi": [0.2, 0.8]},
                            geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10)], crs=5070)


def test_area_join_sums_by_tract_fraction_and_means_by_overlap_area():
    zone = gpd.GeoDataFrame({"zone_id": [1]}, geometry=[box(5, 0, 15, 10)], crs=5070)  # half of A, half of B
    out = area_weighted_join(zone, _tracts(), ["hu"], ["svi"])
    assert out.loc[1, "hu"] == pytest.approx(100 * 0.5 + 50 * 0.5)
    assert out.loc[1, "svi"] == pytest.approx(0.5)  # equal overlap areas


def test_area_join_missing_stays_nan_never_zero():
    t = _tracts(); t.loc[:, "svi"] = np.nan; t.loc[0, "hu"] = np.nan; t.loc[1, "hu"] = np.nan
    zone = gpd.GeoDataFrame({"zone_id": [1]}, geometry=[box(0, 0, 20, 10)], crs=5070)
    out = area_weighted_join(zone, t, ["hu"], ["svi"])
    assert np.isnan(out.loc[1, "svi"]) and np.isnan(out.loc[1, "hu"])


def test_area_join_ignores_nan_tract_in_mean():
    t = _tracts(); t.loc[0, "svi"] = np.nan
    zone = gpd.GeoDataFrame({"zone_id": [1]}, geometry=[box(0, 0, 20, 10)], crs=5070)
    assert area_weighted_join(zone, t, ["hu"], ["svi"]).loc[1, "svi"] == pytest.approx(0.8)


def test_flag_protected_counts_only_protected_types():
    z = gpd.GeoDataFrame({"zone_id": [1, 2]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs=4326)
    f = gpd.GeoDataFrame({"facility_type": ["hospital", "police"]}, geometry=[Point(0.5, 0.5), Point(1.5, 0.5)], crs=4326)
    out = zmod.flag_protected(z, f, ["hospital"]).set_index("zone_id")
    assert out.loc[1, "protected"] and not out.loc[2, "protected"]
    assert out.loc[2, "n_police"] == 1  # display-only type still counted


def test_allocate_zone_loads_sums_to_district_demand():
    z = pd.DataFrame({"housing_units": [100.0, 300.0], "jobs_total": [10.0, 50.0]})
    out = la.allocate_zone_loads(z, 1000.0, 5.0, 1.0)
    assert out["L_mw"].sum() == pytest.approx(1000.0)
    assert out["L_mw"][1] / out["L_mw"][0] == pytest.approx((300 * 5 + 50) / (100 * 5 + 10))
    assert (out["L_source"] == "modeled district estimate").all()


def test_allocate_missing_inputs_raises():
    with pytest.raises(ValueError):
        la.allocate_zone_loads(pd.DataFrame({"housing_units": [1.0, np.nan], "jobs_total": [1.0, 1.0]}), 10.0, 5.0, 1.0)


def test_unimplemented_substation_mode_is_explicit():
    cfg = load_config(); cfg["zones"]["zone_mode"] = "substation"
    with pytest.raises(NotImplementedError):
        zmod.build_zones(cfg, None, None)


# ---------- frozen-output tests (data/frozen is committed) ----------

def test_frozen_zone_loads_sum_to_d_nc08():
    z, c = frozen.load_zones(), frozen.load_constants()
    assert z["L_mw"].sum() == pytest.approx(c["D_NC08_mw"], rel=1e-9)
    assert z["L_mw"].notna().all() and (z["L_mw"] > 0).all()


def test_frozen_scaling_consistent_with_groups():
    c = frozen.load_constants()
    assert sum(g["D_district_mw"] for g in c["groups"].values()) == pytest.approx(c["D_NC08_mw"])
    assert sum(g["T_district_mw"] for g in c["groups"].values()) == pytest.approx(c["T_NC08_mw"])
    assert c["groups"]["DEC"]["r"] == pytest.approx(1000 / 20879) and c["groups"]["DEP"]["r"] == pytest.approx(961 / 13986)
    assert c["sources"]["D_NC08"] == "modeled district estimate"


def test_frozen_zone_ids_unique_and_stable_order():
    z = frozen.load_zones()
    assert z["zone_id"].is_unique and sorted(z["zone_id"]) == list(range(1, len(z) + 1))
    assert list(z.sort_values("zone_id")["GEOID"]) == sorted(z["GEOID"])
    assert (z["zone_kind"] == "census tract").all()


def test_frozen_protected_flags_match_option_a_only():
    z, c = frozen.load_zones(), frozen.load_constants()
    assert c["protected_types"] == ["hospital", "nursing_home", "water_treatment"]
    expect = (z[[f"n_{t}" for t in c["protected_types"]]].sum(axis=1) > 0)
    assert (z["protected"] == expect).all() and int(z["protected"].sum()) == c["n_protected"] == 26


def test_frozen_protected_load_share_below_limit():
    z, c = frozen.load_zones(), frozen.load_constants()
    share = z.loc[z["protected"], "L_mw"].sum() / c["D_NC08_mw"]
    assert share < 0.35  # leaves the optimizer room to make plans differ
    assert c["T_NC08_mw"] < z.loc[~z["protected"], "L_mw"].sum()  # target is feasible


def test_frozen_missing_svi_only_on_zero_housing_zone():
    z = frozen.load_zones()
    miss = z[z["RPL_THEMES"].isna()]
    assert len(miss) == 1 and (miss["housing_units"] == 0).all() and miss["svi_missing"].all()


def test_frozen_sensitivity_rows_include_dep_600():
    c = frozen.load_constants()
    dep600 = [r for r in c["sensitivity"] if "600" in r["case"]][0]
    assert dep600["T_NC08_mw"] == pytest.approx(78.1, abs=0.1) and dep600["D_NC08_mw"] == pytest.approx(c["D_NC08_mw"])


def test_frozen_district_outline_present():
    d = frozen.load_district()
    assert len(d) == 1 and d.geometry.iloc[0].is_valid


def test_r_definition_wording():
    assert "maximum firm load shed" in frozen.load_constants()["r_definition"]


@pytest.mark.skipif(not (PROCESSED / "tracts_joined.geojson").exists(), reason="run `make data` first")
def test_area_join_with_zones_equal_tracts_is_identity():
    t = gpd.read_file(PROCESSED / "tracts_joined.geojson")
    z = t[["GEOID", "geometry"]].assign(zone_id=range(len(t)))
    out = area_weighted_join(z, t, ["housing_units", "jobs_total"], ["RPL_THEMES"])
    assert out["housing_units"].to_numpy() == pytest.approx(t["housing_units"].to_numpy(), rel=1e-4)
    assert out["jobs_total"].to_numpy() == pytest.approx(t["jobs_total"].to_numpy(), rel=1e-4)
    both_nan = out["RPL_THEMES"].isna().to_numpy() == t["RPL_THEMES"].isna().to_numpy()
    assert both_nan.all()
