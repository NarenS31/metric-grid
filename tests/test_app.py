"""App tests: default state renders offline, copy never hides who is cut, fallbacks work, every number has a source."""
import re
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamlit.testing.v1 import AppTest

from metric_grid import frozen
from metric_grid.app import copy, provenance
from metric_grid.config import ROOT
from metric_grid.model import scenarios

APP = str(ROOT / "src" / "metric_grid" / "app" / "streamlit_app.py")
BANNED = ["privacy-preserving", "federated learning", "AI optimizer", "conventional plan", "circuit", "feeder", "service area",
          "neighborhood demand", "least harm", "outage plan"]


def block_network(monkeypatch):
    def blocked(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


def page_text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption] + [c.value for c in at.code]
    return "\n".join(parts)


@pytest.fixture(scope="module")
def default_page():
    with pytest.MonkeyPatch.context() as mp:
        block_network(mp)  # spec rule 8: renders with every network call blocked
        at = AppTest.from_file(APP, default_timeout=120).run()
    return at


def test_default_state_renders_offline(default_page):
    at = default_page
    assert not at.exception, at.exception
    text = page_text(at)
    assert text.count("<svg class=\"map\"") == 2 and "deck_gl" not in str(at.get("deck_gl_json_chart"))  # two inline SVG maps, no WebGL


def test_headline_and_honest_line_use_live_numbers(default_page):
    text = page_text(default_page)
    rec = [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0.5 and not r["cap"]][0]
    pair = scenarios.record_to_pair(rec)
    assert "Same power cut. Different people in the dark." in text
    for tile in (f"{pair.target_mw:.0f} MW", f"{pair.baseline.electric_heat_households - pair.weighted.electric_heat_households:,.0f}",
                 f"+{pair.weighted.households - pair.baseline.households:,.0f}"):
        assert f"<div class='v'>{tile}</div>" in text  # the four stat tiles, the honest one included
    assert "more total homes cut" in text
    assert scenarios.plain_summary(pair) in text and "MORE households" in text  # never hidden
    assert "not an operational switching tool" in text


def test_required_district_sentence_and_labels_present(default_page):
    text = page_text(default_page)
    assert provenance.DISTRICT_SENTENCE in text
    for label in ("NC-08 · Modeled scenario", "Megawatts only (typical of 200 plans)", "Vulnerability-aware", "Compared with 200 megawatts-only plans", "Look up a zone", "Why forecasts aren't enough",
                  "not Duke's method", "not an operational switching tool", "census tracts, not utility boundaries",
                  "Both plans cut between", "2013 dollars", "Vulnerable zones most often cut when only megawatts count", "How robust is this?"):
        assert label in text, label


def test_no_banned_words_in_ui_text(default_page):
    text = page_text(default_page).replace(provenance.DISTRICT_SENTENCE, "")  # rule 4 sentence is required verbatim
    for w in BANNED:
        assert not re.search(re.escape(w), text, re.I), w


def test_priority_card_matches_sensitivity_output(default_page):
    text = page_text(default_page)
    assert "Vulnerable zones most often cut when only megawatts count" in text and "Where to plan first" not in text
    for rec in frozen.load_sensitivity()["priority_list"]:
        assert f"<tr><td>{rec['zone_id']}</td>" in text
        assert f"{rec['loadonly_cut_share']:.0%} ({rec['loadonly_cut_count']} of 200)" in text
        assert f"{'Yes' if rec['vuln_aware_cuts'] else 'No'} (cut in {rec['vuln_aware_cut_settings']} of {rec['n_settings']} settings)" in text
    for col in ("% of megawatts-only plans that cut it", "Vulnerability-aware plan cuts it?"):
        assert col in text
    assert "not a uniform sample of all such plans, so these frequencies are indicative" in text
    assert "CDC Social Vulnerability Index (SVI) of 0.75 or more, or an electric-heat share of 50% or more" in text


def test_robustness_card_counts_come_from_the_table(default_page):
    import pandas as pd
    rows = pd.DataFrame(frozen.load_sensitivity()["rows"])
    n, beat = len(rows), int((rows["human_change_pct"] < 0).sum())
    assert f"<b>{beat} of {n}</b> settings beat the typical megawatts-only plan on vulnerability-weighted households" in page_text(default_page)


def test_every_number_kind_has_a_source_in_the_drawer(default_page):
    consts = frozen.load_constants()
    names = [d["name"] for d in consts["datasets"]]
    for what, (label, tokens) in provenance.UI_SOURCES.items():
        for tok in tokens:
            assert any(tok in nm for nm in names), (what, tok)  # each source token resolves to a listed dataset
    text = page_text(default_page)
    for d in consts["datasets"]:
        assert d["name"] in text and d["url"] in text  # name, vintage and URL are in the drawer
    for what in provenance.UI_SOURCES:
        assert what in text


