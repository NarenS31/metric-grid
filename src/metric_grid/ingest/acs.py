"""Phase 1.2: ACS 5-year tract tables from the Census Data API.

B25001 housing units, B25034 year built, B25040 heating fuel (-> share_electric_heat), B19013 median income,
B25003 tenure, B01001 total population (display only; the harm model uses SVI for age, not a separate 65+ term).
Census negative sentinels (e.g. -666666666 for suppressed medians) become NaN; never zero-filled.
"""
import os

import numpy as np
import pandas as pd
import requests

from metric_grid.config import load_config, load_env
from metric_grid.ingest.common import PROCESSED, RAW, warn_missing

ACS_URL = "https://api.census.gov/data/{year}/acs/acs5"
VARS = {
    "B25001_001E": "housing_units",
    "B25003_001E": "occupied_units",
    "B25003_002E": "owner_occupied",
    "B25003_003E": "renter_occupied",
    "B25040_001E": "heat_total_occupied",
    "B25040_004E": "heat_electricity",
    "B19013_001E": "median_income",
    "B01001_001E": "total_pop_display",
    **{f"B25034_{i:03d}E": f"yearbuilt_{i:03d}" for i in range(1, 12)},
}


def share_electric_heat(electric: pd.Series, occupied: pd.Series) -> pd.Series:
    """Electric-heat share = units heated by electricity / occupied units; NaN where occupied is 0 or missing."""
    return electric / occupied.where(occupied > 0)


def clean_acs(raw: pd.DataFrame) -> pd.DataFrame:
    """Rename columns, convert to numbers, turn Census negative sentinels into NaN, add GEOID and share_electric_heat."""
    df = raw.rename(columns=VARS).copy()
    for col in VARS.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] < 0, col] = np.nan
    df["GEOID"] = df["state"] + df["county"] + df["tract"]
    df["share_electric_heat"] = share_electric_heat(df["heat_electricity"], df["occupied_units"])
    return df.drop(columns=["state", "county", "tract"])


def fetch_acs(year: int, state_fips: str, key: str) -> pd.DataFrame:
    """Fetch all VARS for every tract in the state (one API call)."""
    params = {"get": ",".join(VARS), "for": "tract:*", "in": f"state:{state_fips} county:*", "key": key}
    resp = requests.get(ACS_URL.format(year=year), params=params, timeout=120)
    resp.raise_for_status()
    rows = resp.json()
    return pd.DataFrame(rows[1:], columns=rows[0])


def build_acs(cfg: dict | None = None) -> pd.DataFrame:
    """Fetch (cached in data/raw/acs/), clean, and save to data/raw/processed/acs_tract.csv."""
    cfg = cfg or load_config()
    load_env()
    year = cfg["census"]["acs_year"]
    key = os.environ.get(cfg["census"]["api_key_env"])
    if not key:
        raise RuntimeError(f"{cfg['census']['api_key_env']} is not set; add it to .env")
    cache = RAW / "acs" / f"acs5_{year}_state{cfg['district']['state_fips']}_tracts.csv"
    if cache.exists():
        raw = pd.read_csv(cache, dtype=str)
    else:
        raw = fetch_acs(year, cfg["district"]["state_fips"], key)
        cache.parent.mkdir(parents=True, exist_ok=True)
        raw.to_csv(cache, index=False)  # raw response only; the API key is never written
    df = clean_acs(raw)
    for c in ("occupied_units", "median_income", "share_electric_heat"):
        warn_missing(f"ACS {c} (statewide)", int(df[c].isna().sum()), len(df))
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED / "acs_tract.csv", index=False)
    return df
