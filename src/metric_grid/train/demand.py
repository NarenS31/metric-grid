"""Winter demand model: hourly balancing-authority demand (MW) from temperature and calendar. A modeled demand estimate, not a
utility forecast; it does not predict outages or available supply.

Design is fixed BEFORE looking at the Dec 2022 holdout (and never changed after):
  features  heating degree-hours HDH = max(0, 65 F - T); hour-ending (1..24); weekend; US federal holiday (observed);
            holiday week (Dec 24 - Jan 1); linear trend (years since 2018-01-01).
  baseline  ordinary least squares on those features (explainable: one coefficient per feature).
  boosted   sklearn HistGradientBoostingRegressor (deterministic) on T, HDH, calendar features and a 3-hour lagged HDH.
  selection leave-one-winter-out cross-validation on the training pool ONLY (the pool excludes Dec 2022 in every fold). The boosted
            model replaces the baseline only if its mean CV MAPE is lower by at least CLOSE_PP percentage points.
  holdout   Dec 2022 (local) is never used for fitting, selection or tuning; it is scored once, after the choice is made.
Hours are labelled by the END of the hour (EIA convention); 'hour-ending 07' is the hour 06:00-07:00.
"""
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression

from metric_grid.config import ROOT

FROZEN = ROOT / "data" / "frozen"
BASE_F = 65.0
CLOSE_PP = 0.5                      # "close" = within 0.5 percentage points of mean CV MAPE; then prefer the simple model
HOLDOUT = ("2022-12-01", "2023-01-01")   # local Dec 2022 [start, end)
STORM = ("2022-12-23", "2022-12-26")     # Dec 23-25 local, a secondary holdout slice defined in advance
TREND_ORIGIN = pd.Timestamp("2018-01-01", tz="America/New_York")
BA_COLUMNS = {"DUK": ("duk_mw", "kclt_f"), "CPLE": ("cple_mw", "krdu_f")}
GB_PARAMS = dict(max_iter=300, learning_rate=0.05, max_depth=4, min_samples_leaf=40, l2_regularization=1.0,
                 early_stopping=False, random_state=0)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> pd.Timestamp:
    d = pd.Timestamp(year=year, month=month, day=1)
    d += pd.Timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))
    return d


def federal_holidays(years) -> set:
    """Observed US federal holidays falling in winter: New Year's Day, MLK Day, Presidents Day, Christmas Day."""
    out = set()
    for y in years:
        for d in (pd.Timestamp(year=y, month=1, day=1), pd.Timestamp(year=y, month=12, day=25)):
            out.add(d - pd.Timedelta(days=1) if d.weekday() == 5 else d + pd.Timedelta(days=1) if d.weekday() == 6 else d)
        out.add(_nth_weekday(y, 1, 0, 3))
        out.add(_nth_weekday(y, 2, 0, 3))
    return {d.date() for d in out}


def make_features(df: pd.DataFrame, temp_col: str) -> pd.DataFrame:
    """Feature table for rows of the training table (needs local_end and the temperature column)."""
    start = df["local_end"] - pd.Timedelta(hours=1)           # the hour being described
    T = df[temp_col].astype(float)
    X = pd.DataFrame(index=df.index)
    X["temp_f"] = T
    X["hdh"] = (BASE_F - T).clip(lower=0)
    X["hour_ending"] = (start.dt.hour + 1).astype(int)
    X["weekend"] = (start.dt.weekday >= 5).astype(int)
    hol = federal_holidays(range(2017, 2027))
    X["holiday"] = start.dt.date.map(lambda d: d in hol).astype(int)
    md = start.dt.month * 100 + start.dt.day
    X["holiday_week"] = ((md >= 1224) | (md <= 101)).astype(int)
    X["trend_years"] = (start - TREND_ORIGIN).dt.total_seconds() / (365.25 * 86400)
    return X


