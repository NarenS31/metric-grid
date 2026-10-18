"""Phase 1.4: LEHD LODES8 Workplace Area Characteristics (WAC), block -> tract.

WAC rows are census blocks; the first 11 digits of w_geocode are the tract GEOID, so no crosswalk is needed.
Columns kept: C000 total jobs, CNS05 manufacturing, CNS07 retail, CNS16 health care. Tract sums over blocks.
"""
import pandas as pd

from metric_grid.config import load_config
from metric_grid.ingest.common import PROCESSED, RAW, download

LODES_URL = "https://lehd.ces.census.gov/data/lodes/LODES8/{st}/wac/{st}_wac_S000_JT00_{year}.csv.gz"
JOB_COLS = {"C000": "jobs_total", "CNS05": "jobs_manufacturing", "CNS07": "jobs_retail", "CNS16": "jobs_health"}


def blocks_to_tracts(wac: pd.DataFrame) -> pd.DataFrame:
    """Sum block-level job counts to tract GEOID (first 11 digits of w_geocode)."""
    df = wac.copy()
    df["GEOID"] = df["w_geocode"].astype(str).str.zfill(15).str[:11]
    return df.groupby("GEOID", as_index=False)[list(JOB_COLS)].sum().rename(columns=JOB_COLS)


def build_lodes(state_abbr: str = "nc", year: int | None = None, cfg: dict | None = None) -> pd.DataFrame:
    """Download WAC, aggregate to tracts, save to data/raw/processed/lodes_tract.csv."""
    cfg = cfg or load_config()
    year = year or cfg["census"]["lodes_year"]
    url = LODES_URL.format(st=state_abbr, year=year)
    path = download(url, RAW / "lodes" / f"{state_abbr}_wac_S000_JT00_{year}.csv.gz")
    wac = pd.read_csv(path, dtype={"w_geocode": str}, usecols=["w_geocode", *JOB_COLS])
    out = blocks_to_tracts(wac)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROCESSED / "lodes_tract.csv", index=False)
    return out
