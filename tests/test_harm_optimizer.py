"""Phase 4 steps 1-2 tests: harm model and the two-plan banded optimizer."""
import itertools
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metric_grid import frozen
from metric_grid.config import load_config
from metric_grid.model import harm, optimizer, sensitivity
from metric_grid.model.harm import MissingDataError, MissingDataWarning
from metric_grid.model.optimizer import Infeasible

CFG = load_config()


@pytest.fixture(scope="module")
def real():
    z, c = frozen.load_zones(), frozen.load_constants()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MissingDataWarning)
        zh = harm.compute_harm(z, CFG, c["kw_per_job"])
    return zh, c


def toy(rows):
    """rows: (zone_id, L, protected, Hhat_human, Hhat_econ). Other columns are filler consistent with those."""
    df = pd.DataFrame(rows, columns=["zone_id", "L_mw", "protected", "Hhat_human", "Hhat_econ"])
    df["H_human"], df["H_econ"] = df["Hhat_human"] * 100, df["Hhat_econ"] * 1000
    df["N_households"], df["heat_electricity"], df["jobs_total"] = 10.0, 5.0, 2.0
    return df


# ---------------- harm ----------------

def test_hand_recomputation_of_one_zone_from_raw_inputs(real):
    zh, c = real
    row = zh[(zh["N_households"] > 0)].iloc[10]
    n, svi, eh, jobs = row["occupied_units"], row["RPL_THEMES"], row["share_electric_heat"], row["jobs_total"]
    h_human = n * (0.7 * svi + 0.3 * eh)
    h_econ = n * 5.1 * 1 + jobs * (21.8 * c["kw_per_job"]) * 1
    assert row["H_human"] == pytest.approx(h_human) and row["H_econ"] == pytest.approx(h_econ)
    assert row["Hhat_human"] == pytest.approx(h_human / zh["H_human"].max())
    assert row["Hhat_econ"] == pytest.approx(h_econ / zh["H_econ"].max())


def test_alpha_extremes_reproduce_components(real):
    zh, _ = real
    assert harm.blend(zh, 1.0).equals(zh["Hhat_human"]) and harm.blend(zh, 0.0).equals(zh["Hhat_econ"])
    mid = harm.blend(zh, 0.5)
    assert mid.iloc[3] == pytest.approx(0.5 * zh["Hhat_human"].iloc[3] + 0.5 * zh["Hhat_econ"].iloc[3])


def test_normalization_max_is_one_and_units_separate(real):
    zh, _ = real
    assert zh["Hhat_human"].max() == pytest.approx(1) and zh["Hhat_econ"].max() == pytest.approx(1)
    assert {"H_human", "H_econ"} <= set(zh.columns)


def test_zone9_zero_households_gets_zero_harm_with_visible_warning():
    z = frozen.load_zones()
    with pytest.warns(MissingDataWarning, match="0 occupied households"):
        zh = harm.compute_harm(z, CFG, frozen.load_constants()["kw_per_job"])
    nine = zh[zh["GEOID"] == "37007980000"].iloc[0]
    assert nine["N_households"] == 0 and nine["H_human"] == 0 and nine["H_econ"] > 0  # jobs still carry economic cost


def _inputs(svi, heat, n=100.0):
    return pd.DataFrame({"zone_id": [1, 2], "occupied_units": [n, 50.0], "RPL_THEMES": [svi, 0.5], "share_electric_heat": [heat, 0.2],
                         "jobs_total": [10, 10], "jobs_manufacturing": [1, 1], "jobs_retail": [1, 1], "jobs_health": [1, 1],
                         "svi_missing": [np.isnan(svi), False]})


def test_missing_svi_with_households_is_nan_excluded_from_normalization_and_warns():
    with pytest.warns(MissingDataWarning, match="no SVI/electric-heat"):
        zh = harm.compute_harm(_inputs(np.nan, 0.3), CFG, 1.0)
    assert np.isnan(zh.loc[0, "H_human"]) and np.isnan(zh.loc[0, "Hhat_human"])  # not zero-filled
    assert zh.loc[1, "Hhat_human"] == pytest.approx(1.0)  # the other zone defines the max


