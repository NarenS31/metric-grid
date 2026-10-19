"""The "Why forecasts aren't enough" panel: text and chart spec built from the precomputed demand_panel.json.

Runtime needs only the JSON (no scikit-learn). Every number comes from that file or from the frozen constants.
"""
from metric_grid.app import theme
from metric_grid.app.chart_theme import CONFIG

INK, VIOLET, ORANGE = theme.TEXT, theme.VULN_AWARE, theme.AMBER   # observed demand, model prediction, the Elliott morning


def total_shed_mw(consts: dict) -> float:
    """Sum of the two utilities' maximum firm load shed (MW), from the frozen constants (r x demand = shed)."""
    return sum(g["r"] * g["D_group_mw"] for g in consts["groups"].values())


def sentence(panel: dict, shed_mw: float) -> str:
    """Plain sentence from live numbers. The shed wording is deliberately careful: the ~1,961 MW is the maximum reached
    (by 7:56 a.m.), not the amount excluded from the hour ending 07:00, when the shed was still ramping up."""
    e = panel["elliott"]
    direction = "under-predicted" if e["gap_mw"] < 0 else "over-predicted"
    return (f"Trained on {panel['n_winters']} winters (Elliott held out), this model is typically within "
            f"{panel['typical_mape_pct']:.1f}% of actual demand. In the hour ending 07:00 (06:00-07:00) on Dec 24, 2022 it "
            f"{direction} by {abs(e['gap_pct']):.1f}% ({abs(e['gap_mw']):,.0f} MW). Observed demand already excludes the load that "
            f"was being shed (up to about {shed_mw:,.0f} MW by 7:56 a.m.; less during this hour, while the shed was still "
            f"ramping up), so the true shortfall was larger.")


def chart_spec(panel: dict) -> dict:
    """Vega-Lite spec: predicted vs actual DUK+CPLE demand for Dec 22-26, 2022 with the Elliott morning marked."""
    rows = []
    for r in panel["series"]:
        if r["actual_mw"] is not None:
            rows.append({"t": r["local_end"], "series": "Actual (observed)", "mw": r["actual_mw"]})
        if r["predicted_mw"] is not None:
            rows.append({"t": r["local_end"], "series": "Model prediction", "mw": r["predicted_mw"]})
    e = panel["elliott"]
    color = {"field": "series", "type": "nominal", "title": None,
             "scale": {"domain": ["Actual (observed)", "Model prediction"], "range": [INK, VIOLET]}, "legend": {"orient": "top"}}
    x = {"field": "t", "type": "temporal", "title": "Local time (each hour labelled by its end)", "axis": {"format": "%b %d %H:%M", "labelAngle": -30, "grid": False}}
    vals = [r["mw"] for r in rows]
    top = max(vals)
    y = {"field": "mw", "type": "quantitative", "title": "DUK + CPLE demand (MW)",
         "scale": {"zero": False, "domain": [int(min(vals) // 1000 * 1000 - 1000), int(top // 1000 * 1000 + 5000)]}}
    label_y = top + 2300   # headroom above the peak so the label never sits on the lines
    return {
        "height": 380, "config": CONFIG,
        "data": {"values": rows},
        "layer": [
            {"mark": {"type": "line", "strokeWidth": 2.2}, "encoding": {"x": x, "y": y, "color": color,
                                                                       "tooltip": [{"field": "series", "type": "nominal", "title": "Series"},
                                                                                   {"field": "t", "type": "temporal", "title": "Hour ending", "format": "%b %d, %H:%M"},
                                                                                   {"field": "mw", "type": "quantitative", "title": "Demand (MW)", "format": ",.0f"}],
                                                                       "strokeDash": {"field": "series", "type": "nominal", "legend": None,
                                                                                      "scale": {"domain": ["Actual (observed)", "Model prediction"], "range": [[1, 0], [6, 3]]}}}},
            {"data": {"values": [{"t": e["local_end"]}]}, "mark": {"type": "rule", "color": ORANGE, "strokeWidth": 1.5, "strokeDash": [2, 3]},
             "encoding": {"x": {"field": "t", "type": "temporal"}}},
            {"data": {"values": [{"t": e["local_end"], "series": "Actual (observed)", "mw": e["actual_mw"]},
                                 {"t": e["local_end"], "series": "Model prediction", "mw": e["predicted_mw"]}]},
             "mark": {"type": "point", "filled": True, "size": 110}, "encoding": {"x": {"field": "t", "type": "temporal"}, "y": y, "color": color}},
            {"data": {"values": [{"t": e["local_end"], "mw": label_y, "label": f"Elliott morning: actual {e['actual_mw']:,.0f} MW, "
                                                                             f"model {e['predicted_mw']:,.0f} MW ({e['gap_pct']:+.1f}%)"}]},
             "mark": {"type": "text", "align": "center", "dy": -4, "color": ORANGE, "fontWeight": "bold", "fontSize": 11},
             "encoding": {"x": {"field": "t", "type": "temporal"}, "y": {"field": "mw", "type": "quantitative"}, "text": {"field": "label"}}},
        ]}


def temperature_table(panel: dict) -> str:
    """HTML table: out-of-fold error by temperature band (training data only), highlighting how few cold hours there are."""
    rows = "".join(f"<tr><td>{b['temp_bin'].replace(' F', ' °F')}</td><td>{b['hours']:,}</td><td>{b['mean_pct_error']:+.1f}%</td></tr>"
                   for b in panel["error_by_temperature"])
    return ("<table class='t'><tr><th>Temperature</th><th>Training hours</th><th>Mean error</th></tr>" + rows + "</table>")


def coldest_note(panel: dict) -> str:
    cold = panel["error_by_temperature"][0]
    return (f"Below 20 °F there are only {cold['hours']:,} training hours, and the model is biased low there "
            f"({cold['mean_pct_error']:+.1f}% on average). The Elliott morning was about {panel['elliott']['temp_f']:.0f} °F.")
