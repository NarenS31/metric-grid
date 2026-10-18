"""`make data` entry point: run every ingest step that exists so far (network + .env keys required)."""
from metric_grid.config import load_config
from metric_grid.ingest import district, eia930, noaa, resstock


def build_all() -> None:
    """Phase 1 tables, then Phase 2 demand, temperature and NREL loads. Prints a one-line result per step."""
    cfg = load_config()
    j = district.build_phase1(cfg)
    print(f"tracts joined: {len(j)}")
    d = eia930.build_eia(cfg)
    print(f"EIA-930 hours: {len(d)}; r = {eia930.reduction_ratio(d, cfg)['r']:.4f}")
    print(f"KCLT observations: {len(noaa.build_noaa(cfg))}")
    res, com = resstock.build_loads(cfg)
    print(f"ResStock NC kW/unit: {res['kw_per_unit']:.3f}; ComStock counties: {len(com)}")


if __name__ == "__main__":
    build_all()