def test_reset_button_restores_defaults():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.select_slider(key="alpha").set_value(1.0).run()
    assert at.session_state["alpha"] == 1.0
    [b for b in at.button if b.label == "Reset"][0].click().run()
    assert at.session_state["alpha"] == 0.5 and at.session_state["cap"] is False


def test_alpha_one_and_zero_both_state_the_household_count():
    for alpha, word in ((1.0, "MORE households"), (0.0, "MORE households")):
        at = AppTest.from_file(APP, default_timeout=120)
        at.query_params["alpha"] = str(alpha)
        at.run()
        assert not at.exception and word in page_text(at)


def test_cap_toggle_uses_presolved_capped_record():
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["cap"] = "1"
    at.run()
    assert not at.exception
    assert "No county takes more than 50% of either plan's cut" in page_text(at)
    assert "Showing nearest pre-computed setting" not in page_text(at)


def test_zone_detail_shows_formula_with_numbers():
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["zone"] = "23"
    at.run()
    code = "\n".join(c.value for c in at.code)
    assert "at-risk score = households x (0.7 x SVI + 0.3 x heat)" in code and "(2013 dollars)" in code and "district load x" in code
    assert "census tract zone" in page_text(at) and "load: modeled" in page_text(at)


# ---------------- copy and data layer ----------------

def test_headline_flips_wording_with_the_numbers():
    rec = [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0 and not r["cap"]][0]
    h = copy.headline(scenarios.record_to_pair(rec))
    assert "MORE electric-heat households" in h  # alpha 0: the weighted plan puts more electric-heat homes in the dark
    base = [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0.5 and not r["cap"]][0]
    assert "fewer electric-heat households" in copy.headline(scenarios.record_to_pair(base))


def test_get_view_uses_the_presolved_grid_and_falls_back_with_a_note(monkeypatch):
    from metric_grid.app import data
    A = data.load_all()
    v = data.get_view(0.5, data.pct_options(A["consts"], A["cfg"])[0], False)
    assert v["source"] == "pre-solved" and v["note"] is None and v["record"]["loadonly"]["n"] == 200
    off = data.get_view(0.5, 12.5, False)  # not a slider stop, so not pre-computed
    assert off["source"] == "nearest" and "not pre-computed" in off["note"] and not off["infeasible"]
    _with_infeasible_record(monkeypatch)
    inf = data.get_view(0.5, data.pct_options(A["consts"], A["cfg"])[0], False)
    assert inf["source"] == "nearest" and inf["infeasible"] and "999.0 MW" in inf["note"]


def test_nearest_prefers_same_cap_setting():
    from metric_grid.app import data
    A = data.load_all()
    near = data.nearest_presolved(0.4, 100.0, A["consts"], A["presolved"], cap=True)
    assert near["cap"] is True


# ---------------- Phase 6: default zone, demo locations, tooltips, empty / infeasible / missing-data states ----------------

def test_zone_detail_opens_on_top_priority_zone_by_default(default_page):
    top = frozen.load_sensitivity()["priority_list"][0]["zone_id"]
    text = page_text(default_page)
    assert f"**Zone {top}**" in text and "at-risk score = households x (0.7 x SVI + 0.3 x heat)" in page_text(default_page)


def test_zone_detail_empty_state_when_no_zone_selected():
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["zone"] = "0"
    at.run()
    assert not at.exception and "Select a zone to see its inputs and the formula" in page_text(at)


def test_example_locations_each_inside_a_zone_of_the_right_county():
    from metric_grid.app import lookup
    from metric_grid.config import load_config
    z = frozen.load_zones()
    locs = load_config()["example_locations"]
    assert len(locs) == 3 and {l["county"] for l in locs} == {"Union", "Robeson", "Cabarrus"}
    for loc in locs:
        zid = lookup.locate(z, loc["lat"], loc["lon"])
        assert zid is not None
        assert z.loc[z["zone_id"] == zid, "COUNTY"].iloc[0] == f"{loc['county']} County"
        assert "home" not in loc["label"].lower() and "residence" not in loc["label"].lower() and loc["source"]


def test_example_locations_illustrate_a_difference_between_the_plans(default_page):
    from metric_grid.app import lookup
    from metric_grid.config import load_config
    rec = [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0.5 and not r["cap"]][0]
    rows = {r["zone_id"]: r for r in lookup.lookup_rows(frozen.load_zones(), load_config()["example_locations"], scenarios.record_to_pair(rec))}
    got = sorted((r["baseline"], r["weighted"]) for r in rows.values())
    assert got == sorted([("CUT", "kept on"), ("kept on", "CUT"), ("kept on", "kept on")])  # one spared, one cut instead, one unchanged
    assert (rows[17]["baseline"], rows[17]["weighted"]) == ("CUT", "kept on")  # the Harrisburg fire station: spared
    assert (rows[141]["baseline"], rows[141]["weighted"]) == ("kept on", "CUT")  # Hemby Bridge: cut instead
    assert (rows[100]["baseline"], rows[100]["weighted"]) == ("kept on", "kept on")  # the Robeson library: unchanged
    assert "Example locations" in page_text(default_page) and "Demo locations" not in page_text(default_page)


