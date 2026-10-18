"""Phase 1.1: district boundary and tracts from Census TIGER/Line.

Tract rule (spec): keep a tract if its centroid is inside the district OR >= 50% of its area overlaps it.
"""
import geopandas as gpd

from metric_grid.config import load_config
from metric_grid.ingest.common import PROCESSED, RAW, download

TIGER_BASE = "https://www2.census.gov/geo/tiger/TIGER{year}"
EQUAL_AREA = "EPSG:5070"  # CONUS Albers, for area math only


def load_district(cfg: dict) -> gpd.GeoDataFrame:
    """Download the state's cd119 file and return the single configured district (EPSG:4269)."""
    d = cfg["district"]
    fips, cd, year = d["state_fips"], d["district"], d["tiger_year"]
    # The 2024 release publishes cd119 per state (there is no national file), so we fetch the state file.
    url = f"{TIGER_BASE.format(year=year)}/CD/tl_{year}_{fips}_cd119.zip"
    path = download(url, RAW / "tiger" / f"tl_{year}_{fips}_cd119.zip")
    gdf = gpd.read_file(path)
    out = gdf[(gdf["STATEFP"] == fips) & (gdf["CD119FP"] == cd)]
    if len(out) != 1:
        raise RuntimeError(f"expected exactly 1 district for state {fips} CD {cd}, found {len(out)}")
    return out


def select_tracts(tracts: gpd.GeoDataFrame, district: gpd.GeoDataFrame, min_overlap: float) -> gpd.GeoDataFrame:
    """Keep tracts whose centroid is inside the district or whose area overlap fraction >= min_overlap."""
    t = tracts.to_crs(EQUAL_AREA)
    dist_geom = district.to_crs(EQUAL_AREA).geometry.union_all()
    centroid_in = t.geometry.centroid.within(dist_geom)
    overlap_frac = t.geometry.intersection(dist_geom).area / t.geometry.area
    keep = centroid_in | (overlap_frac >= min_overlap)
    return tracts.loc[keep.values].copy()


def build_tracts(cfg: dict | None = None) -> gpd.GeoDataFrame:
    """Full Phase 1.1: returns district tracts and writes GeoJSON files to data/raw/processed/."""
    cfg = cfg or load_config()
    d = cfg["district"]
    fips, year = d["state_fips"], d["tiger_year"]
    district = load_district(cfg)
    url = f"{TIGER_BASE.format(year=year)}/TRACT/tl_{year}_{fips}_tract.zip"
    tracts = gpd.read_file(download(url, RAW / "tiger" / f"tl_{year}_{fips}_tract.zip"))
    kept = select_tracts(tracts, district, d["tract_min_overlap"])
    kept = kept[["GEOID", "STATEFP", "COUNTYFP", "TRACTCE", "ALAND", "AWATER", "geometry"]].sort_values("GEOID")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    district.to_crs(4326).to_file(PROCESSED / "district.geojson", driver="GeoJSON")
    kept.to_crs(4326).to_file(PROCESSED / "tracts.geojson", driver="GeoJSON")
    return kept


def load_tracts() -> gpd.GeoDataFrame:
    """Read the saved district tracts (WGS84)."""
    return gpd.read_file(PROCESSED / "tracts.geojson")


def join_attributes(tracts: gpd.GeoDataFrame, acs, svi, lodes) -> gpd.GeoDataFrame:
    """Left-join ACS, SVI and LODES onto district tracts by GEOID.

    Raises if any join key is duplicated (would silently multiply rows). Missing values stay NaN.
    LODES tracts absent from WAC are left NaN here; the caller decides how to treat them (see ASSUMPTIONS.md).
    """
    for name, df in (("acs", acs), ("svi", svi), ("lodes", lodes)):
        if df["GEOID"].duplicated().any():
            raise ValueError(f"duplicate GEOID in {name}")
    n = len(tracts)
    out = tracts.merge(acs, on="GEOID", how="left").merge(svi, on="GEOID", how="left").merge(lodes, on="GEOID", how="left")
    if len(out) != n:
        raise ValueError("join changed the number of tracts")
    return out


def build_phase1(cfg: dict | None = None) -> gpd.GeoDataFrame:
    """Run all Phase 1 ingests, join them, save data/raw/processed/tracts_joined.geojson, return the table."""
    from metric_grid.ingest import acs, facilities, lodes, svi  # local imports keep module import light

    cfg = cfg or load_config()
    tracts = build_tracts(cfg)
    joined = join_attributes(tracts, acs.build_acs(cfg), svi.build_svi(cfg), lodes.build_lodes(cfg=cfg))
    joined.to_crs(4326).to_file(PROCESSED / "tracts_joined.geojson", driver="GeoJSON")
    facilities.build_facilities(load_district(cfg))
    return joined


if __name__ == "__main__":
    j = build_phase1()
    print(f"tracts: {len(j)}")
