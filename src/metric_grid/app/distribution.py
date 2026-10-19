"""The distribution strip: where the vulnerability-aware plan falls among the N equivalent load-only plans, per metric.

One small Vega-Lite chart per metric: grey dots = the N load-only plans (deterministic vertical jitter so they do not overlap),
a dark diamond = the typical load-only plan shown on the left map, a large violet circle = the vulnerability-aware plan.
Shapes differ as well as colors, so the chart reads without color vision. Everything comes from the frozen plan set.
"""
from metric_grid.app import theme
from metric_grid.app.chart_theme import CONFIG

INK, VIOLET, GREY = theme.MW_ONLY, theme.VULN_AWARE, theme.DOTS   # typical megawatts-only plan, vulnerability-aware plan, the 200 plans

METRICS = [  # (key, title, axis format, unit note)
    ("electric_heat_households", "Electric-heat households cut", ",.0f", ""),
    ("h_human", "Vulnerability-weighted households", ",.0f", "households x SVI-based index"),
    ("h_econ", "Interruption cost (2013 dollars)", "$,.0f", "1 hour"),
    ("households", "Total households cut", ",.0f", ""),
]


def _jitter(i: int) -> float:
    return (i * 0.6180339887498949) % 1.0  # low-discrepancy sequence: even spread, no randomness


def strip_spec(values: list[float], typical: float, weighted: float, title: str, fmt: str) -> dict:
    """Vega-Lite spec for one metric: hover shows the formatted value and which plan the point is."""
    dots = [{"v": float(v), "y": _jitter(i), "who": "A megawatts-only plan"} for i, v in enumerate(values)]
    x = {"field": "v", "type": "quantitative", "title": None, "axis": {"format": fmt, "tickCount": 4}, "scale": {"zero": False, "nice": True}}
    y0 = {"field": "y", "type": "quantitative", "axis": None, "scale": {"domain": [-0.15, 1.15]}}
    tooltip = [{"field": "who", "type": "nominal", "title": "Plan"}, {"field": "v", "type": "quantitative", "title": title, "format": fmt}]
    return {
        "title": title, "height": 120, "config": CONFIG,
        "layer": [
            {"data": {"values": dots}, "mark": {"type": "circle", "color": GREY, "opacity": 0.55, "size": 38}, "encoding": {"x": x, "y": y0, "tooltip": tooltip}},
            {"data": {"values": [{"v": float(typical), "y": 0.5, "who": "Typical megawatts-only plan (left map)"}]},
             "mark": {"type": "point", "shape": "diamond", "filled": True, "color": INK, "size": 190, "stroke": theme.BG, "strokeWidth": 1.5},
             "encoding": {"x": {"field": "v", "type": "quantitative"}, "y": y0, "tooltip": tooltip}},
            {"data": {"values": [{"v": float(weighted), "y": 0.5, "who": "Vulnerability-aware plan"}]},
             "mark": {"type": "point", "shape": "circle", "filled": True, "color": VIOLET, "size": 230, "stroke": theme.BG, "strokeWidth": 1.5},
             "encoding": {"x": {"field": "v", "type": "quantitative"}, "y": y0, "tooltip": tooltip}},
        ]}


def specs(metrics: dict[str, list[float]], typical: dict[str, float], weighted: dict[str, float]) -> list[tuple[str, dict]]:
    """[(title, spec)] for the four metrics. `metrics[key]` = the N load-only values."""
    return [(title, strip_spec(metrics[k], typical[k], weighted[k], title, fmt)) for k, title, fmt, _ in METRICS]


def caption(dist: dict) -> str:
    """One line under the chart: how many of the N plans the vulnerability-aware plan beats on each metric (live numbers)."""
    n = dist["n"]
    return (f"Of {n} equivalent megawatts-only plans: {dist['electric_heat_households']['n_plans_more']} cut more electric-heat households, "
            f"{dist['h_human']['n_plans_more']} cut more vulnerability-weighted households, {dist['h_econ']['n_plans_more']} cost more, "
            f"and {dist['households']['n_plans_fewer']} cut fewer total households than the vulnerability-aware plan.")


def tradeoff_spec(sweep: list[dict]) -> dict:
    """Vega-Lite line chart from the frozen sweep over the slider: change vs the typical megawatts-only plan (calculated values)."""
    names = ["Vulnerability-weighted households", "Interruption cost (2013 dollars)", "Total households cut"]
    rows = []
    for r in sweep:
        if not r.get("solved", True):
            continue
        rows += [{"x": r["alpha"], "series": names[0], "pct": r["human_change_pct"]},
                 {"x": r["alpha"], "series": names[1], "pct": r["econ_change_pct"]},
                 {"x": r["alpha"], "series": names[2], "pct": r["households_change_pct"]}]
    scale = {"domain": names, "range": [VIOLET, theme.COST, theme.HOUSEHOLDS]}
    return {
        "height": 240, "data": {"values": rows}, "config": CONFIG,
        "layer": [
            {"mark": {"type": "rule", "color": theme.MUTED, "strokeWidth": 1}, "encoding": {"y": {"datum": 0}}},
            {"mark": {"type": "line", "point": {"filled": True, "size": 80}, "strokeWidth": 2.25},
             "encoding": {"x": {"field": "x", "type": "quantitative", "title": "Prioritize: Business cost  →  People at risk",
                                "axis": {"values": [0, 0.25, 0.5, 0.75, 1], "labelExpr": "datum.value == 0 ? 'Business cost' : datum.value == 1 ? 'People at risk' : ''", "grid": False}},
                          "y": {"field": "pct", "type": "quantitative", "title": "Change vs typical plan (%)", "axis": {"labelExpr": "datum.value > 0 ? '+' + datum.value : datum.value"}},
                          "color": {"field": "series", "type": "nominal", "title": None, "legend": None, "scale": scale},
                          "strokeDash": {"field": "series", "type": "nominal", "legend": None, "scale": {"domain": names, "range": [[1, 0], [1, 0], [6, 4]]}},
                          "tooltip": [{"field": "series", "type": "nominal", "title": "Measure"}, {"field": "x", "type": "quantitative", "title": "Slider position (0 = business cost, 1 = people at risk)", "format": ".2f"},
                                      {"field": "pct", "type": "quantitative", "title": "Change vs typical plan (%)", "format": "+.1f"}]}}]}
