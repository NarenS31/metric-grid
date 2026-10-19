"""Phase 4 steps 3-4 tests: sensitivity table, scenarios, presolved grid, plain-language honesty."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metric_grid import frozen
from metric_grid.config import ROOT, load_config
from metric_grid.model import harm, optimizer, scenarios, sensitivity
from metric_grid.model.optimizer import PairResult, PlanResult

CFG = load_config()


@pytest.fixture(scope="module")
def sens():
    return frozen.load_sensitivity()


@pytest.fixture(scope="module")
def rows(sens):
    return pd.DataFrame(sens["rows"])


@pytest.fixture(scope="module")
def consts():
    return frozen.load_constants()


# ---------------- sensitivity ----------------

def test_setting_count_and_kinds(rows):
    assert len(rows) == 20 and rows["solved"].all()
    assert (rows["setting"] == "grid").sum() == 15
    assert set(rows["setting"]) >= {"grid", "band 1%", "band 5%", "Small C&I cost rate", "flat allocation weights", "county-share cap 50%"}


def test_classes_partition_all_zones(sens):
    c = sens["classes"]
    allz = set(c["always"]) | set(c["sometimes"]) | set(c["never"]) | set(c["protected"])
    assert len(allz) == sum(len(v) for v in c.values()) == len(frozen.load_zones())
    z = frozen.load_zones()
    assert set(c["protected"]) == set(z.loc[z["protected"], "zone_id"])


def test_always_zones_are_cut_in_every_setting_and_never_zones_in_none(sens, rows):
    sets = [set(i) for i in rows["weighted_zone_ids"]]
    assert all(set(sens["classes"]["always"]) <= s for s in sets)
    assert not any(set(sens["classes"]["never"]) & s for s in sets)
    assert not any(set(sens["classes"]["protected"]) & s for s in sets)


def test_baseline_unchanged_by_harm_settings(rows):
    nonflat = rows[~rows["flat"] & rows["county_cap"].isna()]
    assert nonflat["baseline_zone_ids"].map(tuple).nunique() == 1  # baseline ignores alpha, weights and cost class


def test_both_plans_inside_their_band_in_every_setting(rows, consts):
    T = consts["T_NC08_mw"]
    for r in rows.itertuples():
        hi = T * (1 + r.band_used_pct / 100)
        assert T - 1e-9 <= r.baseline_mw <= hi + 1e-9 and T - 1e-9 <= r.weighted_mw <= hi + 1e-9


def test_weighted_plan_cuts_more_households_everywhere_and_we_say_so(rows):
    assert (rows["households_change"] > 0).all()  # the honest headline: more households, less vulnerable ones


def test_human_harm_lower_except_economic_only_alpha(rows):
    assert (rows.loc[rows["alpha"] > 0, "human_change_pct"] < 0).all()
    assert (rows.loc[rows["alpha"] == 0, "human_change_pct"] > 0).all()  # alpha=0 ignores human harm by construction
    assert (rows["econ_change_pct"] < 0).all()


def test_band_rows_match_default_and_small_cost_row_differs(rows):
    d = rows[(rows["setting"] == "grid") & (rows["alpha"] == 0.5) & (rows["w_svi"] == 0.7)].iloc[0]
    for name in ("band 1%", "band 5%"):
        assert rows[rows["setting"] == name].iloc[0]["weighted_zone_ids"] == d["weighted_zone_ids"]
    small = rows[rows["setting"] == "Small C&I cost rate"].iloc[0]
    assert small["human_change_pct"] == pytest.approx(d["human_change_pct"]) and small["econ_change_pct"] < d["econ_change_pct"]


def test_cap_row_is_present_and_still_cuts_more_households(rows):
    cap = rows[rows["setting"] == "county-share cap 50%"].iloc[0]
    assert cap["county_cap"] == 0.5 and cap["households_change"] > 0 and cap["human_change_pct"] < 0


def test_flat_loads_sum_to_d_nc08_and_change_the_answer(consts, rows):
    z = frozen.load_zones()
    assert sensitivity.flat_loads(z, consts["D_NC08_mw"]).sum() == pytest.approx(consts["D_NC08_mw"])
    flat = rows[rows["flat"]].iloc[0]
    assert flat["baseline_zone_ids"] != rows[~rows["flat"]].iloc[0]["baseline_zone_ids"]


def test_live_rerun_matches_frozen_default_row(rows, consts):
    z = frozen.load_zones()
    row, _ = sensitivity.run_setting(z, CFG, consts["kw_per_job"], consts["D_NC08_mw"], consts["T_NC08_mw"], "grid", 0.5, 0.7, 2.0)
    f = rows[(rows["setting"] == "grid") & (rows["alpha"] == 0.5) & (rows["w_svi"] == 0.7)].iloc[0]
    assert row["weighted_zone_ids"] == f["weighted_zone_ids"] and row["households_change"] == f["households_change"]


def test_spared_zones_are_baseline_cut_and_never_weighted_cut(sens, rows):
    ever = set().union(*[set(i) for i in rows["weighted_zone_ids"]])
    for rec in sens["spared_every_setting"]:
        assert rec["zone_id"] in sens["default_baseline_ids"] and rec["zone_id"] not in ever
    pos = {r["zone_id"] for r in sens["spared_excluding_alpha0"]}
    assert {r["zone_id"] for r in sens["spared_every_setting"]} <= pos  # dropping alpha=0 can only add zones


# ---------------- scenarios ----------------

def test_scenarios_nested_and_consistent():
    sc = frozen.load_scenarios()
    rows = pd.DataFrame(sc["rows"])
    assert list(rows["target_pct"]) == [10, 15, 20] and rows["solved"].all()
    assert rows["weighted_mw"].is_monotonic_increasing and rows["baseline_mw"].is_monotonic_increasing
    assert (rows["weighted_households"] > rows["baseline_households"]).all()
    for plan in ("baseline", "weighted"):
        assert not set(sc["cut_in_all"][plan]) & set(sc["only_worst"][plan])
    assert sc["worst_pct"] == 20


def test_scenarios_live_matches_frozen(consts):
    z = frozen.load_zones()
    sc = scenarios.run_scenarios(z, CFG, consts["kw_per_job"], consts["D_NC08_mw"])
    froz = frozen.load_scenarios()
    assert sc["cut_in_all"] == froz["cut_in_all"] and sc["only_worst"] == froz["only_worst"]


# ---------------- plain language ----------------

def _pair(bh, wh, bhh, whh, be, we):
    mk = lambda n, hh, h, e: PlanResult(n, [1], 90.0, 0.0, 1, hh, 0.0, 0.0, h, e)
    return PairResult(90.0, 90.0, 92.0, 2.0, False, 0.5, mk("b", bhh, bh, be), mk("w", whh, wh, we), 0.1)


def test_plain_summary_says_more_households_when_weighted_cuts_more():
    s = scenarios.plain_summary(_pair(100, 25, 1000, 1200, 500, 300))
    assert "200 MORE households" in s and "75% fewer vulnerability-weighted households" in s and "2013 dollars" in s


def test_plain_summary_says_fewer_when_it_is_fewer_and_never_hides_direction():
    s = scenarios.plain_summary(_pair(100, 25, 1000, 900, 500, 300))
    assert "100 fewer households" in s and "MORE" not in s
    assert "same number" in scenarios.plain_summary(_pair(100, 25, 1000, 1000, 500, 300))


def test_real_default_summary_states_the_more_households_fact(consts):
    rec = [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0.5][0]
    assert "2,513 MORE households" in rec["summary"] and "2013 dollars" in rec["summary"]


# ---------------- presolved grid and figures ----------------

def test_presolved_grid_complete_and_matches_live_solve(consts):
    g = frozen.load_presolved()
    assert len(g) == 20 and {r["target_key"] for r in g} == {"elliott", "10", "15", "20"}
    assert sorted({r["alpha"] for r in g}) == [0, 0.25, 0.5, 0.75, 1] and all(r["solved"] for r in g)
    for r in g:
        for plan in ("baseline", "weighted"):
            assert r["band_lo_mw"] - 1e-9 <= r[plan]["mw_shed"] <= r["band_hi_mw"] + 1e-9
    z = frozen.load_zones()
    live = optimizer.solve(harm.compute_harm(z, CFG, consts["kw_per_job"]), consts["T_NC08_mw"], 0.5)
    rec = [r for r in g if r["target_key"] == "elliott" and r["alpha"] == 0.5][0]
    assert rec["weighted"]["zone_ids"] == live.weighted.zone_ids and rec["baseline"]["zone_ids"] == live.baseline.zone_ids


def test_alpha_sweep_rows_and_figure_exist():
    sw = pd.DataFrame(frozen.load_alpha_sweep())
    assert list(sw["alpha"]) == [0, 0.25, 0.5, 0.75, 1]
    assert sw["human_change_pct"].iloc[-1] < sw["human_change_pct"].iloc[0]
    assert (sw["households_change"] > 0).all()
    assert (ROOT / "docs" / "figures" / "alpha_tradeoff.png").stat().st_size > 10_000


# ---------------- priority list ("where to plan first") ----------------

def test_priority_list_definition(sens, rows):
    pl = pd.DataFrame(sens["priority_list"])
    assert set(pl["zone_id"]) == {8, 23, 10, 32, 142, 12}
    pos = rows[rows["alpha"] > 0]
    ever_pos = set().union(*[set(i) for i in pos["weighted_zone_ids"]])
    zero = rows[rows["alpha"] == 0]
    ever_zero = set().union(*[set(i) for i in zero["weighted_zone_ids"]])
    for r in pl.itertuples():
        assert r.zone_id in sens["default_baseline_ids"] and r.zone_id not in ever_pos
        assert r.cut_at_alpha0 == (r.zone_id in ever_zero)
    assert list(pl["RPL_THEMES"]) == sorted(pl["RPL_THEMES"], reverse=True)
    assert {"COUNTY", "share_electric_heat", "occupied_units"} <= set(pl.columns)
    assert set(pl.loc[pl["cut_at_alpha0"], "zone_id"]) == {8, 10}


def test_priority_list_live_matches_frozen(sens, consts):
    z = frozen.load_zones()
    res = sensitivity.full_sensitivity(z, CFG, consts["kw_per_job"], consts["D_NC08_mw"], consts["T_NC08_mw"])
    live = sensitivity.priority_list(z, res)
    assert list(live["zone_id"]) == [r["zone_id"] for r in sens["priority_list"]]
