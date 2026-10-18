"""Phase 2.1: EIA-930 hourly demand for the balancing authority (DUK) around Winter Storm Elliott.

EIA region-data 'period' is UTC. We keep both UTC and local-time columns. 'DUK' is Duke Energy Carolinas, a
balancing authority far larger than NC-08, so any NC-08 demand derived from it is a modeled estimate.
"""
import json
import os
import time

import pandas as pd
import requests

from metric_grid.config import load_config, load_env
from metric_grid.ingest.common import PROCESSED, RAW


def fetch_eia(cfg: dict, key: str) -> dict:
    """One EIA API v2 request for the configured respondent/type/window (slow: ~1 min is normal)."""
    params = {
        "api_key": key, "frequency": "hourly", "data[0]": "value", "length": 5000,
        "facets[respondent][]": cfg["balancing_authority"]["code"], "facets[type][]": cfg["eia"]["type"],
        "start": cfg["scenario"]["eia_window_start_utc"][:13], "end": cfg["scenario"]["eia_window_end_utc"][:13],
    }
    last = "no attempt"
    for attempt in range(4):  # the EIA gateway is slow and sometimes 504s
        try:
            resp = requests.get(cfg["eia"]["api_url"], params=params, timeout=240)
            if resp.status_code == 200:
                return resp.json()
            last = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            last = type(exc).__name__
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"EIA request failed after 4 attempts ({last})")  # never include the URL: it holds the key


def parse_eia(payload: dict, tz: str) -> pd.DataFrame:
    """Payload -> DataFrame[period_utc, local_time, demand_mw], sorted, no duplicates, no missing values."""
    rows = payload["response"]["data"]
    df = pd.DataFrame(rows)
    df["demand_mw"] = pd.to_numeric(df["value"], errors="coerce")
    if df["demand_mw"].isna().any():
        raise ValueError("EIA series has missing demand values; refusing to fill them")
    df["period_utc"] = pd.to_datetime(df["period"], format="%Y-%m-%dT%H").dt.tz_localize("UTC")
    df = df.sort_values("period_utc").reset_index(drop=True)
    if df["period_utc"].duplicated().any():
        raise ValueError("duplicate hours in EIA series")
    df["local_time"] = df["period_utc"].dt.tz_convert(tz)
    return df[["period_utc", "local_time", "demand_mw"]]


def build_eia(cfg: dict | None = None) -> pd.DataFrame:
    """Fetch (cached raw JSON, key never stored), parse, save data/raw/processed/eia930_duk.csv."""
    cfg = cfg or load_config()
    load_env()
    cache = RAW / "eia" / "eia930_region_data_DUK_D_2022-12-22_26.json"
    if cache.exists():
        payload = json.loads(cache.read_text())
    else:
        key = os.environ.get(cfg["eia"]["api_key_env"])
        if not key:
            raise RuntimeError(f"{cfg['eia']['api_key_env']} is not set; add it to .env")
        payload = fetch_eia(cfg, key)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload))
    df = parse_eia(payload, cfg["scenario"]["local_tz"])
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED / "eia930_duk.csv", index=False)
    return df


def demand_at(df: pd.DataFrame, local_date: str, local_hhmm: str) -> float:
    """Demand (MW) for the hour starting at the given local date/time."""
    t = pd.Timestamp(f"{local_date} {local_hhmm}", tz=str(df["local_time"].dt.tz))
    hit = df[df["local_time"] == t]
    if len(hit) != 1:
        raise ValueError(f"no unique EIA row at {t}")
    return float(hit["demand_mw"].iloc[0])


def reduction_ratio(df: pd.DataFrame, cfg: dict) -> dict:
    """Default r = regional shed MW (NCUC M-100 Sub 163, ~1,000 MW) / DUK demand at the reference hour.

    Regional numbers only: T_NC08 is computed later from the district-scaled load, never from these MW.
    """
    s = cfg["scenario"]
    d = demand_at(df, s["date"], s["reference_hour_local"])
    return {"duk_demand_mw_0700": d, "shed_mw_regional": s["shed_mw_regional"], "r": s["shed_mw_regional"] / d}
