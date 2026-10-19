"""Winter demand model tests: the Dec 2022 holdout never touches fitting or selection, results are deterministic, data is sane."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metric_grid.config import ROOT
from metric_grid.ingest import demand_history as dh
from metric_grid.train import demand as m

TZ = "America/New_York"


@pytest.fixture(scope="module")
def df():
    return m.load_training()


@pytest.fixture(scope="module")
def base_run(df):
    return m.run_validation(df)   # one protocol run, shared by the tests that only read it


@pytest.fixture(scope="module")
def frozen_validation():
    return json.loads((ROOT / "data" / "frozen" / "demand_validation.json").read_text())


# ---------------- the holdout is never in training ----------------

def test_split_is_a_partition_and_holdout_is_exactly_local_dec_2022(df):
    pool, hold = m.split_pool(df)
    assert len(pool) + len(hold) == len(df) and not set(pool.index) & set(hold.index)
    start = (hold["local_end"] - pd.Timedelta(hours=1))
    assert (start.dt.year == 2022).all() and (start.dt.month == 12).all() and len(hold) == 744
    ps = pool["local_end"] - pd.Timedelta(hours=1)
    assert not ((ps.dt.year == 2022) & (ps.dt.month == 12)).any()  # no Dec 2022 hour anywhere in the pool
    assert (pool["winter"] == 2023).any()  # Jan-Feb 2023 stay in the pool (only Dec 2022 is held out)


def test_no_fit_ever_sees_a_holdout_hour(df, monkeypatch):
    """Wrap fit_model during the whole protocol: every training frame must be free of Dec 2022 hours."""
    seen = []
    real = m.fit_model

    def spy(kind, train, ba):
        s = train["local_end"] - pd.Timedelta(hours=1)
        seen.append(int(((s.dt.year == 2022) & (s.dt.month == 12)).sum()))
        return real(kind, train, ba)

    monkeypatch.setattr(m, "fit_model", spy)
    m.run_validation(df)
    assert len(seen) >= 2 * 2 * 8 + 4 and sum(seen) == 0  # LOWO folds for both kinds and BAs, plus the final fits


def test_selection_and_cv_do_not_depend_on_holdout_values(df, base_run):
    """Poison the holdout demand: CV numbers and the chosen model must not move; only holdout scores may."""
    base = base_run
    poisoned = df.copy()
    _, hold = m.split_pool(df)
    poisoned.loc[hold.index, ["duk_mw", "cple_mw"]] = poisoned.loc[hold.index, ["duk_mw", "cple_mw"]] * 5
    alt = m.run_validation(poisoned)
    assert alt["chosen"] == base["chosen"] and alt["cv"] == base["cv"]
    assert alt["holdout"]["boosted"]["DUK"]["all_dec_2022"]["mae_mw"] != base["holdout"]["boosted"]["DUK"]["all_dec_2022"]["mae_mw"]


def test_selection_rule_is_the_preregistered_one(frozen_validation):
    cv = frozen_validation["cv"]
    gap = cv["linear"]["mean_mape_pct_both"] - cv["boosted"]["mean_mape_pct_both"]
    assert frozen_validation["close_pp"] == m.CLOSE_PP == 0.5
    assert frozen_validation["chosen"] == ("boosted" if gap >= m.CLOSE_PP else "linear")


# ---------------- determinism ----------------

def test_frozen_validation_is_reproduced_exactly(base_run, frozen_validation):
    again = base_run
    assert again["chosen"] == frozen_validation["chosen"]
    for kind in ("linear", "boosted"):
        assert again["cv"][kind]["mean_mape_pct_both"] == pytest.approx(frozen_validation["cv"][kind]["mean_mape_pct_both"], abs=1e-9)
        a, f = again["holdout"][kind]["elliott_morning_0700_local"], frozen_validation["holdout"][kind]["elliott_morning_0700_local"]
        assert a["DUK+CPLE"]["predicted_mw"] == pytest.approx(f["DUK+CPLE"]["predicted_mw"], abs=1e-6)


def test_fits_are_deterministic(df):
    pool, hold = m.split_pool(df)
    for kind in ("linear", "boosted"):
        a, b = m.fit_model(kind, pool, "DUK").predict(hold), m.fit_model(kind, pool, "DUK").predict(hold)
        assert a.equals(b)


# ---------------- data and feature sanity ----------------

def test_training_table_shape_and_winter_months_only(df):
    assert sorted(df["winter"].unique()) == list(range(2018, 2026))
    start = df["local_end"] - pd.Timedelta(hours=1)
    assert set(start.dt.month) == {12, 1, 2}
    assert df["utc_end"].is_unique and df["utc_end"].is_monotonic_increasing
    per_winter = df.groupby("winter").size()
    assert per_winter.between(2160, 2184).all()  # 90 or 91 days of hourly rows per winter, no stray November or March hours
    assert (df[["duk_mw", "cple_mw"]].dropna() > 0).all().all()
    assert df["duk_mw"].isna().sum() == 0 and df["cple_mw"].isna().sum() <= 30  # gaps are left missing, never filled


def test_hour_ending_label_ties_to_the_main_projects_eia_series(df):
    row = df[df["local_end"] == pd.Timestamp("2022-12-24 07:00", tz=TZ)].iloc[0]
    assert row["duk_mw"] == 20879 and row["cple_mw"] == 12711  # the same numbers the district scaling uses
    assert row["kclt_f"] == pytest.approx(10.0, abs=1.0)


def test_sources_are_api_from_2019_and_bulk_before(df):
    early = df[df["utc_end"] < dh.API_FIRST]
    assert set(early["duk_src"]) == {"bulk"} and set(df[df["utc_end"] >= dh.API_FIRST]["duk_src"]) == {"api"}


def test_federal_holidays_and_features():
    hol = m.federal_holidays([2022, 2023])
    import datetime as d
    assert d.date(2022, 12, 26) in hol and d.date(2023, 1, 2) in hol and d.date(2023, 1, 16) in hol and d.date(2022, 12, 25) not in hol
    row = pd.DataFrame({"local_end": [pd.Timestamp("2022-12-24 07:00", tz=TZ)], "kclt_f": [10.0]})
    row["utc_end"] = row["local_end"].dt.tz_convert("UTC")
    X = m.make_features(row, "kclt_f").iloc[0]
    assert X["hour_ending"] == 7 and X["weekend"] == 1 and X["holiday_week"] == 1 and X["hdh"] == 55.0 and X["holiday"] == 0


def test_metrics_known_answer():
    a, p = pd.Series([100.0, 200.0, np.nan]), pd.Series([110.0, 180.0, 5.0])
    r = m.metrics(a, p)
    assert r["n"] == 2 and r["mae_mw"] == 15.0 and r["mape_pct"] == pytest.approx(10.0) and r["bias_mw"] == -5.0


def test_missing_inputs_are_never_filled(df):
    pool, _ = m.split_pool(df)
    fit = m.fit_model("linear", pool, "DUK")
    probe = pool.head(3).copy()
    probe.loc[probe.index[1], "kclt_f"] = np.nan
    pred = fit.predict(probe)
    assert pred.isna().tolist() == [False, True, False]


# ---------------- data pipeline helpers ----------------

def test_temperature_gap_policy_interpolates_short_gaps_only():
    raw = pd.DataFrame({"utc": pd.to_datetime(["2022-01-01 00:52", "2022-01-01 01:52", "2022-01-01 05:52", "2022-01-01 06:52",
                                               "2022-01-01 12:52"], utc=True), "temp_f": [10.0, 12, 20, 22, 30]})
    h = dh.hourly_temperature(raw, max_gap_hours=3).set_index("utc_end")["temp_f"]
    assert [h[f"2022-01-01 0{i}:00+00:00"] for i in (3, 4, 5)] == [14.0, 16.0, 18.0]  # a 3-hour gap is interpolated
    assert h["2022-01-01 08:00+00:00":"2022-01-01 12:00+00:00"].isna().all()  # a 5-hour gap stays missing (no fill at all)


def test_api_vs_bulk_comparison_detects_the_hour_convention():
    t = pd.date_range("2019-01-01 05:00", periods=6, freq="h", tz="UTC")
    api = pd.DataFrame({"resp": "DUK", "utc_end": t, "mw": [1.0, 2, 3, 4, 5, 6]})
    same = api.copy()
    shifted = api.assign(utc_end=api["utc_end"] + pd.Timedelta(hours=1))   # a bulk file that is one hour later
    assert dh.compare_api_bulk(api, same)[0]["share_exact"] == 1.0
    r = dh.compare_api_bulk(api, shifted)
    assert r[0]["share_exact"] < 1.0 and r[-1]["share_exact"] == 1.0


def test_report_confirms_api_labels_are_hour_ending():
    rep = json.loads((ROOT / "data" / "frozen" / "demand_training_report.json").read_text())
    ov = rep["api_vs_bulk_overlap_by_column"][rep["bulk_column_used"]]
    assert ov["0"]["n"] > 2000 and ov["0"]["share_exact"] == 1.0 and ov["1"]["share_exact"] < 0.01 and ov["-1"]["share_exact"] < 0.01
