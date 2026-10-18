# Data sources

Each entry gets: name, URL, dataset date/vintage, retrieval date, what it is used for, and whether it is observed, modeled, or a proxy. Filled in as each phase lands.

| Source | Used for | URL | Vintage | Status |
|---|---|---|---|---|
| Census TIGER/Line 2024 (cd119, tracts) | NC-08 boundary, tracts | https://www2.census.gov/geo/tiger/TIGER2024/CD/tl_2024_37_cd119.zip ; https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_37_tract.zip | 2024 | downloaded 2026-10-18 |
| Census ACS 5-year (B25001, B25003, B25034, B25040, B19013, B01001) | housing units, year built, heating fuel, income, tenure | https://api.census.gov/data/2024/acs/acs5 | 2020-2024 | downloaded 2026-10-18 |
| CDC/ATSDR SVI 2022 | vulnerability percentiles | https://svi.cdc.gov/Documents/Data/2022/csv/states/NorthCarolina.csv | 2022 | downloaded 2026-10-18 |
| LEHD LODES8 WAC (NC, JT00) | jobs by sector | https://lehd.ces.census.gov/data/lodes/LODES8/nc/wac/nc_wac_S000_JT00_2023.csv.gz | 2023 | downloaded 2026-10-18 |
| OpenStreetMap via Overpass (HIFLD Open unavailable, see ASSUMPTIONS.md) | critical facilities | https://overpass-api.de/api/interpreter | pulled 2026-10-18 | downloaded; incomplete coverage |
| EIA-930 (DUK) | regional hourly demand | TBD Phase 2 | 2022-12 | pending |
| NCUC Docket M-100 Sub 163 | ~1,000 MW shed, 06:14 start | TBD Phase 2 | 2022-2023 | pending |
| NREL ResStock / ComStock | load-shape weights | TBD Phase 2 | AMY2018 | pending |
| NOAA KCLT | display-only temperature | TBD Phase 2 | 2022-12 | pending |
| HIFLD Electric Substations | zone generating points | TBD Phase 3 | TBD | pending |
| LBNL ICE Calculator 2.0 | interruption cost per sector | TBD Phase 4 | TBD | pending |