def test_locate_and_status_edge_cases():
    from metric_grid.app import lookup
    z = frozen.load_zones()
    assert lookup.locate(z, 0.0, 0.0) is None and lookup.status(z, None, scenarios.record_to_pair(frozen.load_presolved()[0]).baseline) == "outside NC-08 zones"
    prot = int(z.loc[z["protected"], "zone_id"].iloc[0])
    pair = scenarios.record_to_pair(frozen.load_presolved()[0])
    assert lookup.status(z, prot, pair.weighted) == "protected, never cut"
    cut = pair.weighted.zone_ids[0]
    assert lookup.status(z, cut, pair.weighted) == "CUT"


def test_example_location_table_shows_status_under_both_plans(default_page):
    from metric_grid.app import lookup
    from metric_grid.config import load_config
    text = page_text(default_page)
    rec = [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0.5 and not r["cap"]][0]
    pair = scenarios.record_to_pair(rec)
    for row in lookup.lookup_rows(frozen.load_zones(), load_config()["example_locations"], pair):
        assert f"<td>{row['label']}</td><td>{row['zone_id']}</td><td>{row['baseline']}</td><td>{row['weighted']}</td><td>" in text


def test_tooltips_for_svi_ice_census_tract_zone_and_target_band(default_page):
    html = "\n".join(m.value for m in default_page.markdown)
    for key, needle in (("SVI", "Social Vulnerability Index"), ("ICE", "Interruption Cost Estimate"),
                        ("census tract zone", "not a utility service boundary"), ("target band", "operators cannot hit an exact MW")):
        assert re.search(rf"class='tip' title=\"[^\"]*{re.escape(needle)}", html), key


def _with_infeasible_record(monkeypatch):
    """Replace the default (Elliott, alpha 0.5, cap off) pre-solved record with an infeasible one."""
    from metric_grid.app import data
    A = data.load_all()
    recs = [dict(r) for r in A["presolved"]]
    for r in recs:
        if r["target_key"] == "elliott" and r["alpha"] == 0.5 and not r["cap"]:
            r.update(solved=False, reason="Requested 999.0 MW exceeds the unprotected load.", max_feasible_mw=1407.5)
    monkeypatch.setitem(A, "presolved", recs)


def test_infeasible_target_shows_explanation_and_nearest_result(monkeypatch):
    _with_infeasible_record(monkeypatch)
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    text = page_text(at)
    assert "This target cannot be met" in text and "maximum feasible reduction 1407.5 MW" in text
    assert "class='note warn'" in text and "Showing the nearest pre-computed setting" in text


def test_slider_has_only_the_four_presolved_stops():
    from metric_grid.app import data
    from metric_grid.config import load_config
    consts = frozen.load_constants()
    opts = data.pct_options(consts, load_config())
    assert len(opts) == 4 and opts[1:] == [10, 15, 20]
    assert abs(opts[0] - 100 * consts["T_NC08_mw"] / consts["D_NC08_mw"]) < 1e-12
    for p in opts:  # every stop is pre-solved for every alpha, cap on and off: normal use never solves live
        key, _ = data.target_for(p, consts)
        for cap in (False, True):
            assert {r["alpha"] for r in frozen.load_presolved() if r["target_key"] == key and r["cap"] == cap and r["solved"]} == {0, 0.25, 0.5, 0.75, 1}
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["pct"] = "12.5"  # off-grid deep link snaps to a stop
    at.run()
    assert not at.exception and at.session_state["pct"] in opts and "Showing nearest" not in page_text(at)


def test_missing_frozen_data_state_explains_what_to_do(monkeypatch, tmp_path):
    import streamlit as st
    st.cache_resource.clear()
    monkeypatch.setattr(frozen, "FROZEN", tmp_path)  # an empty folder stands in for a missing data/frozen/
    try:
        at = AppTest.from_file(APP, default_timeout=120).run()
        assert not at.exception
        assert "The frozen data is missing." in page_text(at)
        assert any("make freeze" in e.value for e in at.error)
    finally:
        st.cache_resource.clear()


def test_missing_svi_zone_is_called_out_on_the_page(default_page):
    assert "Zone 9 has no SVI data but 0 occupied households" in page_text(default_page)


def test_drawer_band_text_uses_config_not_a_typed_number(default_page):
    from metric_grid.config import load_config
    widen = max(load_config()["optimizer"]["band_widen_pct"])
    assert f"widened to at most {widen:.0f}% if needed" in page_text(default_page)
