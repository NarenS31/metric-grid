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
    assert len(at.get("deck_gl_json_chart")) == 2  # two maps


def test_headline_and_honest_line_use_live_numbers(default_page):
    text = page_text(default_page)
    rec = [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0.5 and not r["cap"]][0]
    pair = scenarios.record_to_pair(rec)
    assert copy.headline(pair) in text  # "Same 92 MW cut. 3,353 fewer electric-heat households in the dark."
    assert scenarios.plain_summary(pair) in text and "MORE households" in text  # never hidden
    assert "Same target, different burden." in text and "not an operational switching tool" in text


def test_required_district_sentence_and_labels_present(default_page):
    text = page_text(default_page)
    assert provenance.DISTRICT_SENTENCE in text
    for label in ("Modeled scenario", "North Carolina's 8th District", "Load-only baseline", "Vulnerability-aware plan",
                  "not Duke's method", "not an operational switching tool", "census tracts, not utility boundaries",
                  "Both plans cut between", "2013 dollars", "Where to plan first", "How robust is this?", "Flip strip"):
        assert label in text, label


def test_no_banned_words_in_ui_text(default_page):
    text = page_text(default_page).replace(provenance.DISTRICT_SENTENCE, "")  # rule 4 sentence is required verbatim
    for w in BANNED:
        assert not re.search(re.escape(w), text, re.I), w


def test_priority_card_matches_sensitivity_output(default_page):
    text = page_text(default_page)
    for rec in frozen.load_sensitivity()["priority_list"]:
        assert f"<tr><td>{rec['zone_id']}</td>" in text
    assert "not a finding about specific neighborhoods" in text


def test_robustness_card_counts_come_from_the_table(default_page):
    import pandas as pd
    rows = pd.DataFrame(frozen.load_sensitivity()["rows"])
    n, beat = len(rows), int((rows["human_change_pct"] < 0).sum())
    assert f"<b>{beat} of {n}</b> settings beat the load-only baseline on human harm" in page_text(default_page)


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
    [b for b in at.button if b.label == "Reset demo"][0].click().run()
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
    assert "No county takes more than 50% of either plan's cut." in page_text(at)
    assert "Showing nearest pre-computed setting" not in page_text(at)


def test_zone_detail_shows_formula_with_numbers():
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["zone"] = "23"
    at.run()
    code = "\n".join(c.value for c in at.code)
    assert "H_human = N x (0.7 x SVI + 0.3 x heat)" in code and "(2013 dollars)" in code and "L = D_NC08" in code
    assert "census tract zone" in page_text(at) and "load: modeled" in page_text(at)


# ---------------- copy and data layer ----------------

def test_headline_flips_wording_with_the_numbers():
    rec = [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0 and not r["cap"]][0]
    h = copy.headline(scenarios.record_to_pair(rec))
    assert "MORE electric-heat households" in h  # alpha 0: the weighted plan puts more electric-heat homes in the dark
    base = [r for r in frozen.load_presolved() if r["target_key"] == "elliott" and r["alpha"] == 0.5 and not r["cap"]][0]
    assert "fewer electric-heat households" in copy.headline(scenarios.record_to_pair(base))


def test_get_view_prefers_presolved_and_falls_back_with_a_note(monkeypatch):
    from metric_grid.app import data
    A = data.load_all()
    v = data.get_view(0.5, data.pct_options(A["consts"], A["cfg"])[0], False)
    assert v["source"] == "pre-solved" and v["note"] is None
    pct = 12.5  # not a preset: needs a live solve

    monkeypatch.setattr(data, "_live_solve", lambda a, t, c: {"error": "ValueError: boom"})
    v = data.get_view(0.5, pct, False)
    assert v["source"] == "nearest" and "Showing nearest pre-computed setting" in v["note"] and "boom" in v["note"]

    monkeypatch.setattr(data, "_live_solve", lambda a, t, c: {"infeasible": "too big", "max_feasible_mw": 1.0})
    assert "too big" in data.get_view(0.5, pct, False)["note"]

    rec = scenarios.pair_to_record(scenarios.record_to_pair(A["presolved"][0]), "live", 0.5)
    monkeypatch.setattr(data, "_live_solve", lambda a, t, c: {"record": rec, "elapsed": 3.1})
    slow = data.get_view(0.5, pct, False)
    assert slow["source"] == "nearest" and "took 3.1 s" in slow["note"]

    monkeypatch.setattr(data, "_live_solve", lambda a, t, c: {"record": rec, "elapsed": 0.4})
    assert data.get_view(0.5, pct, False)["source"] == "live"


def test_nearest_prefers_same_cap_setting():
    from metric_grid.app import data
    A = data.load_all()
    near = data.nearest_presolved(0.4, 100.0, A["consts"], A["presolved"], cap=True)
    assert near["cap"] is True
