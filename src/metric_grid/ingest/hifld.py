"""HIFLD Open access check.

Phase 1 uses this to decide between HIFLD Open and the OpenStreetMap fallback for critical facilities.
Phase 3 will reuse it for the Electric Substations layer.
"""
import requests

# Public ArcGIS REST root that hosted HIFLD Open layers.
HIFLD_ROOT = "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services?f=json"
WANTED = {
    "hospital": ["hospital"],
    "nursing_home": ["nursing"],
    "fire_station": ["fire_station", "firestation", "fire_stations"],
    "police": ["police", "law_enforcement"],
}


def probe_hifld(timeout: int = 30) -> dict:
    """Return {facility_type: [matching service names]} found in the HIFLD ArcGIS root listing."""
    resp = requests.get(HIFLD_ROOT, timeout=timeout)
    resp.raise_for_status()
    names = [s["name"].lower() for s in resp.json().get("services", [])]
    return {k: [n for n in names if any(p in n for p in pats)] for k, pats in WANTED.items()}