def test_optimizer_refuses_zone_with_unknown_harm():
    with pytest.warns(MissingDataWarning):
        zh = harm.compute_harm(_inputs(np.nan, 0.3), CFG, 1.0)
    zh["L_mw"], zh["protected"], zh["heat_electricity"] = [5.0, 5.0], False, 1.0
    zh["N_households"] = zh["occupied_units"]
    with pytest.raises(MissingDataError):
        optimizer.solve(zh, 4.0, 0.5)


def test_only_one_hour_supported_and_class_switch():
    cfg = load_config(); cfg["harm"]["h_hours"] = 4
    with pytest.raises(ValueError):
        harm.commercial_cost_per_job(cfg, 1.0)
    small = harm.commercial_cost_per_job(CFG, 1.0, "small")["retail"]
    assert small / harm.commercial_cost_per_job(CFG, 1.0)["retail"] == pytest.approx(295.0 / 21.8)


# ---------------- optimizer: toy problems with known answers ----------------

def test_toy_protected_zone_cheapest_is_never_selected():
    z = toy([(1, 10.0, True, 0.0, 0.0), (2, 10.0, False, 0.9, 0.9), (3, 10.0, False, 0.5, 0.5)])
    r = optimizer.solve(z, 10.0, 1.0)
    assert 1 not in r.baseline.zone_ids and 1 not in r.weighted.zone_ids
    assert r.weighted.zone_ids == [3]  # lowest harm among selectable
    assert r.baseline.zone_ids == [2]  # equal loads: tie -> lowest zone_id among selectable


def test_toy_plans_differ_and_both_inside_band():
    z = toy([(1, 5.0, False, 0.9, 0.9), (2, 5.0, False, 0.1, 0.1), (3, 5.0, False, 0.1, 0.1)])
    r = optimizer.solve(z, 5.0, 0.5)
    assert r.baseline.zone_ids == [1] and r.weighted.zone_ids == [2]  # weighted tie 2 vs 3 -> lowest id
    assert r.zones_that_differ() == [1, 2]
    for p in (r.baseline, r.weighted):
        assert r.band_lo_mw <= p.mw_shed <= r.band_hi_mw + 1e-9


def test_toy_tiebreak_fewest_zones_then_lowest_id():
    z = toy([(1, 5.0, False, 0.5, 0.5), (2, 5.0, False, 0.5, 0.5), (3, 10.0, False, 1.0, 1.0)])
    r = optimizer.solve(z, 10.0, 0.5)
    assert r.baseline.zone_ids == [3] and r.weighted.zone_ids == [3]  # one zone beats two zones with identical totals


def test_toy_infeasible_returns_explanation_with_max_feasible():
    z = toy([(1, 5.0, False, 0.5, 0.5), (2, 5.0, False, 0.5, 0.5), (3, 50.0, True, 0.5, 0.5)])
    r = optimizer.solve(z, 20.0, 0.5)
    assert isinstance(r, Infeasible) and r.max_feasible_mw == 10.0 and "10.0 MW" in r.reason


def test_toy_band_widens_when_needed_and_reports_it():
    z = toy([(1, 10.0, False, 0.5, 0.5), (2, 10.4, False, 0.5, 0.5)])
    r = optimizer.solve(z, 10.1, 0.5)  # 2% band [10.1, 10.302] has no subset; 3% band reaches 10.403
    assert not isinstance(r, Infeasible) and r.widened and r.delta_pct_used == 3.0 and r.baseline.zone_ids == [2]


