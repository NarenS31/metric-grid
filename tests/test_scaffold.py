"""Phase 0 smoke test: config loads and carries the required district keys."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metric_grid.config import load_config


def test_config_district_keys():
    cfg = load_config()
    assert cfg["district"]["state_fips"] == "37"
    assert cfg["district"]["district"] == "08"
    keys = [g["key"] for g in cfg["balancing_authorities"]]
    assert keys == ["DEC", "DEP"]
    assert cfg["balancing_authorities"][1]["eia930_respondents"] == ["CPLE", "CPLW"]
