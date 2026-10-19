"""Demand panel ("Why forecasts aren't enough"): content from the precomputed file, honest wording, hides cleanly if the file is missing."""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamlit.testing.v1 import AppTest

from metric_grid import frozen
from metric_grid.app import demand_panel as dp
from metric_grid.config import ROOT

APP = str(ROOT / "src" / "metric_grid" / "app" / "streamlit_app.py")
LABEL = "modeled demand estimate; not a utility forecast; does not predict outages or available supply"


def page_text(at: AppTest) -> str:
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption] + [c.value for c in at.code])


@pytest.fixture(scope="module")
def panel():
    return frozen.load_demand_panel()


@pytest.fixture(scope="module")
def page():
    return AppTest.from_file(APP, default_timeout=120).run()


# ---------------- content ----------------

def test_panel_file_exists_and_is_consistent_with_the_validation(panel):
    val = json.loads((ROOT / "data/frozen/demand_validation.json").read_text())
    assert panel["label"] == LABEL and panel["model"] == val["chosen"] == "boosted" and panel["n_winters"] == 8
    e = panel["elliott"]
    hold = val["holdout"][val["chosen"]]["elliott_morning_0700_local"]["DUK+CPLE"]
    assert e["actual_mw"] == hold["actual_mw"] == 33590 and e["predicted_mw"] == pytest.approx(hold["predicted_mw"], abs=1e-6)
    assert e["gap_mw"] == pytest.approx(e["predicted_mw"] - e["actual_mw"]) and e["gap_pct"] == pytest.approx(hold["error_pct"], abs=1e-9)
    assert panel["typical_mape_pct"] == pytest.approx(val["cv_combined_duk_cple"][val["chosen"]]["mape_pct"])
    assert len(panel["series"]) == 120 and all(r["actual_mw"] and r["predicted_mw"] for r in panel["series"])
    assert panel["series"][0]["local_end"] == "2022-12-22T01:00:00" and panel["series"][-1]["local_end"] == "2022-12-27T00:00:00"


def test_panel_prediction_comes_from_a_fit_that_never_saw_dec_2022(panel):
    from metric_grid.train import demand as m
    df = m.load_training()
    pool, _ = m.split_pool(df)
    fits = {ba: m.fit_model("boosted", pool, ba) for ba in ("DUK", "CPLE")}
    full = {ba: fits[ba].predict(df) for ba in fits}
    row = df[df["local_end"] == m.pd.Timestamp("2022-12-24 07:00", tz="America/New_York")].index[0]
    assert full["DUK"][row] + full["CPLE"][row] == pytest.approx(panel["elliott"]["predicted_mw"], abs=1e-6)


def test_sentence_uses_live_numbers_and_the_careful_shed_wording(panel):
    consts = frozen.load_constants()
    shed = dp.total_shed_mw(consts)
    assert shed == pytest.approx(1961.0)  # 1,000 + 961, computed from the frozen constants
    s = dp.sentence(panel, shed)
    e = panel["elliott"]
    assert f"Trained on {panel['n_winters']} winters (Elliott held out)" in s and f"typically within {panel['typical_mape_pct']:.1f}% of actual demand" in s
    assert f"it under-predicted by {abs(e['gap_pct']):.1f}% ({abs(e['gap_mw']):,.0f} MW)" in s
    assert "hour ending 07:00 (06:00-07:00)" in s and "so the true shortfall was larger" in s
    # not the false claim that the full maximum had already been excluded from that hour
    assert "up to about 1,961 MW by 7:56 a.m." in s and "still ramping up" in s and "already excluded ~1,961" not in s


def test_sentence_direction_flips_with_the_sign_of_the_gap(panel):
    flipped = {**panel, "elliott": {**panel["elliott"], "gap_mw": 500.0, "gap_pct": 1.5}}
    assert "over-predicted by 1.5%" in dp.sentence(flipped, 1961.0)


def test_chart_spec_marks_the_elliott_morning_and_uses_the_series(panel):
    spec = dp.chart_spec(panel)
    rows = spec["data"]["values"]
    assert {r["series"] for r in rows} == {"Actual (observed)", "Model prediction"} and len(rows) == 240
    layers = spec["layer"]
    assert any(l["mark"]["type"] == "rule" and l["data"]["values"][0]["t"] == "2022-12-24T07:00:00" for l in layers)
    label = [l for l in layers if l["mark"]["type"] == "text"][0]["data"]["values"][0]["label"]
    assert "33,590" in label and "29,369" in label and "-12.6%" in label
    json.dumps(spec)  # serializable


def test_temperature_table_and_cold_note(panel):
    html, note = dp.temperature_table(panel), dp.coldest_note(panel)
    assert "below 20 °F" in html and "<td>109</td>" in html and len(panel["error_by_temperature"]) == 6
    assert "only 109 training hours" in note and "biased low" in note


# ---------------- the page ----------------

def test_panel_is_on_the_default_page_with_labels(page, panel):
    assert not page.exception, page.exception
    text = page_text(page)
    assert "Why forecasts aren't enough" in text and LABEL in text
    assert dp.sentence(panel, dp.total_shed_mw(frozen.load_constants())) in text
    assert len(page.get("vega_lite_chart")) == 6  # four distribution strips, the slider tradeoff chart, plus this panel
    assert "<td>109</td>" in text


def test_panel_does_not_need_scikit_learn_at_runtime():
    import ast
    for f in (ROOT / "src/metric_grid/app").glob("*.py"):
        mods = {a.name.split(".")[0] for n in ast.walk(ast.parse(f.read_text())) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split(".")[0] for n in ast.walk(ast.parse(f.read_text())) if isinstance(n, ast.ImportFrom) and n.module}
        assert "sklearn" not in mods, f
    assert "scikit-learn" not in (ROOT / "requirements.txt").read_text()


# ---------------- hides cleanly ----------------

def _app_with_modified_frozen(monkeypatch, tmp_path, mutate):
    import streamlit as st
    st.cache_resource.clear()
    d = tmp_path / "frozen"
    shutil.copytree(ROOT / "data" / "frozen", d)
    mutate(d)
    monkeypatch.setattr(frozen, "FROZEN", d)
    try:
        return AppTest.from_file(APP, default_timeout=120).run()
    finally:
        st.cache_resource.clear()


def test_panel_hides_itself_if_its_frozen_file_is_missing(monkeypatch, tmp_path):
    at = _app_with_modified_frozen(monkeypatch, tmp_path, lambda d: (d / "demand_panel.json").unlink())
    assert not at.exception
    text = page_text(at)
    assert "Why forecasts aren't enough" not in text and "Vulnerable zones most often cut when only megawatts count" in text and "Same power cut. Different people in the dark." in text
    assert len(at.get("vega_lite_chart")) == 5  # the four distribution strips and the tradeoff chart remain


def test_panel_hides_itself_if_its_file_is_unreadable(monkeypatch, tmp_path):
    at = _app_with_modified_frozen(monkeypatch, tmp_path, lambda d: (d / "demand_panel.json").write_text("{not json"))
    assert not at.exception and "Why forecasts aren't enough" not in page_text(at)


def test_loader_returns_none_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(frozen, "FROZEN", tmp_path)
    assert frozen.load_demand_panel() is None
