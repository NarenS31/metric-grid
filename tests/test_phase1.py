"""Phase 1 tests: tract selection, GEOID joins, and no silent NaN fills.

Logic tests use tiny synthetic frames (no network, no data files). Data tests run against
data/raw/processed/ and are skipped with a visible reason if `make data` has not been run.
"""
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metric_grid.config import ROOT, load_config
from metric_grid.ingest import acs, district, facilities, lodes, svi

PROCESSED = ROOT / "data" / "raw" / "processed"
needs_data = pytest.mark.skipif(not (PROCESSED / "tracts_joined.geojson").exists(), reason="run `make data` first")

EXPECTED_TRACTS = 183  # NC-08 under TIGER 2024 tracts with the centroid-or-50%-overlap rule


# ---------- logic tests (synthetic) ----------

def test_svi_missing_sentinel_becomes_nan_not_zero():
    raw = pd.DataFrame({"FIPS": ["37001000100", "37001000200"], "COUNTY": ["A", "A"],
                        "RPL_THEMES": [-999, 0.4], "RPL_THEME1": [0.1, 0.2], "RPL_THEME2": [0.1, 0.2],
                        "RPL_THEME3": [0.1, 0.2], "RPL_THEME4": [-999, 0.2]})
    out = svi.clean_svi(raw, -999)
    assert np.isnan(out.loc[0, "RPL_THEMES"]) and np.isnan(out.loc[0, "RPL_THEME4"])
    assert out.loc[1, "RPL_THEMES"] == 0.4


def test_acs_negative_sentinel_and_electric_share():
    raw = pd.DataFrame({k: ["10"] for k in acs.VARS}).assign(state="37", county="001", tract="000100")
    raw.loc[0, "B19013_001E"] = "-666666666"
    raw.loc[0, "B25003_001E"] = "200"
    raw.loc[0, "B25040_004E"] = "50"
    out = acs.clean_acs(raw)
    assert out.loc[0, "GEOID"] == "37001000100"
    assert np.isnan(out.loc[0, "median_income"])
    assert out.loc[0, "share_electric_heat"] == 0.25


def test_electric_share_zero_occupied_is_nan():
    s = acs.share_electric_heat(pd.Series([0.0]), pd.Series([0.0]))
    assert s.isna().all()


def test_lodes_block_to_tract_sums():
    wac = pd.DataFrame({"w_geocode": ["370010001001001", "370010001002002", "370010002001001"],
                        "C000": [5, 7, 3], "CNS05": [1, 1, 0], "CNS07": [2, 0, 1], "CNS16": [0, 4, 2]})
    out = lodes.blocks_to_tracts(wac).set_index("GEOID")
    assert out.loc["37001000100", "jobs_total"] == 12
    assert out.loc["37001000200", "jobs_health"] == 2


def test_tract_selection_centroid_or_half_overlap():
    dist = gpd.GeoDataFrame(geometry=[box(0, 0, 10, 10)], crs=5070)
    tracts = gpd.GeoDataFrame({"GEOID": ["in", "out", "edge_half_but_centroid_out", "mostly_in_centroid_out"]},
                              geometry=[box(1, 1, 2, 2), box(20, 20, 21, 21),
                                        box(9, 0, 13, 4),      # 25% overlap, centroid x=11 outside
                                        box(-1, 0, 5, 2)],     # 83% overlap, centroid x=2 inside
                              crs=5070)
    kept = district.select_tracts(tracts, dist, 0.5)
    assert sorted(kept.GEOID) == ["in", "mostly_in_centroid_out"]


def test_join_rejects_duplicate_geoid_and_keeps_nan():
    tr = gpd.GeoDataFrame({"GEOID": ["a", "b"]}, geometry=[Point(0, 0), Point(1, 1)], crs=4326)
    acs_df = pd.DataFrame({"GEOID": ["a", "b"], "x": [1.0, np.nan]})
    svi_df = pd.DataFrame({"GEOID": ["a", "b"], "RPL_THEMES": [0.5, np.nan]})
    lodes_df = pd.DataFrame({"GEOID": ["a", "b"], "jobs_total": [3, 4]})
    out = district.join_attributes(tr, acs_df, svi_df, lodes_df)
    assert len(out) == 2 and out["RPL_THEMES"].isna().sum() == 1  # NaN preserved, not zero-filled
    with pytest.raises(ValueError):
        district.join_attributes(tr, pd.concat([acs_df, acs_df]), svi_df, lodes_df)


def test_overpass_elements_use_center_for_ways():
    els = [{"type": "node", "id": 1, "lat": 35.0, "lon": -80.0, "tags": {"name": "N"}},
           {"type": "way", "id": 2, "center": {"lat": 35.1, "lon": -80.1}},
           {"type": "way", "id": 3}]
    rows = facilities.elements_to_points(els, "hospital")
    assert [r["osm_id"] for r in rows] == ["node/1", "way/2"]


# ---------- data tests (need `make data`) ----------

@needs_data
def test_tract_count_stable():
    j = gpd.read_file(PROCESSED / "tracts_joined.geojson")
    assert len(j) == EXPECTED_TRACTS


@needs_data
def test_geoids_clean_and_unique():
    j = gpd.read_file(PROCESSED / "tracts_joined.geojson", dtype={"GEOID": str})
    assert j.GEOID.str.fullmatch(r"37\d{9}").all()
    assert j.GEOID.is_unique
    assert set(j.COUNTYFP) == set(j.GEOID.str[2:5])


@needs_data
def test_no_silent_nan_fills():
    """Missing SVI stays NaN; the only such tract is a zero-housing tract. No placeholder zeros in SVI."""
    j = gpd.read_file(PROCESSED / "tracts_joined.geojson")
    missing = j[j.RPL_THEMES.isna()]
    assert (missing.housing_units == 0).all()
    assert (j.RPL_THEMES.dropna() >= 0).all() and (j.RPL_THEMES.dropna() <= 1).all()
    assert not (j.RPL_THEMES == -999).any()


@needs_data
def test_facility_types_present():
    f = gpd.read_file(PROCESSED / "facilities.geojson")
    assert {"hospital", "nursing_home", "fire_station", "police"} <= set(f.facility_type)
