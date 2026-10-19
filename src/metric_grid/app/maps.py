"""Maps as inline SVG: no WebGL, no JavaScript, no basemap, no tile servers, no external requests (works offline in any browser).

Zones are census tracts projected to a flat plane (x scaled by cos of the district's mid-latitude); geometry is simplified a little
for page weight (tolerance about 150 m, well below the size of a tract). Hover text is the SVG <title> of each zone.
"""
import html
import math

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry

WIDTH = 1000.0          # viewBox width; height follows the district's aspect ratio
SIMPLIFY_DEG = 0.0015
from metric_grid.app import theme

INK = "#C9D3E6"            # hatch lines
CUT_COLOR = theme.AMBER    # one colour for "cut" on both maps; which plan is which comes from the map titles
KEPT_LIGHT, KEPT_DARK, NODATA = np.array([30, 44, 72]), np.array([80, 104, 150]), "#2A2F3D"


def kept_rgb(svi) -> str:
    """Dark slate (low SVI) to a lighter blue-slate (high SVI); lightness is monotonic, so it also reads in greyscale."""
    if svi is None or (isinstance(svi, float) and math.isnan(svi)):
        return NODATA
    t = float(min(max(svi, 0.0), 1.0))
    r, g, b = (int(x) for x in KEPT_LIGHT + (KEPT_DARK - KEPT_LIGHT) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


class Projector:
    """lon/lat -> SVG x/y for one district; one projector shared by both maps so they have the same extent."""

    def __init__(self, district: gpd.GeoDataFrame, pad: float = 0.01):
        minx, miny, maxx, maxy = district.total_bounds
        self.minx, self.maxy = minx - pad, maxy + pad
        self.cos = math.cos(math.radians((miny + maxy) / 2))
        self.scale = WIDTH / ((maxx - minx + 2 * pad) * self.cos)
        self.height = round((maxy - miny + 2 * pad) * self.scale, 1)

    def xy(self, lon: float, lat: float) -> tuple[float, float]:
        return (lon - self.minx) * self.cos * self.scale, (self.maxy - lat) * self.scale

    def path(self, geom: BaseGeometry, simplify: float = SIMPLIFY_DEG) -> str:
        """SVG path data for a (multi)polygon or (multi)line, one decimal place."""
        g = geom.simplify(simplify, preserve_topology=True) if simplify else geom
        parts = []
        for part in getattr(g, "geoms", [g]):
            rings = [part.exterior, *part.interiors] if part.geom_type == "Polygon" else [part]
            for ring in rings:
                pts = [self.xy(x, y) for x, y in ring.coords]
                parts.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + ("Z" if part.geom_type == "Polygon" else ""))
        return "".join(parts)


def hatch_geometry(zones: gpd.GeoDataFrame, spacing: float = 0.0045) -> list[BaseGeometry]:
    """Diagonal hatch lines clipped to each protected zone (drawn as real lines, so the hatching survives any renderer)."""
    out = []
    for g in zones.loc[zones["protected"], "geometry"]:
        minx, miny, maxx, maxy = g.bounds
        c = miny - maxx
        while c < maxy - minx:
            line = LineString([(minx - 1, minx - 1 + c), (maxx + 1, maxx + 1 + c)]).intersection(g)
            if not line.is_empty:
                out.append(line)
            c += spacing
    return out


def static_layers(zones: gpd.GeoDataFrame, district: gpd.GeoDataFrame) -> dict:
    """Everything that does not depend on the plan, computed once: projector, zone paths, hatch path, district outline path."""
    proj = Projector(district)
    return {"proj": proj, "zone_paths": {int(r.zone_id): proj.path(r.geometry) for r in zones.itertuples()},
            "hatch": "".join(proj.path(g, simplify=0) for g in hatch_geometry(zones)),
            "outline": "".join(proj.path(g) for g in district.geometry)}


def map_svg(zones: gpd.GeoDataFrame, layers: dict, cut_ids: set, plan_name: str, map_id: str,
            freq: dict | None = None, n_plans: int = 0, label: str = "") -> str:
    """One map. Cut zones solid `CUT_COLOR` (same on both maps); kept-on zones light grey (deeper = more vulnerable); protected zones carry a hatch."""
    paths = []
    for r in zones.itertuples():
        zid = int(r.zone_id)
        cut = zid in cut_ids
        status = "CUT" if cut else ("protected, never cut" if r.protected else "kept on")
        svi = "n/a" if np.isnan(r.RPL_THEMES) else f"{r.RPL_THEMES:.2f}"
        heat = "n/a" if np.isnan(r.share_electric_heat) else f"{r.share_electric_heat:.0%}"
        tip = [f"Zone {zid} · {r.COUNTY}", f"{status} ({plan_name})"]
        if freq is not None and n_plans:
            tip.append(f"cut in {freq.get(zid, 0)} of {n_plans} megawatts-only plans")
        tip.append(f"Est. load {r.L_mw:.1f} MW (modeled) · SVI {svi} · electric heat {heat} · {r.occupied_units:,.0f} households")
        fill = CUT_COLOR if cut else kept_rgb(r.RPL_THEMES)
        paths.append(f'<path d="{layers["zone_paths"][zid]}" fill="{fill}" stroke="#0B1020" stroke-width="1" '
                     f'stroke-linejoin="round"><title>{html.escape(chr(10).join(tip))}</title></path>')
    hatch = f'<path d="{layers["hatch"]}" fill="none" stroke="{INK}" stroke-width="0.8" stroke-opacity="0.6" pointer-events="none"/>'
    outline = f'<path d="{layers["outline"]}" fill="none" stroke="{theme.TEAL}" stroke-width="2" stroke-linejoin="round" pointer-events="none"/>'
    h = layers["proj"].height
    return (f'<svg class="map" id="{map_id}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH:.0f} {h}" role="img" '
            f'aria-label="{html.escape(label)}" preserveAspectRatio="xMidYMid meet"><rect width="{WIDTH:.0f}" height="{h}" fill="{theme.SURFACE}"/>'
            + "".join(paths) + hatch + outline + "</svg>")
