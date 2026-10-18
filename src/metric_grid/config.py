"""Load config.yaml: the single place state, district, balancing authority and constants live."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: Path | None = None) -> dict:
    """Return the parsed config.yaml as a dict."""
    with open(path or ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def load_env(path: Path | None = None) -> None:
    """Load KEY=value lines from .env into os.environ (existing variables win). No extra dependency."""
    import os

    p = path or ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
