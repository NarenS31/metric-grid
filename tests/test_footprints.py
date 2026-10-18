"""Tests for county->group assignment (EIA-861 logic) and district scaling arithmetic."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metric_grid.config import ROOT, load_config
from metric_grid.ingest import footprints as fp
from metric_grid.model import load_allocation as la

PROCESSED = ROOT / "data" / "raw" / "processed"
GROUPS = [
    {"key": "G1", "eia861_utility_numbers": ["1"], "eia861_ba_codes": ["AAA"]},
    {"key": "G2", "eia861_utility_numbers": ["2"], "eia861_ba_codes": ["BBB"]},
]


def _toy():
    terr = pd.DataFrame({"Utility Number": ["1", "1", "2", "3", "9"], "State": ["NC"] * 5,
                         "County": ["Aa", "Bb", "Aa", "Bb", "Bb"]})
    ba = pd.DataFrame({"Utility Number": ["1", "2", "3", "9"], "State": ["NC"] * 4, "BA Code": ["AAA", "BBB", "AAA", "ZZZ"]})
    return terr, ba


def test_norm_county():
    assert fp.norm_county("St. Johns County") == "saintjohns"
    assert fp.norm_county("McDowell") == "mcdowell"


def test_assign_counties_via_utility_and_ba_code_and_shared():
    terr, ba = _toy()
    a = fp.assign_counties(terr, ba, GROUPS)
    got = {(r.county_name, r.group): (r.via, r.shared) for r in a.itertuples()}
    assert got[("Aa", "G1")] == ("utility", True) and got[("Aa", "G2")] == ("utility", True)
    assert got[("Bb", "G1")] == ("ba_code+utility", False)  # co-op 3 has BA code AAA, so it joins G1
    assert ("Bb", "G2") not in got  # utility 9 is in another BA and matches no group


def test_customer_spread_known_answer():
    terr, ba = _toy()
    a = fp.assign_counties(terr, ba, GROUPS)
    customers = {("1", "NC"): 100.0, ("2", "NC"): 100.0, ("3", "NC"): 0.0}
    hu = pd.Series({("NC", "aa"): 10.0, ("NC", "bb"): 30.0})
    s = fp.add_shares(a, terr, customers, hu, "customer_spread")
    aa = s[s.county_name == "Aa"].set_index("group")["share"]
    # G1 spreads 100 customers over Aa(10) and Bb(30): 25 in Aa. G2 serves only Aa: 100. Share G1 = 25/125.
    assert aa["G1"] == pytest.approx(0.2) and aa["G2"] == pytest.approx(0.8)
    assert s.groupby("county_name")["share"].sum().round(9).eq(1).all()


def test_equal_rule_splits_evenly():
    terr, ba = _toy()
    s = fp.add_shares(fp.assign_counties(terr, ba, GROUPS), terr, {}, pd.Series(dtype=float), "equal")
    assert s[s.county_name == "Aa"]["share"].tolist() == [0.5, 0.5]


def test_district_scaling_known_answer():
    wd = pd.Series({"G1": 10.0, "G2": 5.0})
    wg = pd.Series({"G1": 100.0, "G2": 50.0})
    out = la.district_scaling({"G1": 1000.0, "G2": 400.0}, {"G1": 50.0, "G2": 40.0}, wd, wg)
    # D = 1000*10/100 + 400*5/50 = 100 + 40 ; T = 100*0.05 + 40*0.10 = 5 + 4
    assert out["D_NC08_mw"] == pytest.approx(140) and out["T_NC08_mw"] == pytest.approx(9)
    assert out["r_effective"] == pytest.approx(9 / 140)
    assert out["source"] == "modeled district estimate"


def test_override_shared_puts_shared_counties_wholly_in_one_group():
    df = pd.DataFrame({"geoid5": ["1", "1", "2"], "group": ["G1", "G2", "G1"], "share": [0.5, 0.5, 1.0],
                       "shared": [True, True, False]})
    o = la.override_shared(df, "G2")
    assert o[o.geoid5 == "1"]["group"].tolist() == ["G2"] and o[o.geoid5 == "2"]["share"].tolist() == [1.0]


def test_unassigned_district_county_raises():
    t = pd.DataFrame({"GEOID": ["37999000100"], "housing_units": [10.0], "jobs_total": [5.0]})
    c = pd.DataFrame({"geoid5": ["37001"], "group": ["G1"], "share": [1.0]})
    with pytest.raises(ValueError):
        la.district_weights_by_group(t, c, "37", 5.0, 1.0)


@pytest.mark.skipif(not (PROCESSED / "county_groups.csv").exists(), reason="run `make data` first")
def test_saved_county_table_shares_sum_to_one_and_cover_district():
    cfg = load_config()
    c = pd.read_csv(PROCESSED / "county_groups.csv", dtype={"geoid5": str})
    assert c.groupby("geoid5")["share"].sum().round(6).eq(1).all()
    for cty in cfg["district"]["counties"]:
        assert (cfg["district"]["state_fips"] + cty) in set(c["geoid5"])
    assert set(c["group"]) == {"DEC", "DEP"}
