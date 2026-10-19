"""Phase 2.3: NREL ResStock / ComStock load profiles for the coldest week of the AMY2018 weather year.

Source files are huge, time-ordered CSVs (15-minute rows, timestamps are period-ending, EST). We use HTTP Range
requests and a byte-offset bisect to fetch only the cold week, then average the reference hour (06:00-06:59, the hour ending 07:00) over its days.

Outputs (kW, average over the reference hour 06:00-07:00 of the cold week):
  * residential kW per housing unit (ResStock NC state aggregate: total kWh / units_represented)
  * commercial kW per county (ComStock county aggregate: sum over building types)
ResStock has no county aggregates in any release, so the residential per-unit value is statewide NC (documented).
"""
import csv
import io
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from metric_grid.config import load_config
from metric_grid.ingest.common import PROCESSED, RAW

TOTAL_COL = "out.electricity.total.energy_consumption.kwh"
CHUNK = 20000
ROWS_PER_YEAR = 365 * 96  # 15-minute rows in a full year (rows are near-constant width)


def list_keys(base: str, prefix: str) -> list[str]:
    """List S3 object keys under prefix (anonymous ListObjectsV2, handles pagination)."""
    keys, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        r = requests.get(base + "/", params=params, timeout=60)
        r.raise_for_status()
        root = ET.fromstring(re.sub(r' xmlns="[^"]+"', "", r.text, count=1))
        keys += [c.findtext("Key") for c in root.findall("Contents")]
        if root.findtext("IsTruncated") != "true":
            return keys
        token = root.findtext("NextContinuationToken")


def _get_range(url: str, start: int, end: int) -> str:
    r = requests.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=60)
    r.raise_for_status()
    return r.text


def _first_full_line(text: str, from_start: bool) -> tuple[int, str]:
    """(offset of first complete line within text, that line). If text begins mid-line, skip to the next newline."""
    off = 0 if from_start else text.index("\n") + 1
    return off, text[off:text.index("\n", off)]