def linear_matrix(X: pd.DataFrame) -> pd.DataFrame:
    """Design matrix for the baseline: HDH, hour-ending dummies (2..24), weekend, holiday, holiday week, trend."""
    M = X[["hdh", "weekend", "holiday", "holiday_week", "trend_years"]].copy()
    for h in range(2, 25):
        M[f"hour_{h:02d}"] = (X["hour_ending"] == h).astype(int)
    return M


def boosted_matrix(X: pd.DataFrame, df: pd.DataFrame, temp_col: str) -> pd.DataFrame:
    """Features for the boosted model: raw features plus HDH lagged 3 hours (computed within contiguous hours only)."""
    M = X[["temp_f", "hdh", "hour_ending", "weekend", "holiday", "holiday_week", "trend_years"]].copy()
    ordered = df.sort_values("utc_end")
    hdh = (BASE_F - ordered[temp_col].astype(float)).clip(lower=0)
    gap_ok = ordered["utc_end"].diff().eq(pd.Timedelta(hours=1))
    lag = hdh.shift(3).where(gap_ok & gap_ok.shift(1, fill_value=False) & gap_ok.shift(2, fill_value=False))
    M["hdh_lag3"] = lag.reindex(df.index)
    return M


@dataclass
class Fit:
    kind: str
    model: object
    columns: list
    ba: str

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """Predicted MW for rows of `df` (NaN where inputs are missing). Never fills missing inputs."""
        temp = BA_COLUMNS[self.ba][1]
        X = make_features(df, temp)
        M = linear_matrix(X) if self.kind == "linear" else boosted_matrix(X, df, temp)
        ok = M[self.columns].notna().all(axis=1)
        out = pd.Series(np.nan, index=df.index)
        if ok.any():
            out[ok] = self.model.predict(M.loc[ok, self.columns])
        return out


def _clean(df: pd.DataFrame, ba: str) -> pd.DataFrame:
    mw, t = BA_COLUMNS[ba]
    return df[df[mw].notna() & df[t].notna() & (df[mw] > 0)]


def fit_model(kind: str, train: pd.DataFrame, ba: str) -> Fit:
    """Fit one model kind ('linear' or 'boosted') for one balancing authority on the given training rows."""
    mw, t = BA_COLUMNS[ba]
    tr = _clean(train, ba)
    X = make_features(tr, t)
    if kind == "linear":
        M = linear_matrix(X)
        model = LinearRegression().fit(M, tr[mw])
    else:
        M = boosted_matrix(X, tr, t).dropna()
        model = HistGradientBoostingRegressor(**GB_PARAMS).fit(M, tr.loc[M.index, mw])
    return Fit(kind, model, list(M.columns), ba)


def metrics(actual: pd.Series, pred: pd.Series) -> dict:
    """MAE (MW), MAPE (%), bias (mean predicted minus actual, MW) over rows where both exist."""
    ok = actual.notna() & pred.notna()
    a, p = actual[ok], pred[ok]
    return {"n": int(ok.sum()), "mae_mw": float((p - a).abs().mean()), "mape_pct": float(((p - a).abs() / a).mean() * 100),
            "bias_mw": float((p - a).mean())}


