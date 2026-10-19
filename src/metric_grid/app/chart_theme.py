"""One Vega-Lite look for every chart: transparent background, Inter labels, quiet grid lines, readable axes (palette from theme.py)."""
from metric_grid.app import theme

SANS = "Inter, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"
MONO = "IBM Plex Mono, ui-monospace, Menlo, Consolas, monospace"

CONFIG = {
    "background": None,
    "view": {"stroke": None},
    "font": SANS,
    "axis": {"labelColor": theme.MUTED, "titleColor": theme.MUTED, "labelFont": MONO, "titleFont": SANS, "labelFontSize": 11, "titleFontSize": 12,
             "titleFontWeight": 400, "gridColor": "#1E2B44", "gridDash": [], "domainColor": theme.BORDER, "tickColor": theme.BORDER,
             "titlePadding": 8, "labelPadding": 4},
    "legend": {"labelColor": theme.MUTED, "titleColor": theme.MUTED, "labelFont": SANS, "labelFontSize": 12},
    "title": {"color": theme.TEXT, "font": SANS, "fontSize": 13, "fontWeight": 500, "anchor": "start", "offset": 8, "subtitleColor": theme.MUTED,
              "subtitleFont": SANS, "subtitleFontSize": 12},
    "text": {"font": SANS},
}


def tip(*fields: tuple[str, str, str | None]) -> list[dict]:
    """Tooltip encoding: (field, title, d3 format or None) per row."""
    return [({"field": f, "title": t, "format": fmt} if fmt else {"field": f, "title": t}) | {"type": "quantitative" if fmt else "nominal"} for f, t, fmt in fields]
