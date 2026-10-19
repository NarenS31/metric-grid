"""Phase 3.1-3.2: analysis zones, attribute join, protected flags.

zone_mode "tract" (current): each zone is one census tract. The label everywhere is "census tract zone", never a
utility service boundary. zone_mode "substation" (Voronoi cells around public infrastructure points) is not
implemented because the substation layer was unavailable; see docs/ASSUMPTIONS.md.
"""
import geopandas as gpd
import pandas as pd

SUM_COLS = ["housing_units", "occupied_units", "owner_occupied", "renter_occupied", "heat_electricity",
            "heat_total_occupied", "total_pop_display", "jobs_total", "jobs_manufacturing", "jobs_retail", "jobs_health"]
MEAN_COLS = ["median_income", "RPL_THEMES", "RPL_THEME1", "RPL_THEME2", "RPL_THEME3", "RPL_THEME4"]
ZONE_NOTE = "census tract zone (not a utility service boundary)"


def tract_zones(joined: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One zone per tract. zone_id = 1..N in sorted-GEOID order (stable while the tract set is unchanged).

    Attributes are copied as-is (identity join). Tract geometry is kept whole, including the parts outside the district.
    """
    z = joined.sort_values("GEOID").reset_index(drop=True).copy()
    z.insert(0, "zone_id", range(1, len(z) + 1))
    z["zone_kind"] = "census tract"
    z["share_electric_heat"] = z["heat_electricity"] / z["occupied_units"].where(z["occupied_units"] > 0)
    z["svi_missing"] = z["RPL_THEMES"].isna()
    return z


def flag_protected(zones: gpd.GeoDataFrame, facilities: gpd.GeoDataFrame, protected_types: list[str]) -> gpd.GeoDataFrame:
    """Add protected (any facility of a protected type inside the zone), n_protected_facilities and per-type counts."""
    z = zones.copy()
    f = facilities.to_crs(z.crs)
    hit = gpd.sjoin(f, z[["zone_id", "geometry"]], predicate="within")
    counts = hit.groupby(["zone_id", "facility_type"]).size().unstack(fill_value=0)
    for ftype in sorted(f["facility_type"].unique()):
        z[f"n_{ftype}"] = z["zone_id"].map(counts[ftype] if ftype in counts else pd.Series(dtype=int)).fillna(0).astype(int)
    z["n_protected_facilities"] = sum((z[f"n_{t}"] for t in protected_types), start=pd.Series(0, index=z.index))
    z["protected"] = z["n_protected_facilities"] > 0
    return z


def build_zones(cfg: dict, joined: gpd.GeoDataFrame, facilities: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Zones for the configured mode with protected flags."""
    mode = cfg["zones"]["zone_mode"]
    if mode != "tract":
        raise NotImplementedError(f"zone_mode {mode!r} is not implemented; the substation layer was unavailable (see ASSUMPTIONS.md)")
    return flag_protected(tract_zones(joined), facilities, cfg["facilities"]["protected_types"])
