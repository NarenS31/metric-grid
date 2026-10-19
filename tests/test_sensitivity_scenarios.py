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


def test_typical_load_only_plan_depends_on_harm_weights_but_not_on_alpha(rows):
    grid = rows[rows["setting"] == "grid"]
    for w, g in grid.groupby("w_svi"):  # same weights -> same plan set metrics -> the same typical plan for every alpha
        assert g["baseline_zone_ids"].map(tuple).nunique() == 1 and g["typical_index"].nunique() == 1


def test_both_plans_inside_their_band_in_every_setting(rows, consts):
    T = consts["T_NC08_mw"]
    for r in rows.itertuples():
        hi = T * (1 + r.band_used_pct / 100)
        assert T - 1e-9 <= r.baseline_mw <= hi + 1e-9 and T - 1e-9 <= r.weighted_mw <= hi + 1e-9


def test_weighted_plan_cuts_more_households_than_the_typical_plan_and_we_say_so(rows):
    """The honest headline: more households, less vulnerable ones. Counted live on the page; here it holds in every setting."""
    assert (rows["households_change"] > 0).all()
    d = rows[(rows["setting"] == "grid") & (rows["alpha"] == 0.5) & (rows["w_svi"] == 0.7)].iloc[0]
    assert d["households_change"] > 2000 and d["more_households_than"] == d["n_plans"]  # more than every equivalent load-only plan


def test_human_harm_lower_except_economic_only_alpha(rows):
    assert (rows.loc[rows["alpha"] > 0, "human_change_pct"] < 0).all()
    assert (rows.loc[rows["alpha"] == 0, "human_change_pct"] > 0).all()  # alpha=0 ignores human harm by construction
    assert (rows.loc[rows["alpha"] <= 0.5, "econ_change_pct"] < 0).all()  # cost is lower whenever cost carries weight
    assert (rows.loc[rows["alpha"] == 1, "econ_change_pct"] > 0).all()   # at alpha 1 cost is ignored and comes out about 5% higher


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
    plans = frozen.load_loadonly()["sets"]["elliott|free"]["plans"]
    row, _ = sensitivity.run_setting(z, CFG, consts["kw_per_job"], consts["D_NC08_mw"], consts["T_NC08_mw"], "grid", 0.5, 0.7, 2.0, plans)
    f = rows[(rows["setting"] == "grid") & (rows["alpha"] == 0.5) & (rows["w_svi"] == 0.7)].iloc[0]
    assert row["weighted_zone_ids"] == f["weighted_zone_ids"] and row["households_change"] == f["households_change"]


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
    sc = scenarios.run_scenarios(z, CFG, consts["kw_per_job"], consts["D_NC08_mw"], frozen.load_loadonly()["sets"])
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
    more = rec["weighted"]["households"] - rec["baseline"]["households"]
    assert more > 0 and f"{more:,.0f} MORE households" in rec["summary"] and "2013 dollars" in rec["summary"]


# ---------------- presolved grid and figures ----------------

def test_presolved_grid_complete_and_matches_live_solve(consts):
    g = frozen.load_presolved()
    assert len(g) == 40 and {r["cap"] for r in g} == {False, True}
    off = [r for r in g if not r["cap"]]
    assert len(off) == 20 and {r["target_key"] for r in off} == {"elliott", "10", "15", "20"}
    assert sorted({r["alpha"] for r in off}) == [0, 0.25, 0.5, 0.75, 1] and all(r["solved"] for r in g)
    for r in g:
        for plan in ("baseline", "weighted"):
            assert r["band_lo_mw"] - 1e-9 <= r[plan]["mw_shed"] <= r["band_hi_mw"] + 1e-9
    z = frozen.load_zones()
    st = frozen.load_loadonly()["sets"]["elliott|free"]
    typ = st["plans"][st["typical_index"]]
    live = optimizer.solve(harm.compute_harm(z, CFG, consts["kw_per_job"]), consts["T_NC08_mw"], 0.5, baseline_ids=typ)
    rec = [r for r in off if r["target_key"] == "elliott" and r["alpha"] == 0.5][0]
    assert rec["weighted"]["zone_ids"] == live.weighted.zone_ids and rec["baseline"]["zone_ids"] == typ


