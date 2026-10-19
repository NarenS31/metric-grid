"""Winter demand history for the demand model: EIA-930 hourly demand (DUK, CPLE) + IEM hourly temperature (KCLT, KRDU).

Source rules
  * EIA API v2 region-data hourly starts at 2019-01-01, so Dec 2017 - Dec 2018 come from EIA's own bulk CSV files (the same
    EIA-930 data; the spec's documented fallback). Where both exist (Jan-Feb 2019) they are compared in `compare_api_bulk`.
  * Time: EIA labels each hour by the UTC time at its END (checked against the bulk column "UTC Time at End of Hour").
    All hours here are labelled that way; `local_end` is the same instant in America/New_York.
  * Temperature: IEM archive of NOAA ASOS observations (routine reports near HH:52). Each report is assigned to the nearest
    hour (HH:52 -> HH+1:00, matching the hour-ending label). Gaps up to 3 hours are linearly interpolated; longer gaps stay
    missing (NaN). Nothing is zero-filled.
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from metric_grid.config import load_config, load_env
from metric_grid.ingest.common import PROCESSED, RAW, download

API_FIRST = pd.Timestamp("2019-01-01 00:00", tz="UTC")
BULK_BASE = "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/"
BULK_FILES = ["EIA930_BALANCE_2017_Jul_Dec", "EIA930_BALANCE_2018_Jan_Jun", "EIA930_BALANCE_2018_Jul_Dec", "EIA930_BALANCE_2019_Jan_Jun"]
IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
BA_STATION = {"DUK": "CLT", "CPLE": "RDU"}   # KCLT for Duke Energy Carolinas, KRDU (Raleigh-Durham) for Progress East
WINTERS = list(range(2018, 2026))            # winter Y = Dec (Y-1), Jan Y, Feb Y
HIST = RAW / "eia" / "hist"


def winter_of(local_hour_start: pd.Series) -> pd.Series:
    """Winter label (the January year) for the local START of each hour, if it falls in Dec/Jan/Feb; NaN otherwise.
    (Hours are labelled by their end, so callers pass `local_end - 1 hour`.)"""
    m, y = local_hour_start.dt.month, local_hour_start.dt.year
    return np.where(m == 12, y + 1, np.where(m <= 2, y, np.nan))


def api_windows() -> list[tuple[str, str, int]]:
    """(start, end, winter) UTC windows the API can serve: Jan-Feb 2019 and every full winter 2020-2025."""
    out = [("2019-01-01T00", "2019-03-01T06", 2019)]
    out += [(f"{w - 1}-12-01T00", f"{w}-03-01T06", w) for w in range(2020, 2026)]
    return out


def _fetch(cfg: dict, key: str, resp: str, start: str, end: str) -> dict:
    params = {"api_key": key, "frequency": "hourly", "data[0]": "value", "length": 5000, "facets[respondent][]": resp,
              "facets[type][]": cfg["eia"]["type"], "start": start, "end": end, "sort[0][column]": "period", "sort[0][direction]": "asc"}
    last = "no attempt"
    for attempt in range(5):  # the gateway is slow and sometimes 504s
        try:
            r = requests.get(cfg["eia"]["api_url"], params=params, timeout=240)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            last = type(exc).__name__
        time.sleep(6 * (attempt + 1))
    raise RuntimeError(f"EIA request {resp} {start}..{end} failed ({last})")  # never include the URL: it holds the key


def fetch_api_history(cfg: dict | None = None) -> pd.DataFrame:
    """All API windows for DUK and CPLE (cached per window under data/raw/eia/hist/). Columns: resp, utc_end, mw."""
    cfg = cfg or load_config()
    load_env()
    key = os.environ.get(cfg["eia"]["api_key_env"], "")
    HIST.mkdir(parents=True, exist_ok=True)
    jobs = [(resp, s, e) for resp in BA_STATION for (s, e, _) in api_windows()]

    def one(job):
        resp, s, e = job
        cache = HIST / f"{resp}_{s}_{e}.json"
        if cache.exists():
            return json.loads(cache.read_text())
        if not key:
            raise RuntimeError("EIA_API_KEY is not set; add it to .env")
        payload = _fetch(cfg, key, resp, s, e)
        cache.write_text(json.dumps(payload))
        return payload

    with ThreadPoolExecutor(3) as ex:
        payloads = list(ex.map(one, jobs))
    rows = []
    for (resp, _, _), p in zip(jobs, payloads):
        for d in p["response"]["data"]:
            rows.append({"resp": resp, "period": d["period"], "mw": d["value"]})
    df = pd.DataFrame(rows)
    df["mw"] = pd.to_numeric(df["mw"], errors="coerce")
    df["utc_end"] = pd.to_datetime(df["period"], format="%Y-%m-%dT%H").dt.tz_localize("UTC")
    return df.drop(columns="period").drop_duplicates(["resp", "utc_end"])


def load_bulk(demand_col: str = "Demand (MW)") -> pd.DataFrame:
    """DUK and CPLE hours from the downloaded bulk CSVs. Columns: resp, utc_end, mw (the chosen demand column:
    'Demand (MW)' raw, 'Demand (MW) (Imputed)' or 'Demand (MW) (Adjusted)')."""
    frames = []
    for name in BULK_FILES:
        path = download(BULK_BASE + name + ".csv", RAW / "eia_bulk" / f"{name}.csv", timeout=900)
        head = pd.read_csv(path, nrows=0).columns
        ba, utc, dem = "Balancing Authority", "UTC Time at End of Hour", demand_col
        for need in (ba, utc, dem):
            if need not in head:
                raise ValueError(f"{name}: column {need!r} not found; columns are {list(head)}")
        df = pd.read_csv(path, usecols=[ba, utc, dem], dtype=str)
        df = df[df[ba].isin(BA_STATION)]
        out = pd.DataFrame({"resp": df[ba], "mw": pd.to_numeric(df[dem].str.replace(",", ""), errors="coerce"),
                            "utc_end": pd.to_datetime(df[utc], format="%m/%d/%Y %I:%M:%S %p", errors="coerce").dt.tz_localize("UTC")})
        frames.append(out)
    return pd.concat(frames).dropna(subset=["utc_end"]).drop_duplicates(["resp", "utc_end"])


def compare_api_bulk(api: pd.DataFrame, bulk: pd.DataFrame) -> dict:
    """Where both sources cover an hour, how close are they? Also tests whether the API label equals the bulk end-of-hour
    (shift 0) or is one hour earlier/later (shift -1/+1), to settle the hour convention."""
    out = {}
    for shift in (-1, 0, 1):
        b = bulk.assign(utc_end=bulk["utc_end"] + pd.Timedelta(hours=shift))
        m = api.merge(b, on=["resp", "utc_end"], suffixes=("_api", "_bulk")).dropna()
        out[shift] = {"n": int(len(m)), "mae_mw": float((m["mw_api"] - m["mw_bulk"]).abs().mean()) if len(m) else None,
                      "share_exact": float((m["mw_api"] == m["mw_bulk"]).mean()) if len(m) else None}
    return out


def fetch_iem(station: str, start: str, end: str) -> pd.DataFrame:
    """Raw ASOS temperature reports (F) in UTC for one station, cached per request."""
    cache = RAW / "noaa" / f"iem_{station}_{start}_{end}.csv"
    if not cache.exists():
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        params = {"station": station, "data": "tmpf", "year1": s.year, "month1": s.month, "day1": s.day, "year2": e.year,
                  "month2": e.month, "day2": e.day, "tz": "Etc/UTC", "format": "onlycomma", "latlon": "no", "missing": "M",
                  "report_type": "3"}
        for attempt in range(4):
            r = requests.get(IEM, params=params, timeout=300)
            if r.status_code == 200 and r.text.startswith("station"):
                break
            time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError(f"IEM request failed for {station} {start}..{end}")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(r.text)
    df = pd.read_csv(cache)
    df = df[df["tmpf"].astype(str) != "M"].copy()
    df["temp_f"] = pd.to_numeric(df["tmpf"])
    df["utc"] = pd.to_datetime(df["valid"]).dt.tz_localize("UTC")
    return df[["utc", "temp_f"]]


def hourly_temperature(raw: pd.DataFrame, max_gap_hours: int = 3) -> pd.DataFrame:
    """Raw reports -> one value per UTC hour label (nearest hour), gaps of <= max_gap_hours interpolated, longer gaps NaN.
    Columns: utc_end, temp_f, interpolated (bool)."""
    r = raw.assign(utc_end=raw["utc"].dt.round("h")).groupby("utc_end", as_index=False)["temp_f"].mean()
    full = pd.date_range(r["utc_end"].min(), r["utc_end"].max(), freq="h", tz="UTC")
    s = r.set_index("utc_end")["temp_f"].reindex(full)
    was_missing = s.isna()
    filled = s.interpolate(limit=max_gap_hours, limit_area="inside")
    # interpolate(limit=n) fills the first n of a longer gap too; blank out any gap longer than the limit completely
    run = (was_missing != was_missing.shift()).cumsum()
    gap_len = was_missing.groupby(run).transform("sum").where(was_missing, 0)
    filled = filled.where(~(was_missing & (gap_len > max_gap_hours)))
    return pd.DataFrame({"utc_end": full, "temp_f": filled.to_numpy(), "interpolated": (was_missing & filled.notna()).to_numpy()})


def build_training(cfg: dict | None = None, bulk_col: str = "Demand (MW)", api: pd.DataFrame | None = None) -> pd.DataFrame:
    """Assemble the winter table (Dec-Feb, winters 2018-2025): demand per BA + its station temperature, hour-ending labels.

    Columns: utc_end, local_end, winter, duk_mw, cple_mw, duk_src, cple_src, kclt_f, krdu_f. Rows with no data at all for an
    hour are absent; per-BA gaps stay NaN."""
    cfg = cfg or load_config()
    api = fetch_api_history(cfg) if api is None else api
    bulk = load_bulk(bulk_col)
    both = api.assign(src="api")
    early = bulk[bulk["utc_end"] < API_FIRST].assign(src="bulk")
    d = pd.concat([both, early])
    wide = d.pivot(index="utc_end", columns="resp", values="mw").rename(columns={"DUK": "duk_mw", "CPLE": "cple_mw"})
    src = d.pivot(index="utc_end", columns="resp", values="src").rename(columns={"DUK": "duk_src", "CPLE": "cple_src"})
    t = {}
    for ba, st in BA_STATION.items():
        parts = [fetch_iem(st, f"{y}-11-30", f"{y + 1}-03-02") for y in range(2017, 2025)]
        t[ba] = hourly_temperature(pd.concat(parts).drop_duplicates("utc")).set_index("utc_end")["temp_f"]
    temps = pd.DataFrame({"kclt_f": t["DUK"], "krdu_f": t["CPLE"]})
    df = wide.join(src).join(temps, how="left").reset_index()
    df["local_end"] = df["utc_end"].dt.tz_convert(cfg["scenario"]["local_tz"])
    df["winter"] = winter_of(df["local_end"] - pd.Timedelta(hours=1))
    df = df[df["winter"].between(WINTERS[0], WINTERS[-1])].copy()
    df["winter"] = df["winter"].astype(int)
    out = df[["utc_end", "local_end", "winter", "duk_mw", "cple_mw", "duk_src", "cple_src", "kclt_f", "krdu_f"]].sort_values("utc_end")
    return out.reset_index(drop=True)


DEMAND_VARIANTS = ["Demand (MW)", "Demand (MW) (Imputed)", "Demand (MW) (Adjusted)"]


def freeze_training(cfg: dict | None = None) -> dict:
    """Pull everything, choose the bulk demand column that matches the API on the Jan-Feb 2019 overlap, write
    data/frozen/demand_training.csv.gz and demand_training_report.json (counts, gaps, source comparison, hour convention)."""
    import json as _json

    from metric_grid.config import ROOT

    cfg = cfg or load_config()
    api = fetch_api_history(cfg)
    overlap = {}
    for col in DEMAND_VARIANTS:
        overlap[col] = compare_api_bulk(api, load_bulk(col))
    best = min(DEMAND_VARIANTS, key=lambda c: (overlap[c][0]["mae_mw"] if overlap[c][0]["mae_mw"] is not None else 1e9))
    df = build_training(cfg, bulk_col=best, api=api)
    out = ROOT / "data" / "frozen"
    out.mkdir(parents=True, exist_ok=True)
    save = df.assign(utc_end=df["utc_end"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")).drop(columns="local_end")
    save.to_csv(out / "demand_training.csv.gz", index=False, float_format="%.1f")
    rep = {"rows": int(len(df)), "winters": sorted(df["winter"].unique().tolist()), "bulk_column_used": best,
           "api_vs_bulk_overlap_by_column": overlap,
           "per_winter": {int(w): {"hours": int(len(g)), "duk_missing": int(g["duk_mw"].isna().sum()), "cple_missing": int(g["cple_mw"].isna().sum()),
                                   "kclt_missing": int(g["kclt_f"].isna().sum()), "krdu_missing": int(g["krdu_f"].isna().sum()),
                                   "sources": sorted(set(g["duk_src"].dropna()) | set(g["cple_src"].dropna()))} for w, g in df.groupby("winter")},
           "temperature_stations": {"DUK": "KCLT (Charlotte)", "CPLE": "KRDU (Raleigh-Durham)"},
           "notes": ["EIA hours are labelled by the UTC time at the END of the hour", "temperature gaps of up to 3 hours interpolated, longer gaps left missing"]}
    (out / "demand_training_report.json").write_text(_json.dumps(rep, indent=1))
    return rep


if __name__ == "__main__":
    r = freeze_training()
    print({k: r[k] for k in ("rows", "winters", "bulk_column_used")})
