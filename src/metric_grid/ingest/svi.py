"""Phase 1.3: CDC/ATSDR Social Vulnerability Index 2022, NC tract CSV.

Keeps RPL_THEMES and the four theme percentiles. The CDC uses -999 for "no data"; we convert it to NaN,
warn, and never zero-fill.
"""
import numpy as np
import pandas as pd

from metric_grid.config import load_config
from metric_grid.ingest.common import PROCESSED, RAW, download, warn_missing

SVI_URL = "https://svi.cdc.gov/Documents/Data/2022/csv/states/NorthCarolina.csv"
SVI_COLS = ["RPL_THEMES", "RPL_THEME1", "RPL_THEME2", "RPL_THEME3", "RPL_THEME4"]


def clean_svi(raw: pd.DataFrame, missing_value: float) -> pd.DataFrame:
    """Return GEOID + SVI percentile columns with the missing sentinel turned into NaN."""
    df = raw.copy()
    df["GEOID"] = df["FIPS"].astype(str).str.zfill(11)
    out = df[["GEOID", "COUNTY"] + SVI_COLS].copy()
    for c in SVI_COLS:
        out[c] = pd.to_numeric(out[c], errors="coerce").replace(missing_value, np.nan)
    return out


def build_svi(cfg: dict | None = None) -> pd.DataFrame:
    """Download, clean and save SVI (all NC tracts) to data/raw/processed/svi.csv."""
    cfg = cfg or load_config()
    path = download(SVI_URL, RAW / "svi" / "NorthCarolina.csv")
    svi = clean_svi(pd.read_csv(path, dtype={"FIPS": str}, encoding="utf-8-sig"), cfg["census"]["svi_missing_value"])
    warn_missing("SVI RPL_THEMES (statewide)", int(svi["RPL_THEMES"].isna().sum()), len(svi))
    PROCESSED.mkdir(parents=True, exist_ok=True)
    svi.to_csv(PROCESSED / "svi.csv", index=False)
    return svi