def test_toy_no_subset_even_at_widest_band_is_infeasible():
    z = toy([(1, 10.0, False, 0.5, 0.5), (2, 11.0, False, 0.5, 0.5)])
    r = optimizer.solve(z, 10.1, 0.5)  # sums are 10, 11, 21: none inside 10.1 to 10.605
    assert isinstance(r, Infeasible) and r.max_feasible_mw == 21.0 and "widened up to 5%" in r.reason


def test_matches_brute_force_on_random_small_problem():
    rng = np.random.default_rng(7)
    n = 12
    z = toy([(i + 1, float(rng.uniform(1, 9)), i in (3, 8), float(rng.uniform()), float(rng.uniform())) for i in range(n)])
    T = 0.4 * z.loc[~z["protected"], "L_mw"].sum()
    r = optimizer.solve(z, T, 0.5, band_pct=5.0, widen_pct=())
    assert not isinstance(r, Infeasible)
    H = (0.5 * z["Hhat_human"] + 0.5 * z["Hhat_econ"]).to_numpy()
    L = z["L_mw"].to_numpy(); free = [i for i in range(n) if not z.loc[i, "protected"]]
    best_load, best_h = np.inf, np.inf
    for k in range(1, len(free) + 1):
        for comb in itertools.combinations(free, k):
            s = L[list(comb)].sum()
            if T <= s <= T * 1.05:
                best_load, best_h = min(best_load, s), min(best_h, H[list(comb)].sum())
    assert r.baseline.mw_shed == pytest.approx(best_load, abs=0.01)
    chosen = [z.index[z["zone_id"] == i][0] for i in r.weighted.zone_ids]
    assert H[chosen].sum() == pytest.approx(best_h, abs=1e-4)


# ---------------- optimizer: real zones ----------------

@pytest.mark.parametrize("alpha", [0, 0.25, 0.5, 0.75, 1])
def test_real_both_plans_in_same_band_and_protected_never_selected(real, alpha):
    zh, c = real
    r = optimizer.solve(zh, c["T_NC08_mw"], alpha)
    assert not isinstance(r, Infeasible)
    prot = set(zh.loc[zh["protected"], "zone_id"])
    for p in (r.baseline, r.weighted):
        assert r.band_lo_mw - 1e-9 <= p.mw_shed <= r.band_hi_mw + 1e-9 and not (set(p.zone_ids) & prot)
        assert p.mw_shed == pytest.approx(zh.loc[zh["zone_id"].isin(p.zone_ids), "L_mw"].sum())
    assert r.baseline.mw_shed <= r.weighted.mw_shed + 0.011  # baseline is least-overshed within the 10 kW tolerance


def test_real_weighted_plan_optimal_at_alpha_extremes(real):
    zh, c = real
    r1 = optimizer.solve(zh, c["T_NC08_mw"], 1.0)
    assert r1.weighted.h_human <= r1.baseline.h_human  # alpha=1 minimizes human harm inside the shared band
    r0 = optimizer.solve(zh, c["T_NC08_mw"], 0.0)
    assert r0.weighted.h_econ <= r0.baseline.h_econ


def test_real_deterministic_and_fast(real):
    zh, c = real
    runs = [optimizer.solve(zh, c["T_NC08_mw"], 0.5) for _ in range(3)]
    for r in runs[1:]:  # strict: identical plans and totals every time
        assert r.baseline.zone_ids == runs[0].baseline.zone_ids and r.weighted.zone_ids == runs[0].weighted.zone_ids
        assert r.baseline.mw_shed == runs[0].baseline.mw_shed and r.weighted.h_human == runs[0].weighted.h_human
    # speed: best of three, so a busy machine cannot fail the test; spec target ~1 s, 2 s is the app's fallback threshold
    assert min(r.solve_seconds for r in runs) < 2.0


def test_real_infeasible_target_gives_explanation(real):
    zh, c = real
    free = zh.loc[~zh["protected"], "L_mw"].sum()
    r = optimizer.solve(zh, free * 1.01, 0.5)
    assert isinstance(r, Infeasible) and r.max_feasible_mw == pytest.approx(free)


