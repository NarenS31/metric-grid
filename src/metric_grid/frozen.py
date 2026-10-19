"""Runtime reader for data/frozen/. The app and every model import data only through here (no network, no data/raw)."""
import json

import geopandas as gpd
import pandas as pd

from metric_grid.config import ROOT

FROZEN = ROOT / "data" / "frozen"


def load_constants() -> dict:
    """constants.json: scenario, D_NC08, T_NC08, per-utility parts, weights, sensitivity rows, dataset list."""
    return json.loads((FROZEN / "constants.json").read_text())


def load_zones() -> gpd.GeoDataFrame:
    """Final zones (WGS84) with attributes, protected flag, W_kw and L_mw."""
    return gpd.read_file(FROZEN / "zones.geojson")


def load_facilities() -> gpd.GeoDataFrame:
    """All facility points; `protected` marks the hard-exclusion types."""
    return gpd.read_file(FROZEN / "facilities.geojson")


def load_demand() -> pd.DataFrame:
    """Hourly EIA-930 demand per utility group (DEC, DEP) for 2022-12-22..26 with local time."""
    return pd.read_csv(FROZEN / "demand_groups.csv")


def load_district() -> gpd.GeoDataFrame:
    """NC-08 boundary (WGS84, simplified), drawn as an outline on every map."""
    return gpd.read_file(FROZEN / "district.geojson")