def test_presolved_cap_records_respect_the_county_cap():
    zh = harm.compute_harm(frozen.load_zones(), CFG, frozen.load_constants()["kw_per_job"]).set_index("zone_id")
    for rec in [r for r in frozen.load_presolved() if r["cap"] and r["alpha"] == 0.5]:
        for plan in ("baseline", "weighted"):
            t = zh.loc[rec[plan]["zone_ids"]]
            by_county = t.groupby("COUNTY")["L_mw"].sum()
            assert by_county.max() <= 0.5 * by_county.sum() + 1e-6


def test_alpha_sweep_rows_and_figure_exist():
    sw = pd.DataFrame(frozen.load_alpha_sweep())
    assert list(sw["alpha"]) == [0, 0.25, 0.5, 0.75, 1]
    assert sw["human_change_pct"].iloc[-1] < sw["human_change_pct"].iloc[0]
    assert (sw["households_change"] > 0).all()
    assert (ROOT / "docs" / "figures" / "alpha_tradeoff.png").stat().st_size > 10_000


# ---------------- priority list ("Vulnerable zones most often cut when only megawatts count") ----------------

def test_priority_list_definition(sens, rows):
    pl = pd.DataFrame(sens["priority_list"])
    p = CFG["priority_list"]
    assert p == {"svi_min": 0.75, "electric_heat_min": 0.5, "max_rows": 10} and len(pl) == p["max_rows"]
    z = frozen.load_zones().set_index("zone_id")
    plans = frozen.load_loadonly()["sets"]["elliott|free"]["plans"]
    counts = {i: sum(i in pl_ for pl_ in plans) for i in z.index}
    for r in pl.itertuples():
        zone = z.loc[r.zone_id]
        assert not zone["protected"] and (zone["RPL_THEMES"] >= p["svi_min"] or zone["share_electric_heat"] >= p["electric_heat_min"])
        assert r.loadonly_cut_count == counts[r.zone_id] and r.loadonly_cut_share == pytest.approx(counts[r.zone_id] / 200)
    assert list(pl["loadonly_cut_count"]) == sorted(pl["loadonly_cut_count"], reverse=True)  # ranked by frequency
    # nothing qualifying was left out: every other qualifying zone is cut no more often than the last listed one
    qual = z[(~z["protected"]) & ((z["RPL_THEMES"] >= p["svi_min"]) | (z["share_electric_heat"] >= p["electric_heat_min"]))]
    others = qual.drop(index=list(pl["zone_id"]))
    assert max(counts[i] for i in others.index) <= pl["loadonly_cut_count"].min()


def test_priority_list_vulnerability_aware_flags_match_the_runs(sens, rows):
    pl = pd.DataFrame(sens["priority_list"])
    d0 = rows[(rows["setting"] == "grid") & (rows["alpha"] == 0.5) & (rows["w_svi"] == 0.7)].iloc[0]
    for r in pl.itertuples():
        assert r.vuln_aware_cuts == (r.zone_id in d0["weighted_zone_ids"])
        assert r.vuln_aware_cut_settings == sum(r.zone_id in ids for ids in rows["weighted_zone_ids"]) and r.n_settings == len(rows)


def test_priority_list_excludes_zones_without_svi_data_and_protected_zones():
    z = frozen.load_zones()
    pl = pd.DataFrame(frozen.load_sensitivity()["priority_list"])
    assert not set(pl["zone_id"]) & set(z.loc[z["protected"], "zone_id"]) and 9 not in set(pl["zone_id"])  # zone 9: no SVI data


def test_priority_list_live_matches_frozen(sens, consts):
    z = frozen.load_zones()
    res = sensitivity.full_sensitivity(z, CFG, consts["kw_per_job"], consts["D_NC08_mw"], consts["T_NC08_mw"], frozen.load_loadonly()["sets"])
    live = sensitivity.priority_list(z, res, CFG)
    assert list(live["zone_id"]) == [r["zone_id"] for r in sens["priority_list"]]
    assert list(live["loadonly_cut_count"]) == [r["loadonly_cut_count"] for r in sens["priority_list"]]
