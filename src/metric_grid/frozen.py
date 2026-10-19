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


def load_demand_panel() -> dict | None:
    """Precomputed data for the "Why forecasts aren't enough" panel, or None if the file is missing or unreadable.
    The app hides the panel in that case; nothing else depends on it."""
    path = FROZEN / "demand_panel.json"
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except (OSError, ValueError):
        return None


def load_district() -> gpd.GeoDataFrame:
    """NC-08 boundary (WGS84, simplified), drawn as an outline on every map."""
    return gpd.read_file(FROZEN / "district.geojson")


def _json(name: str):
    return json.loads((FROZEN / name).read_text())


def load_presolved() -> list[dict]:
    """Pre-solved grid (alpha x target) used as the fallback when a live solve fails or is slow."""
    return _json("presolved.json")


def load_loadonly() -> dict:
    """The frozen load-only plan sets {key: {plans, typical_index, n, ...}} (see model/loadonly.py)."""
    return _json("loadonly_plans.json")


def load_sensitivity() -> dict:
    """Sensitivity settings table, always/sometimes/never zone classes, and spared zones."""
    return _json("sensitivity.json")


def load_scenarios() -> dict:
    """10/15/20% scenario rows and cut-in-all / only-worst zone lists."""
    return _json("scenarios.json")


def load_alpha_sweep() -> list[dict]:
    """alpha sweep rows (percent change in human harm and economic cost, households cut)."""
    return _json("alpha_sweep.json")
