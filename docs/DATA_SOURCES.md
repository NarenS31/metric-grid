# Data sources

Each entry gets: name, URL, dataset date/vintage, retrieval date, what it is used for, and whether it is observed, modeled, or a proxy. Filled in as each phase lands.

| Source | Used for | URL | Vintage | Status |
|---|---|---|---|---|
| Census TIGER/Line 2024 (cd119, tracts) | NC-08 boundary, tracts | https://www2.census.gov/geo/tiger/TIGER2024/CD/tl_2024_37_cd119.zip ; https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_37_tract.zip | 2024 | downloaded 2026-10-18 |
| Census ACS 5-year (B25001, B25003, B25034, B25040, B19013, B01001) | housing units, year built, heating fuel, income, tenure | https://api.census.gov/data/2024/acs/acs5 | 2020-2024 | downloaded 2026-10-18 |
| CDC/ATSDR SVI 2022 | vulnerability percentiles | https://svi.cdc.gov/Documents/Data/2022/csv/states/NorthCarolina.csv | 2022 | downloaded 2026-10-18 |
| LEHD LODES8 WAC (NC, JT00) | jobs by sector | https://lehd.ces.census.gov/data/lodes/LODES8/nc/wac/nc_wac_S000_JT00_2023.csv.gz | 2023 | downloaded 2026-10-18 |
| OpenStreetMap via Overpass (HIFLD Open unavailable, see ASSUMPTIONS.md) | critical facilities | https://overpass-api.de/api/interpreter | pulled 2026-10-18 | downloaded; incomplete coverage |
| EIA-930 region-data, respondents DUK (Duke Energy Carolinas), CPLE and CPLW (Duke Energy Progress East/West), type D | regional hourly demand | https://api.eia.gov/v2/electricity/rto/region-data/data/ | 2022-12-22..26 | downloaded 2026-10-18 |
| SC Office of Regulatory Staff, "Inspection and Examination Report of DEC and DEP December 2022 Winter Storm Outages and Blackouts" | DEC shed 400 MW directed 6:14 AM, maintained at 1,000 MW; DEP requests 600/200/50/~111 MW (sum 961); p.39 printed (PDF p.49) | https://ors.sc.gov/sites/scors/files/Documents/News%20Archive/Inspection%20and%20Examination%20Report%20of%20DEC%20and%20DEP%20December%202022%20Winter%20Storm%20Outages%20and%20Blackouts.pdf | 2023 | downloaded 2026-10-18; quotes verified |
| FERC-NERC-Regional Entity staff report, "Inquiry into Bulk-Power System Operations During December 2022 Winter Storm Elliott" (Nov 2023) | DEC 400 MW (6:27) -> 1,000 MW (7:10); DEP 600 MW (6:25) -> 800 MW (7:10) -> max 961 MW by 7:56; PDF p.71 | https://www.ferc.gov/sites/default/files/2024-02/24_Winter-Storm_Elliot_0207_UPDATE.pdf | Nov 2023 | downloaded 2026-10-18; quotes verified |
| EIA Form 861 (data year 2024): Service_Territory, Sales_Ult_Cust (BA Code, customers) | county -> utility/BA assignment; customer counts for shared-county split | https://www.eia.gov/electricity/data/eia861/zip/f8612024.zip | 2024 | downloaded 2026-10-18 |
| NREL End-Use Load Profiles: ResStock AMY2018 release 2 (NC state), ComStock AMY2018 release 2 (NC state, counties) | load per housing unit / per job | https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/ | AMY2018, release 2 (2024) | cold week downloaded 2026-10-18 |
| KCLT ASOS hourly temperature via Iowa Environmental Mesonet (NOAA NCEI was unavailable) | display only | https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py | 2022-12-23..25 | downloaded 2026-10-18 |
| HIFLD Electric Substations | zone generating points | TBD Phase 3 | TBD | pending |
| LBNL ICE Calculator 2.0 | interruption cost per sector | TBD Phase 4 | TBD | pending |
