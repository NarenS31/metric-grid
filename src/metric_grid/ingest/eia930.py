"""Phase 2.1: EIA-930 hourly demand for the balancing authorities that cover the district, around Winter Storm Elliott.

EIA region-data 'period' is UTC; we keep UTC and local-time columns. Each footprint group in config
(`balancing_authorities`) sums one or more EIA-930 respondents (DEP = CPLE + CPLW). These BAs are far larger than
NC-08, so any NC-08 demand derived from them is a modeled estimate.
"""
import json
import os
import time

import pandas as pd
import requests

from metric_grid.config import load_config, load_env
from metric_grid.ingest.common import PROCESSED, RAW


def respondents(cfg: dict) -> list[str]:
    """All EIA-930 respondent codes named by the configured footprint groups (order preserved, no duplicates)."""
    out = []
    for g in cfg["balancing_authorities"]:
        out += [r for r in g["eia930_respondents"] if r not in out]
    return out


def fetch_eia(cfg: dict, key: str, respondent: str) -> dict:
    """One EIA API v2 request for one respondent over the configured window (slow: ~1 min is normal)."""
    params = {
        "api_key": key, "frequency": "hourly", "data[0]": "value", "length": 5000,
        "facets[respondent][]": respondent, "facets[type][]": cfg["eia"]["type"],
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
    raise RuntimeError(f"EIA request for {respondent} failed after 4 attempts ({last})")  # never include the URL: it holds the key


def parse_eia(payload: dict, tz: str) -> pd.DataFrame:
    """Payload -> DataFrame[respondent, period_utc, local_time, demand_mw]; sorted, no duplicates, no missing values."""
    df = pd.DataFrame(payload["response"]["data"])
    if "respondent" not in df:
        df["respondent"] = "?"
    df["demand_mw"] = pd.to_numeric(df["value"], errors="coerce")
    if df["demand_mw"].isna().any():
        raise ValueError("EIA series has missing demand values; refusing to fill them")
    df["period_utc"] = pd.to_datetime(df["period"], format="%Y-%m-%dT%H").dt.tz_localize("UTC")
    df = df.sort_values(["respondent", "period_utc"]).reset_index(drop=True)
    if df.duplicated(["respondent", "period_utc"]).any():
        raise ValueError("duplicate hours in EIA series")
    df["local_time"] = df["period_utc"].dt.tz_convert(tz)
    return df[["respondent", "period_utc", "local_time", "demand_mw"]]


def build_eia(cfg: dict | None = None) -> pd.DataFrame:
    """Fetch each respondent (cached raw JSON, key never stored), parse, save data/raw/processed/eia930_demand.csv."""
    cfg = cfg or load_config()
    load_env()
    frames = []
    for resp in respondents(cfg):
        cache = RAW / "eia" / f"eia930_{resp}_D_2022-12-22_26.json"
        if cache.exists():
            payload = json.loads(cache.read_text())
        else:
            key = os.environ.get(cfg["eia"]["api_key_env"])
            if not key:
                raise RuntimeError(f"{cfg['eia']['api_key_env']} is not set; add it to .env")
            payload = fetch_eia(cfg, key, resp)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(payload))
        frames.append(parse_eia(payload, cfg["scenario"]["local_tz"]))
    df = pd.concat(frames, ignore_index=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED / "eia930_demand.csv", index=False)
    return df


def group_demand(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Hourly demand per footprint group (sum of its respondents). Raises if any respondent is missing an hour."""
    wide = df.pivot(index="period_utc", columns="respondent", values="demand_mw")
    out = {}
    for g in cfg["balancing_authorities"]:
        cols = g["eia930_respondents"]
        missing = [c for c in cols if c not in wide]
        if missing:
            raise ValueError(f"no EIA-930 data for {missing}")
        sub = wide[cols]
        if sub.isna().any().any():
            raise ValueError(f"missing hours for group {g['key']}; refusing to fill")
        out[g["key"]] = sub.sum(axis=1)
    res = pd.DataFrame(out).reset_index()
    res["local_time"] = res["period_utc"].dt.tz_convert(cfg["scenario"]["local_tz"])
    return res


def demand_at(wide: pd.DataFrame, local_date: str, local_hhmm: str, column: str) -> float:
    """Demand (MW) of `column` for the hour ENDING at the given local date/time (EIA labels hours by their end)."""
    t = pd.Timestamp(f"{local_date} {local_hhmm}", tz=str(wide["local_time"].dt.tz))
    hit = wide[wide["local_time"] == t]
    if len(hit) != 1:
        raise ValueError(f"no unique EIA row at {t}")
    return float(hit[column].iloc[0])


def reduction_ratios(wide: pd.DataFrame, cfg: dict) -> dict:
    """Per group: r_g = max firm load shed (FERC-NERC / SC ORS reports) / group demand in the reference hour (the hour ending 07:00, i.e. 06:00-07:00).

    Regional numbers only: T_NC08 is computed later from district-scaled load, never from these MW.
    """
    s = cfg["scenario"]
    out = {}
    for g in cfg["balancing_authorities"]:
        d = demand_at(wide, s["date"], s["reference_hour_local"], g["key"])
        out[g["key"]] = {"demand_mw_0700": d, "shed_mw": g["shed_mw"], "r": g["shed_mw"] / d}
    return out
