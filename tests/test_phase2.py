"""Phase 2 tests: EIA parsing, reduction ratio, NOAA parsing, NREL window fetch and reference-hour averaging."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metric_grid.config import ROOT, load_config
from metric_grid.ingest import eia930, noaa, resstock

PROCESSED = ROOT / "data" / "raw" / "processed"


def _payload(values):
    rows = [{"period": f"2022-12-24T{h:02d}", "value": str(v)} for h, v in enumerate(values)]
    return {"response": {"data": rows}}


def test_eia_parse_utc_to_local():
    df = eia930.parse_eia(_payload([100 + h for h in range(24)]), "America/New_York")
    row = df[df.local_time.dt.strftime("%H") == "07"].iloc[0]
    assert row.period_utc.hour == 12 and row.demand_mw == 112  # 07:00 EST = 12:00 UTC


def test_eia_missing_value_raises_not_filled():
    p = _payload([1, 2, 3]); p["response"]["data"][1]["value"] = None
    with pytest.raises(ValueError):
        eia930.parse_eia(p, "America/New_York")


def test_reduction_ratio_formula():
    cfg = load_config()
    df = eia930.parse_eia(_payload([20000] * 24), cfg["scenario"]["local_tz"])
    r = eia930.reduction_ratio(df, cfg)
    assert r["r"] == pytest.approx(cfg["scenario"]["shed_mw_regional"] / 20000)


def test_noaa_missing_rows_dropped_not_filled():
    raw = pd.DataFrame({"station": ["CLT"] * 3, "valid": ["2022-12-24 12:00", "2022-12-24 13:00", "2022-12-24 14:00"],
                        "tmpf": ["10.0", "M", "12.0"]})
    out = noaa.parse_iem(raw, "America/New_York", "2022-12-24", "2022-12-24")
    assert list(out.temp_f) == [10.0, 12.0]


def _fake_csv(n_days=3):
    ts = pd.date_range("2018-01-01 00:15", periods=n_days * 96, freq="15min")
    df = pd.DataFrame({"upgrade": 0, "in.state": "NC", "x": "pad" * 10, "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                       "units_represented": 100.0, resstock.TOTAL_COL: 1.0})
    return df.to_csv(index=False)


def test_fetch_window_bisect_returns_exact_rows(monkeypatch):
    text = _fake_csv(30)
    data = text.encode()

    def fake_get_range(url, start, end):
        return data[start:end + 1].decode()

    monkeypatch.setattr(resstock, "_get_range", fake_get_range)
    t0, t1 = pd.Timestamp("2018-01-10 00:15"), pd.Timestamp("2018-01-12 00:00")
    df = resstock.fetch_window("fake://x", len(data), t0, t1)
    assert len(df) == 2 * 96 and df.timestamp.min() == t0 and df.timestamp.max() == t1


def test_fetch_window_at_file_start(monkeypatch):
    data = _fake_csv(30).encode()
    monkeypatch.setattr(resstock, "_get_range", lambda u, s, e: data[s:e + 1].decode())
    df = resstock.fetch_window("fake://x", len(data), pd.Timestamp("2018-01-01 00:15"), pd.Timestamp("2018-01-03 00:00"))
    assert len(df) == 2 * 96


def test_reference_hour_mean_uses_period_ending_stamps():
    ts = pd.date_range("2018-01-01 00:15", periods=2 * 96, freq="15min")
    df = pd.DataFrame({"timestamp": ts, "kwh": 0.0})
    in_hour = (ts - pd.Timedelta(minutes=15)).hour == 7  # stamps 07:15, 07:30, 07:45, 08:00
    df.loc[in_hour, "kwh"] = 2.5
    assert resstock.reference_hour_mean(df, "kwh", 7) == pytest.approx(10.0)  # 4 x 2.5 kWh in the hour = 10 kW


def test_reference_hour_mean_gap_raises():
    ts = pd.date_range("2018-01-01 00:15", periods=96, freq="15min")
    df = pd.DataFrame({"timestamp": ts, "kwh": 1.0}).drop(index=30)
    with pytest.raises(ValueError):
        resstock.reference_hour_mean(df, "kwh", 7)


@pytest.mark.skipif(not (PROCESSED / "eia930_duk.csv").exists(), reason="run `make data` first")
def test_saved_eia_series_complete_and_peak_at_0700():
    df = pd.read_csv(PROCESSED / "eia930_duk.csv", parse_dates=["period_utc"])
    assert len(df) == 120 and df.demand_mw.notna().all()
    assert df.demand_mw.max() == 20879  # Elliott morning peak, 2022-12-24 07:00 EST
