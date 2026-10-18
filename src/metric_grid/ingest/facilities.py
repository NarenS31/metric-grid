"""Phase 1.5: critical facilities within the district.

HIFLD Open is tried first (see hifld.probe_hifld); when its layers are not reachable we do a one-time
OpenStreetMap Overpass pull. OSM coverage is incomplete, which the app states. Output: points with
facility_type, source, osm_id.
"""
import json

import geopandas as gpd
import requests
from shapely.geometry import Point

from metric_grid.ingest.common import PROCESSED, RAW

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# facility_type -> Overpass tag filters (union of filters per type)
OSM_FILTERS = {
    "hospital": ['["amenity"="hospital"]'],
    "nursing_home": ['["amenity"="nursing_home"]', '["social_facility"="nursing_home"]'],
    "water_treatment": ['["man_made"="water_works"]'],
    "wastewater_treatment": ['["man_made"="wastewater_plant"]'],
    "fire_station": ['["amenity"="fire_station"]'],
    "police": ['["amenity"="police"]'],
}


def overpass_query(bbox: tuple[float, float, float, float], filters: list[str]) -> str:
    """Build an Overpass QL query for nodes/ways/relations; bbox is (south, west, north, east)."""
    s, w, n, e = bbox
    parts = "".join(f"{kind}{f}({s},{w},{n},{e});" for f in filters for kind in ("node", "way", "relation"))
    return f"[out:json][timeout:180];({parts});out center tags;"


def elements_to_points(elements: list[dict], facility_type: str) -> list[dict]:
    """Turn Overpass elements into point records (nodes use lat/lon, ways/relations use center)."""
    rows = []
    for el in elements:
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        rows.append({
            "facility_type": facility_type,
            "name": tags.get("name"),
            "osm_id": f"{el['type']}/{el['id']}",
            "source": "OpenStreetMap via Overpass",
            "geometry": Point(lon, lat),
        })
    return rows


def pull_osm(district: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One-time Overpass pull per facility type over the district bbox, clipped to the district polygon."""
    minx, miny, maxx, maxy = district.to_crs(4326).total_bounds
    rows = []
    for ftype, filters in OSM_FILTERS.items():
        cache = RAW / "facilities" / f"osm_{ftype}.json"
        if not cache.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            r = requests.post(OVERPASS_URL, headers={"User-Agent": "metric-grid/0.1 (student research project)"}, data={"data": overpass_query((miny, minx, maxy, maxx), filters)}, timeout=240)
            r.raise_for_status()
            cache.write_text(r.text)
        rows += elements_to_points(json.loads(cache.read_text())["elements"], ftype)
    pts = gpd.GeoDataFrame(rows, crs=4326)
    pts = pts.drop_duplicates(subset=["facility_type", "osm_id"])
    inside = pts.within(district.to_crs(4326).geometry.union_all())
    return pts[inside].reset_index(drop=True)


def build_facilities(district: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Pull, clip and save facilities to data/raw/processed/facilities.geojson."""
    pts = pull_osm(district)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    pts.to_file(PROCESSED / "facilities.geojson", driver="GeoJSON")
    return pts
