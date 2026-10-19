# Changelog

- Phase 0: scaffold repo layout, config.yaml placeholders, README, docs stubs, Makefile stubs.
- Phase 0: add CLAUDE.md (from docs/SPEC.md), rebuild requirements.txt and .gitignore, create .venv (Python 3.11), add config loader and scaffold smoke test.
- Phase 1: ingest NC-08 tracts (TIGER 2024), ACS 2024 5-yr, SVI 2022, LODES 2023, OSM critical facilities; joined table; tests; `make data` runs Phase 1.
- Decision: protected facilities are hospital, nursing_home, water_treatment (config `facilities.protected_types`); fire, police and wastewater are display-only. Headroom counts recorded in ASSUMPTIONS.md.
- Phase 1: protected facility types set to hospital/nursing_home/water_treatment (fire, police, wastewater display-only) after tract-level protection check.
- Phase 2: EIA-930 DUK series + r=0.0479, NOAA KCLT (IEM fallback), ResStock NC per-unit and ComStock loads for the cold week via Range requests; tests.
- Phase 2b: two footprint groups (DEC: DUK; DEP: CPLE+CPLW) from EIA-861; per-group r from ORS/FERC-NERC (1,000 / 961 MW); district scaling D_NC08=1,686 MW, T_NC08=91.9 MW; demand figure (matplotlib); tests.
- Phase 3: tract zones (substation layer unavailable), option-(a) protected flags, L_i from two-utility scaling (sum L_i = D_NC08), `make freeze` to data/frozen/, zone map figure, app shell with offline render test.
- Phase 4.1-4.2: harm model (ICE-sourced costs) and two-plan optimizer with a shared target band replacing exact T* (spec change; exact-equality check showed ~5e12 feasible subsets but a 34 s solve); band sensitivity; district outline on maps; protected-zone constraint bug found and fixed by tests.
- Phase 4.3-4.4: sensitivity (19 settings, always/sometimes/never), scenarios 10/15/20%, alpha sweep + alpha_tradeoff.png, pre-solved grid and model outputs written at `make freeze` (spec deviation, approved), plain-language honesty summary.
- Optional county-share cap (default OFF) with tests and a sensitivity row; priority-list definition (baseline-cut zones spared in every alpha>0 setting) added to sensitivity outputs.
- Phase 4.5: Streamlit app (two pydeck maps, flip strip, priority list, zone detail, robustness card, methods drawer), offline blank map style, pre-solved grid with cap on/off (40 records), app tests, Playwright screenshots.