def split_pool(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(training pool, holdout). The holdout is local Dec 2022; the pool is everything else."""
    lo, hi = (pd.Timestamp(x, tz="America/New_York") for x in HOLDOUT)
    mask = (df["local_end"] > lo) & (df["local_end"] <= hi)   # hour-ending labels: (Dec 1 00:00, Jan 1 00:00] covers Dec 1-31
    return df[~mask].copy(), df[mask].copy()


def leave_one_winter_out(pool: pd.DataFrame, kind: str, ba: str) -> pd.DataFrame:
    """Per-winter MAE/MAPE: train on the pool minus that winter, test on that winter (the pool has no Dec 2022)."""
    mw, _ = BA_COLUMNS[ba]
    rows = []
    for w in sorted(pool["winter"].unique()):
        tr, te = pool[pool["winter"] != w], pool[pool["winter"] == w]
        fit = fit_model(kind, tr, ba)
        rows.append({"winter": int(w), **metrics(te[mw], fit.predict(te))})
    return pd.DataFrame(rows)


def combined_metrics(parts: dict) -> dict:
    """DUK + CPLE: sum predictions and actuals on hours where both BAs have a value."""
    a = parts["DUK"][0] + parts["CPLE"][0]
    p = parts["DUK"][1] + parts["CPLE"][1]
    return metrics(a, p)


def run_validation(df: pd.DataFrame) -> dict:
    """Full protocol. Selection uses CV on the pool only; the holdout is scored once at the end."""
    pool, hold = split_pool(df)
    assert not ((pool["local_end"] > pd.Timestamp(HOLDOUT[0], tz="America/New_York")) &
                (pool["local_end"] <= pd.Timestamp(HOLDOUT[1], tz="America/New_York"))).any()
    cv = {}
    for kind in ("linear", "boosted"):
        per = {ba: leave_one_winter_out(pool, kind, ba) for ba in BA_COLUMNS}
        cv[kind] = {ba: {"per_winter": per[ba].to_dict("records"), "mean_mape_pct": float(per[ba]["mape_pct"].mean()),
                         "mean_mae_mw": float(per[ba]["mae_mw"].mean())} for ba in BA_COLUMNS}
        cv[kind]["mean_mape_pct_both"] = float(np.mean([cv[kind][ba]["mean_mape_pct"] for ba in BA_COLUMNS]))
    chosen = "boosted" if cv["linear"]["mean_mape_pct_both"] - cv["boosted"]["mean_mape_pct_both"] >= CLOSE_PP else "linear"
    # ---- holdout, scored once, after the choice
    fits = {kind: {ba: fit_model(kind, pool, ba) for ba in BA_COLUMNS} for kind in ("linear", "boosted")}
    storm_lo, storm_hi = (pd.Timestamp(x, tz="America/New_York") for x in STORM)
    storm = (hold["local_end"] > storm_lo) & (hold["local_end"] <= storm_hi)
    holdout = {}
    for kind in ("linear", "boosted"):
        pred = {ba: fits[kind][ba].predict(hold) for ba in BA_COLUMNS}
        res = {}
        for ba, (mw, _) in BA_COLUMNS.items():
            res[ba] = {"all_dec_2022": metrics(hold[mw], pred[ba]), "dec_2022_excluding_storm_days": metrics(hold.loc[~storm, mw], pred[ba][~storm]),
                       "storm_days_dec_23_to_25": metrics(hold.loc[storm, mw], pred[ba][storm])}
        both = {ba: (hold[BA_COLUMNS[ba][0]], pred[ba]) for ba in BA_COLUMNS}
        res["DUK+CPLE"] = {"all_dec_2022": combined_metrics(both),
                           "dec_2022_excluding_storm_days": combined_metrics({k: (v[0][~storm], v[1][~storm]) for k, v in both.items()}),
                           "storm_days_dec_23_to_25": combined_metrics({k: (v[0][storm], v[1][storm]) for k, v in both.items()})}
        # the Elliott morning: local 07:00 (hour ending 07:00) on Dec 24, 2022
        target = pd.Timestamp("2022-12-24 07:00", tz="America/New_York")
        row = hold[hold["local_end"] == target]
        el = {}
        for ba, (mw, tcol) in BA_COLUMNS.items():
            a, p = (float(row[mw].iloc[0]) if len(row) else None), (float(pred[ba][row.index[0]]) if len(row) else None)
            el[ba] = {"actual_mw": a, "predicted_mw": p, "temp_f": float(row[tcol].iloc[0]) if len(row) else None,
                      "error_mw": None if a is None or p is None or np.isnan(p) else p - a,
                      "error_pct": None if a is None or p is None or np.isnan(p) else 100 * (p - a) / a}
        if all(el[b]["predicted_mw"] is not None and not np.isnan(el[b]["predicted_mw"]) for b in BA_COLUMNS):
            A, P = sum(el[b]["actual_mw"] for b in BA_COLUMNS), sum(el[b]["predicted_mw"] for b in BA_COLUMNS)
            el["DUK+CPLE"] = {"actual_mw": A, "predicted_mw": P, "error_mw": P - A, "error_pct": 100 * (P - A) / A}
        res["elliott_morning_0700_local"] = el
        holdout[kind] = res
    return {"chosen": chosen, "close_pp": CLOSE_PP, "cv": cv, "holdout": holdout, "n_pool": int(len(pool)), "n_holdout": int(len(hold)),
            "design": __doc__.split("\n\n")[0]}


def linear_spec(fit: Fit) -> dict:
    """JSON-serializable coefficients of a fitted linear model."""
    return {"ba": fit.ba, "intercept": float(fit.model.intercept_), "coefficients": dict(zip(fit.columns, map(float, fit.model.coef_)))}


def load_training() -> pd.DataFrame:
    """The frozen winter table (data/frozen/demand_training.csv.gz) with timezone-aware timestamps."""
    df = pd.read_csv(FROZEN / "demand_training.csv.gz", parse_dates=["utc_end"])
    df["utc_end"] = pd.to_datetime(df["utc_end"], utc=True)
    df["local_end"] = df["utc_end"].dt.tz_convert("America/New_York")
    return df


def build_and_write(df: pd.DataFrame | None = None) -> dict:
    """Run the protocol, write data/frozen/demand_validation.json and, for the chosen model, demand_model.json (linear only:
    coefficients; no scikit-learn needed at runtime). The shipped model is trained on the pool (Dec 2022 excluded)."""
    df = load_training() if df is None else df
    res = run_validation(df)
    pool, _ = split_pool(df)
    oofs = {k: oof_predictions(pool, k) for k in ("linear", "boosted")}
    res["cv_error_by_temperature"] = {k: cv_error_by_temperature(pool, k, oofs[k]) for k in oofs}  # diagnostic only
    res["cv_combined_duk_cple"] = {k: {"mape_pct": float(((o["pred"] - o["actual"]).abs() / o["actual"]).mean() * 100),
                                       "mae_mw": float((o["pred"] - o["actual"]).abs().mean()), "n": int(len(o))} for k, o in oofs.items()}
    FROZEN.mkdir(parents=True, exist_ok=True)
    (FROZEN / "demand_validation.json").write_text(json.dumps(res, indent=1, default=float))
    (FROZEN / "demand_panel.json").write_text(json.dumps(build_panel(df, res, pool, oofs[res["chosen"]]), indent=1))
    if res["chosen"] == "linear":
        spec = {"kind": "linear", "base_temp_f": BASE_F, "trend_origin": str(TREND_ORIGIN.date()), "trained_on": "all winter hours except Dec 2022",
                "n_train": res["n_pool"], "models": {ba: linear_spec(fit_model("linear", pool, ba)) for ba in BA_COLUMNS},
                "label": "modeled demand estimate; not a utility forecast; does not predict outages or available supply"}
        (FROZEN / "demand_model.json").write_text(json.dumps(spec, indent=1))
    return res


def oof_predictions(pool: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Out-of-fold DUK+CPLE predictions from leave-one-winter-out fits on the pool (rows where all inputs exist).
    Columns: actual, pred (MW, DUK+CPLE), t (mean of the two station temperatures, F)."""
    rows = []
    for w in sorted(pool["winter"].unique()):
        tr, te = pool[pool["winter"] != w], pool[pool["winter"] == w].copy()
        for ba in BA_COLUMNS:
            te[f"pred_{ba}"] = fit_model(kind, tr, ba).predict(te)
        rows.append(te)
    d = pd.concat(rows)
    d = d[d[["duk_mw", "cple_mw", "pred_DUK", "pred_CPLE", "kclt_f", "krdu_f"]].notna().all(axis=1)].copy()
    d["t"] = (d["kclt_f"] + d["krdu_f"]) / 2
    d["actual"], d["pred"] = d["duk_mw"] + d["cple_mw"], d["pred_DUK"] + d["pred_CPLE"]
    return d[["actual", "pred", "t"]]


def cv_error_by_temperature(pool: pd.DataFrame, kind: str, oof: pd.DataFrame | None = None) -> list[dict]:
    """Diagnostic only (does not feed model selection): out-of-fold percent error of DUK+CPLE demand by temperature bin,
    from leave-one-winter-out predictions on the pool. Temperature = mean of the two stations."""
    d = oof_predictions(pool, kind) if oof is None else oof.copy()
    d["bin"] = pd.cut(d["t"], [-50, 20, 25, 30, 35, 45, 100], labels=["below 20 F", "20-25 F", "25-30 F", "30-35 F", "35-45 F", "45 F and above"])
    out = []
    for b, g in d.groupby("bin", observed=True):
        out.append({"temp_bin": str(b), "hours": int(len(g)), "mean_pct_error": float(((g["pred"] - g["actual"]) / g["actual"]).mean() * 100),
                    "mape_pct": float(((g["pred"] - g["actual"]).abs() / g["actual"]).mean() * 100)})
    return out


PANEL_LABEL = "modeled demand estimate; not a utility forecast; does not predict outages or available supply"


def build_panel(df: pd.DataFrame, validation: dict, pool: pd.DataFrame, oof: pd.DataFrame) -> dict:
    """Precomputed data for the app's "Why forecasts aren't enough" panel. The app ships this file only (no scikit-learn):
    hourly actual vs predicted DUK+CPLE demand for Dec 22-26, 2022 from the chosen model trained WITHOUT Dec 2022."""
    kind = validation["chosen"]
    fits = {ba: fit_model(kind, pool, ba) for ba in BA_COLUMNS}
    lo, hi = (pd.Timestamp(x, tz="America/New_York") for x in ("2022-12-22", "2022-12-27"))
    win = df[(df["local_end"] > lo) & (df["local_end"] <= hi)].copy()
    full = {ba: fits[ba].predict(df) for ba in BA_COLUMNS}   # predict on the whole table so lagged features have their context
    pred = {ba: full[ba].loc[win.index] for ba in BA_COLUMNS}
    win["actual"] = win["duk_mw"] + win["cple_mw"]
    win["pred"] = pred["DUK"] + pred["CPLE"]
    series = [{"local_end": r.local_end.strftime("%Y-%m-%dT%H:%M:%S"), "actual_mw": None if np.isnan(r.actual) else float(r.actual),
               "predicted_mw": None if np.isnan(r.pred) else float(r.pred), "temp_f": None if np.isnan(r.kclt_f) else float(r.kclt_f)}
              for r in win.itertuples()]
    target = pd.Timestamp("2022-12-24 07:00", tz="America/New_York")
    row = win[win["local_end"] == target].iloc[0]
    gap_mw = float(row["pred"] - row["actual"])
    cv_mape = float(((oof["pred"] - oof["actual"]).abs() / oof["actual"]).mean() * 100)
    return {"label": PANEL_LABEL, "model": kind, "n_winters": int(pool["winter"].nunique()), "n_train_hours": int(len(pool)),
            "typical_mape_pct": cv_mape, "typical_mape_basis": "leave-one-winter-out cross-validation, DUK+CPLE, training pool only",
            "holdout_mape_pct": validation["holdout"][kind]["DUK+CPLE"]["all_dec_2022"]["mape_pct"],
            "elliott": {"local_end": target.strftime("%Y-%m-%dT%H:%M:%S"), "hour_label": "hour ending 07:00 (06:00-07:00) local",
                        "actual_mw": float(row["actual"]), "predicted_mw": float(row["pred"]), "gap_mw": gap_mw,
                        "gap_pct": 100 * gap_mw / float(row["actual"]), "temp_f": float(row["kclt_f"])},
            "series": series, "error_by_temperature": cv_error_by_temperature(pool, kind, oof)}


if __name__ == "__main__":
    r = build_and_write()
    print("chosen:", r["chosen"])