def test_plan_totals_match_zone_table(real):
    zh, c = real
    r = optimizer.solve(zh, c["T_NC08_mw"], 0.5)
    s = zh[zh["zone_id"].isin(r.weighted.zone_ids)]
    assert r.weighted.households == s["occupied_units"].sum() and r.weighted.electric_heat_households == s["heat_electricity"].sum()
    assert r.weighted.h_human == pytest.approx(s["H_human"].sum()) and r.weighted.h_econ == pytest.approx(s["H_econ"].sum())


def test_delta_sensitivity_rows(real):
    zh, c = real
    df = sensitivity.delta_sensitivity(zh, c["T_NC08_mw"], 0.5, [1.0, 2.0, 5.0])
    assert df["solved"].all() and list(df["band_pct"]) == [1.0, 2.0, 5.0]
    assert (df["human_change_pct"] < 0).all() and (df["econ_change_pct"] < 0).all()  # harm difference survives every band


# ---------------- county-share cap ----------------

def toy_counties(rows):
    """rows: (zone_id, county, L, Hhat). Same filler columns as toy()."""
    z = toy([(i, L, False, h, h) for i, _, L, h in rows])
    z["COUNTYFP"] = [c for _, c, _, _ in rows]
    return z


def test_cap_forces_split_across_counties_for_both_plans():
    z = toy_counties([(1, "A", 5.0, 0.1), (2, "A", 5.0, 0.1), (3, "B", 5.0, 0.9), (4, "B", 5.0, 0.9)])
    off = optimizer.solve(z, 10.0, 0.5)
    assert off.baseline.zone_ids == [1, 2] and off.weighted.zone_ids == [1, 2]  # both pile into county A
    on = optimizer.solve(z, 10.0, 0.5, county_cap=0.5)
    for p in (on.baseline, on.weighted):
        counties = z[z["zone_id"].isin(p.zone_ids)].groupby("COUNTYFP")["L_mw"].sum()
        assert counties.max() <= 0.5 * counties.sum() + 1e-9 and len(counties) == 2
    assert on.baseline.zone_ids == [1, 3]  # tie-break picks lowest ids that satisfy the cap


def test_cap_on_real_zones_limits_every_county_in_both_plans(real):
    zh, c = real
    from metric_grid.model import scenarios
    for alpha in (0.25, 0.5, 1.0):
        r = optimizer.solve(zh, c["T_NC08_mw"], alpha, county_cap=0.5)
        assert not isinstance(r, Infeasible)
        for p in (r.baseline, r.weighted):
            assert scenarios.county_breakdown(zh, p)["share_of_cut"].max() <= 0.5 + 1e-6
            assert r.band_lo_mw - 1e-9 <= p.mw_shed <= r.band_hi_mw + 1e-9
            assert not set(p.zone_ids) & set(zh.loc[zh["protected"], "zone_id"])


def test_cap_off_by_default_matches_uncapped_and_cap_changes_the_baseline(real):
    zh, c = real
    assert CFG["optimizer"]["county_cap"]["enabled"] is False
    off, on = optimizer.solve(zh, c["T_NC08_mw"], 0.5), optimizer.solve(zh, c["T_NC08_mw"], 0.5, county_cap=0.5)
    assert off.baseline.zone_ids != on.baseline.zone_ids  # without the cap Cabarrus takes 69% of the baseline cut


def test_cap_with_single_county_is_infeasible_with_explanation():
    z = toy_counties([(1, "A", 5.0, 0.1), (2, "A", 5.0, 0.2)])
    r = optimizer.solve(z, 5.0, 0.5, county_cap=0.5)
    assert isinstance(r, Infeasible) and "county" in r.reason


def test_cap_value_validated():
    z = toy_counties([(1, "A", 5.0, 0.1), (2, "B", 5.0, 0.2)])
    with pytest.raises(ValueError):
        optimizer.solve(z, 5.0, 0.5, county_cap=1.5)
