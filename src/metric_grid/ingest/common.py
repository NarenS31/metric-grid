"""Shared helpers for ingest modules: raw-data paths, downloading, loud missing-data warnings."""
import warnings
from pathlib import Path

import requests

from metric_grid.config import ROOT

RAW = ROOT / "data" / "raw"
PROCESSED = RAW / "processed"


def download(url: str, dest: Path, timeout: int = 300) -> Path:
    """Download url to dest (skipped if it already exists). Raises on HTTP errors."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def warn_missing(name: str, n_missing: int, n_total: int) -> None:
    """Visible warning for missing values. We never zero-fill; callers keep the NaN."""
    if n_missing:
        warnings.warn(f"{name}: {n_missing} of {n_total} rows missing (kept as NaN, never zero-filled)")
