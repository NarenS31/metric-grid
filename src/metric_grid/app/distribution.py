"""The distribution strip: where the vulnerability-aware plan falls among the N equivalent load-only plans, per metric.

One small Vega-Lite chart per metric: grey dots = the N load-only plans (deterministic vertical jitter so they do not overlap),
a dark diamond = the typical load-only plan shown on the left map, a large violet circle = the vulnerability-aware plan.
Shapes differ as well as colors, so the chart reads without color vision. Everything comes from the frozen plan set.
"""
INK, VIOLET, GREY = "#1C1A24", "#5B3FD6", "#8D8A99"

METRICS = [  # (key, title, axis format, unit note)
    ("electric_heat_households", "Electric-heat households cut", ",.0f", ""),
    ("h_human", "Vulnerability-weighted households", ",.0f", "households x SVI-based index"),
    ("h_econ", "Interruption cost (2013 dollars)", "$,.0f", "1 hour"),
    ("households", "Total households cut", ",.0f", ""),
]


def _jitter(i: int) -> float:
    return (i * 0.6180339887498949) % 1.0  # low-discrepancy sequence: even spread, no randomness


def strip_spec(values: list[float], typical: float, weighted: float, title: str, fmt: str) -> dict:
    """Vega-Lite spec for one metric."""
    dots = [{"v": float(v), "y": _jitter(i)} for i, v in enumerate(values)]
    x = {"field": "v", "type": "quantitative", "title": title, "axis": {"format": fmt, "tickCount": 4, "labelColor": INK, "titleColor": INK, "titleFontSize": 11},
         "scale": {"zero": False, "nice": True}}
    y0 = {"field": "y", "type": "quantitative", "axis": None, "scale": {"domain": [-0.15, 1.15]}}
    mark_y = {"field": "y", "type": "quantitative", "axis": None, "scale": {"domain": [-0.15, 1.15]}}
    return {
        "height": 120, "background": None, "config": {"view": {"stroke": None}},
        "layer": [
            {"data": {"values": dots}, "mark": {"type": "circle", "color": GREY, "opacity": 0.55, "size": 38}, "encoding": {"x": x, "y": y0}},
            {"data": {"values": [{"v": float(typical), "y": 0.5}]},
             "mark": {"type": "point", "shape": "diamond", "filled": True, "color": INK, "size": 190, "stroke": "white", "strokeWidth": 1.5},
             "encoding": {"x": {"field": "v", "type": "quantitative"}, "y": mark_y}},
            {"data": {"values": [{"v": float(weighted), "y": 0.5}]},
             "mark": {"type": "point", "shape": "circle", "filled": True, "color": VIOLET, "size": 230, "stroke": "white", "strokeWidth": 1.5},
             "encoding": {"x": {"field": "v", "type": "quantitative"}, "y": mark_y}},
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
    """Vega-Lite line chart from the frozen alpha sweep (plain axis, no Greek letters): change vs the typical megawatts-only plan,
    with the households line included so the 'more households' fact is on the chart."""
    rows = []
    for r in sweep:
        if not r.get("solved", True):
            continue
        rows += [{"x": r["alpha"], "series": "Vulnerability-weighted households", "pct": r["human_change_pct"]},
                 {"x": r["alpha"], "series": "Interruption cost (2013 dollars)", "pct": r["econ_change_pct"]},
                 {"x": r["alpha"], "series": "Total households cut", "pct": r["households_change_pct"]}]
    return {
        "height": 240, "background": None, "data": {"values": rows}, "config": {"view": {"stroke": None}, "axis": {"labelColor": INK, "titleColor": INK}},
        "layer": [
            {"mark": {"type": "rule", "color": INK, "strokeWidth": 1}, "encoding": {"y": {"datum": 0}}},
            {"mark": {"type": "line", "point": {"filled": True, "size": 80}, "strokeWidth": 2.5},
             "encoding": {"x": {"field": "x", "type": "quantitative", "title": "Prioritize: Business cost  →  People at risk",
                                "axis": {"values": [0, 0.25, 0.5, 0.75, 1], "labelExpr": "datum.value == 0 ? 'Business cost' : datum.value == 1 ? 'People at risk' : ''"}},
                          "y": {"field": "pct", "type": "quantitative", "title": "Change vs typical plan (%)"},
                          "color": {"field": "series", "type": "nominal", "title": None, "legend": None,
                                    "scale": {"domain": ["Vulnerability-weighted households", "Interruption cost (2013 dollars)", "Total households cut"],
                                              "range": [VIOLET, "#D98E04", GREY]}},
                          "strokeDash": {"field": "series", "type": "nominal", "legend": None,
                                         "scale": {"domain": ["Vulnerability-weighted households", "Interruption cost (2013 dollars)", "Total households cut"],
                                                   "range": [[1, 0], [1, 0], [6, 4]]}}}}]}
