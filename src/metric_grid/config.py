"""Load config.yaml: the single place state, district, balancing authority and constants live."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: Path | None = None) -> dict:
    """Return the parsed config.yaml as a dict."""
    with open(path or ROOT / "config.yaml") as f:
        return yaml.safe_load(f)
