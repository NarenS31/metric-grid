# Changelog

- Phase 0: scaffold repo layout, config.yaml placeholders, README, docs stubs, Makefile stubs.
- Phase 0: add CLAUDE.md (from docs/SPEC.md), rebuild requirements.txt and .gitignore, create .venv (Python 3.11), add config loader and scaffold smoke test.
- Phase 1: ingest NC-08 tracts (TIGER 2024), ACS 2024 5-yr, SVI 2022, LODES 2023, OSM critical facilities; joined table; tests; `make data` runs Phase 1.
- Decision: protected facilities are hospital, nursing_home, water_treatment (config `facilities.protected_types`); fire, police and wastewater are display-only. Headroom counts recorded in ASSUMPTIONS.md.
- Phase 1: protected facility types set to hospital/nursing_home/water_treatment (fire, police, wastewater display-only) after tract-level protection check.
- Phase 2: EIA-930 DUK series + r=0.0479, NOAA KCLT (IEM fallback), ResStock NC per-unit and ComStock loads for the cold week via Range requests; tests.
