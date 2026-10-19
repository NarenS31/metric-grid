"""Area-weighted join of tract attributes into zones (spec Phase 3.2).

Counts are summed with each tract contributing in proportion to the share of the *tract* that lies in the zone;
rates/percentiles/medians are area-weighted means over the overlapping tracts. Missing values are never zero-filled:
a sum with no data stays NaN and means skip NaN tracts (and are NaN if every overlapping tract is missing).
"""
import geopandas as gpd
import numpy as np
import pandas as pd

EQUAL_AREA = "EPSG:5070"


def area_weighted_join(zones: gpd.GeoDataFrame, tracts: gpd.GeoDataFrame, sum_cols: list[str], mean_cols: list[str],
                       zone_id: str = "zone_id", tract_id: str = "GEOID") -> pd.DataFrame:
    """Return a DataFrame indexed by zone_id with the sum_cols and mean_cols joined from tracts."""
    z = zones[[zone_id, "geometry"]].to_crs(EQUAL_AREA)
    t = tracts[[tract_id, "geometry", *sum_cols, *mean_cols]].to_crs(EQUAL_AREA)
    t["_tract_area"] = t.geometry.area
    ov = gpd.overlay(z, t, how="intersection", keep_geom_type=True)
    ov["_ov_area"] = ov.geometry.area
    ov = ov[ov["_ov_area"] > 1e-6]  # drop shared-edge slivers
    ov["_frac"] = ov["_ov_area"] / ov["_tract_area"]
    out = pd.DataFrame(index=sorted(z[zone_id]))
    out.index.name = zone_id
    g = ov.groupby(zone_id)
    for c in sum_cols:
        out[c] = (ov[c] * ov["_frac"]).groupby(ov[zone_id]).sum(min_count=1)
    for c in mean_cols:
        ok = ov[c].notna()
        num = (ov[c].where(ok, 0) * ov["_ov_area"]).groupby(ov[zone_id]).sum()
        den = ov["_ov_area"].where(ok, 0).groupby(ov[zone_id]).sum()
        out[c] = (num / den.replace(0, np.nan))
    return out
