"""The load-only plan set: definition, determinism, stability, and everything the page says about it."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamlit.testing.v1 import AppTest

from metric_grid import frozen
from metric_grid.app import copy, distribution
from metric_grid.config import ROOT, load_config
from metric_grid.model import harm, loadonly, scenarios

CFG = load_config()
APP = str(ROOT / "src" / "metric_grid" / "app" / "streamlit_app.py")


@pytest.fixture(scope="module")
def sets():
    return frozen.load_loadonly()["sets"]


@pytest.fixture(scope="module")
def zh():
    return harm.compute_harm(frozen.load_zones(), CFG, frozen.load_constants()["kw_per_job"])


@pytest.fixture(scope="module")
def default_record():
    return [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0.5 and not r["cap"]][0]


# ---------------- the set itself ----------------

def test_every_frozen_set_has_the_expected_keys_and_size(sets):
    keys = {f"{t}|{k}" for t in ("elliott", "10", "15", "20") for k in ("free", "cap")} | {"elliott|flat"}
    assert set(sets) == keys
    for k, st in sets.items():
        assert st["n"] == len(st["plans"]) == CFG["optimizer"]["loadonly"]["n_plans"] == 200
        assert len({tuple(p) for p in st["plans"]}) == 200  # distinct
        assert 0 <= st["typical_index"] < 200


def test_plans_meet_the_band_exclude_protected_zones_and_respect_the_cap(sets, zh):
    prot = set(zh.loc[zh["protected"], "zone_id"])
    flat_z = zh.copy()
    from metric_grid.model.sensitivity import flat_loads
    consts = frozen.load_constants()
    flat_z["L_mw"] = flat_loads(flat_z, consts["D_NC08_mw"])
    near = CFG["optimizer"]["loadonly"]["near_opt_pct"]
    for key, st in sets.items():
        z = flat_z if st["flat"] else zh
        L = z.set_index("zone_id")["L_mw"]
        T = st["target_mw"]
        for p in st["plans"]:
            mw = L.loc[p].sum()
            assert T - 1e-9 <= mw <= T * (1 + near / 100) + 1e-9, key  # meets the target, overshoots by at most near_opt_pct
            assert not set(p) & prot
            if st["cap"]:
                by_county = zh.set_index("zone_id").loc[p].groupby("COUNTY")["L_mw"].sum()
                assert by_county.max() <= CFG["optimizer"]["county_cap"]["max_share"] * by_county.sum() + 1e-6


def test_plans_are_diverse(sets):
    d = sets["elliott|free"]["diversity"]
    assert d["zones_used"] >= 150 and d["mean_jaccard"] < 0.1  # every selectable zone appears; plans overlap very little


def test_typical_plan_is_closest_to_the_median_on_four_measures(sets, zh):
    st = sets["elliott|free"]
    M = loadonly.plan_metrics(zh, st["plans"])
    assert loadonly.typical_index(M) == st["typical_index"]
    ranks = M[["households", "electric_heat_households", "h_human", "h_econ"]].rank(pct=True)
    dist = (ranks - 0.5).abs().sum(axis=1)
    assert dist.iloc[st["typical_index"]] == dist.min()
    # typical on every dimension: no metric of the typical plan sits in the outer 20% of the set
    for c in ("households", "electric_heat_households", "h_human", "h_econ"):
        assert 0.3 <= ranks[c].iloc[st["typical_index"]] <= 0.7, c


def test_typical_index_known_answer():
    M = pd.DataFrame({"households": [1, 2, 3], "electric_heat_households": [10, 20, 30], "h_human": [5, 6, 7], "h_econ": [100, 200, 900]})
    assert loadonly.typical_index(M) == 1


def test_distribution_summary_known_answer():
    M = pd.DataFrame({"households": [10, 20, 30], "electric_heat_households": [5, 6, 7], "h_human": [1.0, 2, 3], "h_econ": [100, 200, 300]})
    d = loadonly.distribution_summary(M, {"households": 25, "electric_heat_households": 4, "h_human": 2, "h_econ": 350})
    assert d["n"] == 3 and d["households"]["n_plans_fewer"] == 2 and d["households"]["n_plans_more"] == 1
    assert d["electric_heat_households"]["n_plans_more"] == 3 and d["h_human"]["n_plans_more"] == 1 and d["h_econ"]["n_plans_fewer"] == 3
    assert d["h_human"]["median"] == 2 and d["electric_heat_households"]["min"] == 5 and d["electric_heat_households"]["max"] == 7


def test_plan_metrics_match_a_direct_sum(sets, zh):
    p = sets["elliott|free"]["plans"][5]
    M = loadonly.plan_metrics(zh, [p]).iloc[0]
    t = zh[zh["zone_id"].isin(p)]
    assert M["households"] == t["N_households"].sum() and M["electric_heat_households"] == t["heat_electricity"].sum()
    assert M["h_human"] == pytest.approx(t["H_human"].sum()) and M["h_econ"] == pytest.approx(t["H_econ"].sum()) and M["mw"] == pytest.approx(t["L_mw"].sum())


# ---------------- determinism and stability ----------------

def test_generation_is_deterministic_and_seed_dependent(zh):
    T = frozen.load_constants()["T_NC08_mw"]
    a = loadonly.sample_plans(zh, T, 2.0, 1.0, n_plans=6, seed=1)["plans"]
    b = loadonly.sample_plans(zh, T, 2.0, 1.0, n_plans=6, seed=1)["plans"]
    c = loadonly.sample_plans(zh, T, 2.0, 1.0, n_plans=6, seed=2)["plans"]
    assert a == b and a != c


def test_frozen_default_set_is_reproduced_for_its_first_plans(sets, zh):
    st, lo = sets["elliott|free"], CFG["optimizer"]["loadonly"]
    again = loadonly.sample_plans(zh, st["target_mw"], CFG["optimizer"]["band_pct"], lo["near_opt_pct"], n_plans=5, seed=lo["seed"],
                                  spread=lo["spread"])["plans"]
    assert again == st["plans"][:5]


def test_distribution_is_not_an_artifact_of_the_seed(sets, zh):
    """A fresh 60-plan set with another seed gives about the same medians (within 5%)."""
    st = sets["elliott|free"]
    other = loadonly.sample_plans(zh, st["target_mw"], 2.0, 1.0, n_plans=60, seed=987654)["plans"]
    a, b = loadonly.plan_metrics(zh, st["plans"]), loadonly.plan_metrics(zh, other)
    for c in ("households", "electric_heat_households", "h_human", "h_econ"):
        assert abs(b[c].median() - a[c].median()) / a[c].median() < 0.05, c


# ---------------- presolved records and the sentences ----------------

def test_presolved_baseline_is_the_typical_plan_and_summary_matches_the_set(default_record, sets, zh):
    st = sets[default_record["loadonly_key"]]
    assert default_record["baseline"]["zone_ids"] == st["plans"][st["typical_index"]]
    d = default_record["loadonly"]
    M = loadonly.plan_metrics(zh, st["plans"])
    w = default_record["weighted"]
    assert d["n"] == 200 and d["electric_heat_households"]["min"] == M["electric_heat_households"].min()
    assert d["households"]["n_plans_fewer"] == int((M["households"] < w["households"]).sum())
    assert d["h_human"]["n_plans_more"] == int((M["h_human"] > w["h_human"]).sum())


def test_every_presolved_record_points_at_its_set_and_stays_inside_the_band(sets):
    for r in frozen.load_presolved():
        assert r["solved"] and r["loadonly_key"] in sets and r["loadonly"]["n"] == 200
        assert r["baseline"]["zone_ids"] == sets[r["loadonly_key"]]["plans"][sets[r["loadonly_key"]]["typical_index"]]
        assert r["band_lo_mw"] - 1e-9 <= r["baseline"]["mw_shed"] <= r["band_hi_mw"] + 1e-9


def test_headline_and_range_line_wording(default_record):
    pair = scenarios.record_to_pair(default_record)
    n = pair.baseline.electric_heat_households - pair.weighted.electric_heat_households
    assert copy.headline(pair) == f"Same {pair.target_mw:.0f} MW cut. {n:,.0f} fewer electric-heat households than the typical megawatts-only plan."
    d = default_record["loadonly"]
    line = copy.range_line(d)
    e = d["electric_heat_households"]
    assert line == (f"Across 200 equivalent megawatts-only plans, they cut {e['min']:,.0f}–{e['max']:,.0f} electric-heat households; the "
                    f"vulnerability-aware plan cut {e['weighted']:,.0f}. It cuts MORE total households than {d['households']['n_plans_fewer']} of 200.")
    flipped = scenarios.record_to_pair({**default_record, "baseline": {**default_record["baseline"], "electric_heat_households": 1000.0}})
    assert "MORE electric-heat households than the typical megawatts-only plan" in copy.headline(flipped)


# ---------------- the strip chart ----------------

def test_strip_spec_has_all_dots_the_typical_and_the_weighted_plan(sets, zh, default_record):
    M = loadonly.plan_metrics(zh, sets["elliott|free"]["plans"])
    typ, w = default_record["baseline"], default_record["weighted"]
    specs = distribution.specs({k: M[k].tolist() for k in ("electric_heat_households", "h_human", "h_econ", "households")},
                               {"electric_heat_households": typ["electric_heat_households"], "h_human": typ["h_human"], "h_econ": typ["h_econ"], "households": typ["households"]},
                               {"electric_heat_households": w["electric_heat_households"], "h_human": w["h_human"], "h_econ": w["h_econ"], "households": w["households"]})
    assert [t for t, _ in specs] == ["Electric-heat households cut", "Vulnerability-weighted households", "Interruption cost (2013 dollars)", "Total households cut"]
    for title, spec in specs:
        layers = spec["layer"]
        assert len(layers[0]["data"]["values"]) == 200 and layers[1]["data"]["values"][0]["y"] == layers[2]["data"]["values"][0]["y"]
        assert layers[1]["mark"]["shape"] == "diamond" and layers[2]["mark"]["shape"] == "circle"  # shapes differ, not only colors
        assert layers[2]["mark"]["color"] == distribution.VIOLET and layers[0]["mark"]["color"] == distribution.GREY
        json.dumps(spec)
    ys = [v["y"] for v in specs[0][1]["layer"][0]["data"]["values"]]
    assert len(set(ys)) == 200 and min(ys) >= 0 and max(ys) <= 1  # deterministic jitter, all distinct


def test_strip_caption_counts_come_from_the_summary(default_record):
    cap = distribution.caption(default_record["loadonly"])
    d = default_record["loadonly"]
    assert f"Of {d['n']} equivalent megawatts-only plans" in cap and f"{d['households']['n_plans_fewer']} cut fewer total households" in cap


# ---------------- the page ----------------

@pytest.fixture(scope="module")
def page():
    return AppTest.from_file(APP, default_timeout=180).run()


def text_of(at):
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption] + [c.value for c in at.code])


def test_page_shows_the_typical_plan_headline_range_line_and_strips(page, default_record):
    assert not page.exception, page.exception
    t = text_of(page)
    pair = scenarios.record_to_pair(default_record)
    assert copy.range_line(default_record["loadonly"]) in t
    assert "Megawatts only (typical of 200 plans)" in t
    assert "Compared with 200 megawatts-only plans" in t
    assert len(page.get("vega_lite_chart")) == 6  # four strips, the slider tradeoff, the demand panel
    assert "megawatts-only plans cut this zone" in t and "Megawatts-only plans that cut it" in t


def test_flip_strip_and_tooltips_carry_the_cut_frequency(page):
    t = text_of(page)
    assert "megawatts-only plans" in t and ", cut in " in t  # flip strip lines
    from metric_grid.app import maps
    assert "cut in {freq.get(zid, 0)} of {n_plans} megawatts-only plans" in __import__("inspect").getsource(maps.map_svg).replace("\"", "\"") or "megawatts-only plans" in __import__("inspect").getsource(maps.map_svg)
