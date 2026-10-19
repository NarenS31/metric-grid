"""pydeck maps: no basemap and no tile servers (offline); same view for both maps; district outline; hatched protected zones."""
import json
import math
import urllib.parse

import geopandas as gpd
import numpy as np
import pydeck as pdk
from shapely.geometry import LineString, mapping

LAV, VIO, CUT, NODATA = np.array([240, 235, 252]), np.array([70, 40, 170]), (22, 18, 31), (205, 200, 215)
INK = [28, 26, 36]


def svi_rgb(v) -> list[int]:
    """Lavender (low SVI) to deep violet (high SVI); lightness is monotonic so it also reads in greyscale."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return list(NODATA)
    t = float(min(max(v, 0.0), 1.0)) ** 0.9
    return [int(x) for x in LAV + (VIO - LAV) * t]


def view_state(district: gpd.GeoDataFrame, width_px: int = 640, height_px: int = 520) -> pdk.ViewState:
    """One fixed view that fits the district; both maps use it."""
    minx, miny, maxx, maxy = district.total_bounds
    lon_span, lat_span = maxx - minx, maxy - miny
    zoom_x = math.log2(360 * width_px / (256 * lon_span))
    zoom_y = math.log2(170 * height_px / (256 * lat_span * 1.15))
    return pdk.ViewState(longitude=(minx + maxx) / 2, latitude=(miny + maxy) / 2, zoom=min(zoom_x, zoom_y) - 0.15, pitch=0, bearing=0)


def hatch_features(zones: gpd.GeoDataFrame, spacing: float = 0.0045) -> list[dict]:
    """Diagonal hatch lines clipped to each protected zone (deck.gl has no fill patterns, so draw real lines)."""
    feats = []
    for g in zones.loc[zones["protected"], "geometry"]:
        minx, miny, maxx, maxy = g.bounds
        c = miny - maxx
        while c < maxy - minx:
            line = LineString([(minx - 1, minx - 1 + c), (maxx + 1, maxx + 1 + c)]).intersection(g)
            if not line.is_empty:
                feats.append({"type": "Feature", "properties": {}, "geometry": mapping(line)})
            c += spacing
    return feats


def zone_collection(zones: gpd.GeoDataFrame, cut_ids: set, plan_name: str) -> dict:
    """GeoJSON FeatureCollection with fill/line colours and tooltip text per zone for one plan."""
    feats = []
    for r in zones.itertuples():
        cut = r.zone_id in cut_ids
        status = "CUT" if cut else ("protected (never cut)" if r.protected else "kept on")
        feats.append({"type": "Feature", "geometry": mapping(r.geometry), "properties": {
            "fill": list(CUT) + [235] if cut else svi_rgb(r.RPL_THEMES) + [225],
            "line": [250, 247, 242] if not r.protected else INK, "lw": 1 if not r.protected else 1500,  # metres; min 1 px
            "zone": f"Zone {r.zone_id}", "county": r.COUNTY, "status": f"{status} ({plan_name})",
            "load": f"{r.L_mw:.1f} MW (modeled)", "svi": "n/a" if np.isnan(r.RPL_THEMES) else f"{r.RPL_THEMES:.2f}",
            "heat": "n/a" if np.isnan(r.share_electric_heat) else f"{r.share_electric_heat:.0%}", "hh": f"{r.occupied_units:,.0f}"}})
    return {"type": "FeatureCollection", "features": feats}


TOOLTIP = {"html": "<b>{zone}</b> · {county}<br/>{status}<br/>Est. load: {load}<br/>SVI: {svi}<br/>Electric heat: {heat}<br/>Households: {hh}",
           "style": {"backgroundColor": "#1C1A24", "color": "#FAF7F2", "fontSize": "12px", "fontFamily": "sans-serif"}}


# A style with no sources: Streamlit's frontend otherwise falls back to Carto tiles fetched from the internet (offline rule).
# Passed as a data: URL string because Streamlit's frontend calls string methods on mapStyle (a dict crashes the component).
_BLANK = {"version": 8, "name": "blank", "sources": {}, "layers": [
    {"id": "bg", "type": "background", "paint": {"background-color": "#FAF7F2"}}]}
BLANK_STYLE = "data:application/json;charset=utf-8," + urllib.parse.quote(json.dumps(_BLANK, separators=(",", ":")))


def build_deck(zone_fc: dict, hatch: list[dict], district_geojson: dict, vs: pdk.ViewState) -> pdk.Deck:
    """Layers: zones, hatch on protected zones, NC-08 outline. Map controller is off so both maps stay at the same extent."""
    # Widths: `line_width_min_pixels` sets the on-screen minimum; `get_line_width` is in metres (about 575 m per pixel at this zoom).
    # (line_width_units="pixels" renders huge in this deck.gl version, so it is not used.)
    zones = pdk.Layer("GeoJsonLayer", zone_fc, pickable=True, stroked=True, filled=True, get_fill_color="properties.fill",
                      get_line_color="properties.line", get_line_width="properties.lw", line_width_min_pixels=1,
                      auto_highlight=True, highlight_color=[91, 63, 214, 90])
    hatching = pdk.Layer("GeoJsonLayer", {"type": "FeatureCollection", "features": hatch}, stroked=True, filled=False,
                         get_line_color=INK + [200], get_line_width=1, line_width_min_pixels=1, pickable=False)
    outline = pdk.Layer("GeoJsonLayer", district_geojson, stroked=True, filled=False, get_line_color=[91, 63, 214, 255],
                        get_line_width=1200, line_width_min_pixels=2.5, pickable=False)
    return pdk.Deck(layers=[zones, hatching, outline], initial_view_state=vs, map_provider="carto", map_style=BLANK_STYLE,
                    tooltip=TOOLTIP, views=[pdk.View(type="MapView", controller=False)])