def fetch_window(url: str, size: int, t0: pd.Timestamp, t1: pd.Timestamp) -> pd.DataFrame:
    """Rows with t0 <= timestamp <= t1 from a time-ordered CSV via byte-offset bisect (naive timestamps)."""
    head = _get_range(url, 0, CHUNK)
    cols = next(csv.reader([head[:head.index("\n")]]))
    ti = cols.index("timestamp")
    hdr_end = head.index("\n") + 1

    def ts_after(offset: int) -> pd.Timestamp:
        txt = _get_range(url, offset, min(offset + 12000, size - 1))
        _, line = _first_full_line(txt, from_start=False)
        return pd.Timestamp(next(csv.reader([line]))[ti])

    lo, hi = hdr_end, size - 12000
    while hi - lo > 8192:
        mid = (lo + hi) // 2
        if ts_after(mid) < t0:
            lo = mid
        else:
            hi = mid
    nbytes = int(((t1 - t0) / pd.Timedelta(minutes=15) + 4) * size / ROWS_PER_YEAR * 1.5) + 30000
    txt = _get_range(url, lo, min(lo + nbytes, size - 1))
    # txt starts at byte lo: at hdr_end that is a clean line start, otherwise it is mid-line (drop the partial line)
    txt = txt[:txt.rindex("\n")] if lo == hdr_end else txt[txt.index("\n") + 1: txt.rindex("\n")]
    df = pd.read_csv(io.StringIO(txt), header=None, names=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df[(df["timestamp"] >= t0) & (df["timestamp"] <= t1)].reset_index(drop=True)


def cold_week_bounds(cfg: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Period-ending timestamps covering the cold week: first 00:15 to last day's next midnight 00:00."""
    n = cfg["nrel"]
    start = pd.Timestamp(n["cold_week_start"])
    return start + pd.Timedelta(minutes=15), start + pd.Timedelta(days=n["cold_week_days"])


def reference_hour_mean(df: pd.DataFrame, col: str, hour: int) -> float:
    """Mean over days of the sum of the four 15-min rows in the hour [hour:00, hour+1:00).

    Period-ending stamps hour:15, hour:30, hour:45, hour+1:00 cover that hour. Sum of kWh over an hour = avg kW.
    Raises unless exactly 4 rows exist for every day (no silent gaps).
    """
    ts = df["timestamp"] - pd.Timedelta(minutes=15)  # convert to period-start
    sel = df[ts.dt.hour == hour].copy()
    sel["day"] = (sel["timestamp"] - pd.Timedelta(minutes=15)).dt.date
    counts = sel.groupby("day").size()
    if (counts != 4).any():
        raise ValueError(f"incomplete hour data: {counts.to_dict()}")
    return float(sel.groupby("day")[col].sum().mean())


def _fetch_file(cfg: dict, key: str) -> pd.DataFrame:
    """Cold-week slice for one source file, cached under data/raw/nrel/slices/."""
    base = cfg["nrel"]["s3_base"]
    cache = RAW / "nrel" / "slices" / (key.split("/")[-1])
    if cache.exists():
        df = pd.read_csv(cache)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    url = f"{base}/{key}"
    size = int(requests.head(url, timeout=60).headers["Content-Length"])
    t0, t1 = cold_week_bounds(cfg)
    df = fetch_window(url, size, t0, t1)
    expected = (cfg["nrel"]["cold_week_days"]) * 96
    if len(df) != expected:
        raise ValueError(f"{key}: got {len(df)} rows for the cold week, expected {expected}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


def residential_kw_per_unit(cfg: dict) -> dict:
    """ResStock NC (upgrade 0, all building types): kW per housing unit at the reference hour."""
    n = cfg["nrel"]
    prefix = f"{n['root']}/{n['resstock_release']}/timeseries_aggregates/by_state/upgrade=0/state=NC/"
    keys = [k for k in list_keys(n["s3_base"], prefix) if k.endswith(".csv")]
    with ThreadPoolExecutor(5) as ex:
        dfs = list(ex.map(lambda k: _fetch_file(cfg, k), keys))
    kw = sum(reference_hour_mean(d, TOTAL_COL, n["reference_hour_local"]) for d in dfs)
    units = sum(float(d["units_represented"].iloc[0]) for d in dfs)
    return {"kw_total_nc": kw, "units_represented_nc": units, "kw_per_unit": kw / units, "n_files": len(keys)}


def commercial_kw_by_county(cfg: dict, county_fips: list[str]) -> pd.DataFrame:
    """ComStock (upgrade 0): kW at the reference hour for each county (3-digit FIPS under state_fips)."""
    n, st = cfg["nrel"], cfg["district"]["state_fips"]
    jobs = []
    for c in county_fips:
        gid = f"G{st}0{c}0"
        prefix = f"{n['root']}/{n['comstock_release']}/timeseries_aggregates/by_county/upgrade=0/county={gid}/"
        for k in list_keys(n["s3_base"], prefix):
            if k.endswith(".csv"):
                jobs.append((c, k))
    with ThreadPoolExecutor(12) as ex:
        dfs = list(ex.map(lambda j: _fetch_file(cfg, j[1]), jobs))
    rows = {}
    for (c, _), d in zip(jobs, dfs):
        rows[c] = rows.get(c, 0.0) + reference_hour_mean(d, TOTAL_COL, n["reference_hour_local"])
    return pd.DataFrame({"county_fips": list(rows), "comstock_kw": list(rows.values()),
                         "n_building_type_files": [sum(1 for j in jobs if j[0] == c) for c in rows]})


def commercial_kw_state(cfg: dict) -> float:
    """ComStock statewide (upgrade 0, all building types): kW at the reference hour for the whole state."""
    n, st = cfg["nrel"], cfg["district"]["state_fips"]
    prefix = f"{n['root']}/{n['comstock_release']}/timeseries_aggregates/by_state/upgrade=0/state=NC/"
    keys = [k for k in list_keys(n["s3_base"], prefix) if k.endswith(".csv")]
    with ThreadPoolExecutor(7) as ex:
        dfs = list(ex.map(lambda k: _fetch_file(cfg, k), keys))
    return sum(reference_hour_mean(d, TOTAL_COL, n["reference_hour_local"]) for d in dfs)


def build_loads(cfg: dict | None = None) -> tuple[dict, pd.DataFrame]:
    """Residential per-unit, commercial statewide and commercial per-county loads; saved to processed/."""
    cfg = cfg or load_config()
    res = residential_kw_per_unit(cfg)
    res["comstock_kw_nc"] = commercial_kw_state(cfg)
    com = commercial_kw_by_county(cfg, cfg["district"]["counties"])
    PROCESSED.mkdir(parents=True, exist_ok=True)
    com.to_csv(PROCESSED / "comstock_county_kw.csv", index=False)
    pd.Series(res).to_json(PROCESSED / "resstock_nc_per_unit.json")
    return res, com
