"""Phase 0 smoke test: config loads and carries the required district keys."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metric_grid.config import load_config


def test_config_district_keys():
    cfg = load_config()
    assert cfg["district"]["state_fips"] == "37"
    assert cfg["district"]["district"] == "08"
    assert cfg["balancing_authority"]["code"] == "DUK"
    assert "ba_counties" in cfg["balancing_authority"]
