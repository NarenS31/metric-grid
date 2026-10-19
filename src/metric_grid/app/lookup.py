"""Fixed demo-location lookup: which zone (census tract) a public building sits in, and its status under both plans."""
import geopandas as gpd
from shapely.geometry import Point

from metric_grid.model.optimizer import PairResult


def locate(zones: gpd.GeoDataFrame, lat: float, lon: float) -> int | None:
    """zone_id of the zone containing the point, or None if it is outside every zone."""
    hit = zones[zones.contains(Point(lon, lat))]
    return int(hit["zone_id"].iloc[0]) if len(hit) else None


def status(zones: gpd.GeoDataFrame, zone_id: int | None, plan) -> str:
    """'CUT', 'kept on' or 'protected, never cut' for a zone under one plan."""
    if zone_id is None:
        return "outside NC-08 zones"
    if zone_id in plan.zone_ids:
        return "CUT"
    return "protected, never cut" if bool(zones.loc[zones["zone_id"] == zone_id, "protected"].iloc[0]) else "kept on"


def lookup_rows(zones: gpd.GeoDataFrame, locations: list[dict], r: PairResult) -> list[dict]:
    """One row per configured location: zone, county and status under the baseline and the vulnerability-aware plan."""
    rows = []
    for loc in locations:
        zid = locate(zones, loc["lat"], loc["lon"])
        rows.append({"label": loc["label"], "county": loc["county"], "zone_id": zid,
                     "baseline": status(zones, zid, r.baseline), "weighted": status(zones, zid, r.weighted)})
    return rows
