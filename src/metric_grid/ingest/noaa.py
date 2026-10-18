"""Phase 2.4: KCLT (Charlotte airport) hourly temperature, display only.

Primary source NOAA NCEI Access Data Service returned HTTP 503 on 2026-10-18 (two tries), so the fallback is
the Iowa Environmental Mesonet (IEM) archive of the same ASOS station. Not used in any calculation.
"""
import pandas as pd

from metric_grid.config import load_config
from metric_grid.ingest.common import PROCESSED, RAW, download

IEM_URL = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=CLT&data=tmpf"
           "&year1=2022&month1=12&day1=23&year2=2022&month2=12&day2=27&tz=Etc/UTC&format=onlycomma"
           "&latlon=no&missing=M&report_type=3")


def parse_iem(df: pd.DataFrame, tz: str, first_day: str, last_day: str) -> pd.DataFrame:
    """Keep rows with a real temperature (missing 'M' rows dropped, not filled) in the local-date window."""
    df = df[df["tmpf"].astype(str) != "M"].copy()
    df["temp_f"] = pd.to_numeric(df["tmpf"])
    df["time_utc"] = pd.to_datetime(df["valid"]).dt.tz_localize("UTC")
    df["local_time"] = df["time_utc"].dt.tz_convert(tz)
    d = df["local_time"].dt.strftime("%Y-%m-%d")
    return df[(d >= first_day) & (d <= last_day)][["time_utc", "local_time", "temp_f"]].reset_index(drop=True)


def build_noaa(cfg: dict | None = None) -> pd.DataFrame:
    """Download (cached), parse, save data/raw/processed/kclt_temp.csv."""
    cfg = cfg or load_config()
    path = download(IEM_URL, RAW / "noaa" / "kclt_iem_2022-12-23_27.csv")
    out = parse_iem(pd.read_csv(path), cfg["scenario"]["local_tz"], "2022-12-23", "2022-12-25")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROCESSED / "kclt_temp.csv", index=False)
    return out
