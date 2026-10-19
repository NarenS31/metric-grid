"""`make data` entry point: run every ingest step that exists so far (network + .env keys required)."""
from metric_grid.config import load_config
from metric_grid.ingest import district, eia930, footprints, noaa, resstock


def build_all() -> None:
    """Phase 1 tables, then Phase 2 demand, temperature and NREL loads. Prints a one-line result per step."""
    cfg = load_config()
    j = district.build_phase1(cfg)
    print(f"tracts joined: {len(j)}")
    d = eia930.build_eia(cfg)
    r = eia930.reduction_ratios(eia930.group_demand(d, cfg), cfg)
    print(f"EIA-930 rows: {len(d)}; r per group: { {k: round(v['r'], 4) for k, v in r.items()} }")
    print(f"KCLT observations: {len(noaa.build_noaa(cfg))}")
    res, com = resstock.build_loads(cfg)
    print(f"footprint county-group rows: {len(footprints.build_footprints(cfg))}")
    footprints.build_footprints(cfg, rule="equal")  # sensitivity input for `make freeze`
    print(f"ResStock NC kW/unit: {res['kw_per_unit']:.3f}; ComStock counties: {len(com)}")


if __name__ == "__main__":
    build_all()
