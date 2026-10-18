"""County -> footprint group assignment from EIA Form 861, plus county housing units and jobs for the weights.

Rule (documented in docs/ASSUMPTIONS.md): a county belongs to a group if any utility serving it (EIA-861
Service_Territory) is the group's own utility OR has the group's BA Code in Sales_Ult_Cust. So co-ops and
municipals inside a footprint count as that BA's load. A county matching several groups is split between them
(config `shared_county_rule`, default `customer_spread`) and flagged `shared`; "equal" and the 0/1 extremes are
run as sensitivity cases. EIA-861 gives customers per utility and state, not per county, so customer_spread
is an approximation: each utility's customers are spread over the counties it serves in proportion to housing units.
"""
import os
import re
import zipfile

import pandas as pd
import requests

from metric_grid.config import load_config, load_env
from metric_grid.ingest import lodes
from metric_grid.ingest.common import PROCESSED, RAW, download
from metric_grid.ingest.xlsx_min import read_xlsx

EIA861_ZIP = "https://www.eia.gov/electricity/data/eia861/zip/f861{year}.zip"
STATE_FIPS = {  # 50 states + DC; general reference table, not district-specific
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10", "DC": "11",
    "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30",
    "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
}
FIPS_STATE = {v: k for k, v in STATE_FIPS.items()}


def norm_county(name: str) -> str:
    """Normalize a county name for matching: lowercase, drop 'county'/'parish', 'St.' -> 'saint', strip punctuation."""
    n = re.sub(r"\b(county|parish)\b", "", name.lower().replace("st.", "saint"))
    return re.sub(r"[^a-z]", "", n)


def load_861(year: int = 2024) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Download EIA-861 (cached); return (service_territory, utility/state/BA map, sales table) of strings."""
    zpath = download(EIA861_ZIP.format(year=year), RAW / "eia861" / f"f861{year}.zip")
    out = RAW / "eia861" / f"f{year}"
    if not (out / f"Service_Territory_{year}.xlsx").exists():
        with zipfile.ZipFile(zpath) as z:
            z.extractall(out)
    terr = read_xlsx(out / f"Service_Territory_{year}.xlsx", 0)
    sales = read_xlsx(out / f"Sales_Ult_Cust_{year}.xlsx", 2)  # header is on the third row
    ba = sales[["Utility Number", "State", "BA Code"]].dropna().drop_duplicates()
    return terr, ba, sales


def assign_counties(terr: pd.DataFrame, ba: pd.DataFrame, groups: list[dict]) -> pd.DataFrame:
    """Return rows [state, county_norm, county_name, group, n_groups, shared, via, utilities] for every footprint county.

    `via` says why the county matched ('utility' = the group's own utility number, 'ba_code' = another utility
    (co-op/municipal) with the group's BA Code). `utilities` are the matching utility numbers. Only states where a
    group's own utility appears are considered. Shares are added later by add_shares().
    """
    ba_map = {(r["Utility Number"], r["State"]): r["BA Code"] for _, r in ba.iterrows()}
    states = {g["key"]: set(terr[terr["Utility Number"].isin(g["eia861_utility_numbers"])]["State"]) for g in groups}
    rows = []
    for (st, county), sub in terr.groupby(["State", "County"]):
        hits = {}
        for g in groups:
            if st not in states[g["key"]]:
                continue
            via, utils = set(), []
            for _, u in sub.iterrows():
                if u["Utility Number"] in g["eia861_utility_numbers"]:
                    via.add("utility"); utils.append(u["Utility Number"])
                elif ba_map.get((u["Utility Number"], st)) in g["eia861_ba_codes"]:
                    via.add("ba_code"); utils.append(u["Utility Number"])
            if via:
                hits[g["key"]] = (via, utils)
        for key, (via, utils) in hits.items():
            rows.append({"state": st, "county_norm": norm_county(county), "county_name": county, "group": key,
                         "n_groups": len(hits), "shared": len(hits) > 1, "via": "+".join(sorted(via)), "utilities": utils})
    return pd.DataFrame(rows)


def utility_customers(sales: pd.DataFrame) -> dict:
    """Total customers per (Utility Number, State): Bundled + Delivery service rows, last 'Count' column (all classes)."""
    s = sales[sales["Service Type"].isin(["Bundled", "Delivery"])].copy()
    s["customers"] = pd.to_numeric(s.iloc[:, -1], errors="coerce")
    return s.groupby(["Utility Number", "State"])["customers"].sum().to_dict()


def add_shares(asg: pd.DataFrame, terr: pd.DataFrame, customers: dict, hu: pd.Series, rule: str) -> pd.DataFrame:
    """Add `share` (sums to 1 per county across groups).

    customer_spread: each utility's customers are spread over the counties it serves in proportion to housing units
    (`hu`, indexed by (state, county_norm)); a group's share is its utilities' spread customers over the county total.
    equal: 1 / number of groups. Any county whose spread total is 0 falls back to equal and is reported by the caller.
    """
    asg = asg.copy()
    if rule == "equal":
        asg["share"] = 1.0 / asg["n_groups"]
        return asg
    if rule != "customer_spread":
        raise ValueError(f"unknown shared_county_rule {rule!r}")
    t = terr.assign(county_norm=terr["County"].map(norm_county))
    served = t.groupby(["Utility Number", "State"])["county_norm"].apply(list).to_dict()
    spread = {}  # (state, county_norm, group) -> customers
    for _, r in asg.iterrows():
        tot = 0.0
        for u in r["utilities"]:
            cs = served[(u, r["state"])]
            denom = sum(hu.get((r["state"], c), 0.0) for c in cs)
            if denom > 0:
                tot += customers.get((u, r["state"]), 0.0) * hu.get((r["state"], r["county_norm"]), 0.0) / denom
        spread[(r["state"], r["county_norm"], r["group"])] = tot
    asg["spread"] = [spread[(r.state, r.county_norm, r.group)] for r in asg.itertuples()]
    totals = asg.groupby(["state", "county_norm"])["spread"].transform("sum")
    asg["share"] = (asg["spread"] / totals).where(totals > 0, 1.0 / asg["n_groups"])
    return asg


def county_housing_units(state_fips: str, year: int, key: str) -> pd.DataFrame:
    """ACS B25001 housing units for every county in a state (cached under data/raw/acs/)."""
    cache = RAW / "acs" / f"acs5_{year}_state{state_fips}_counties_hu.csv"
    if not cache.exists():
        r = requests.get(f"https://api.census.gov/data/{year}/acs/acs5", timeout=120,
                         params={"get": "NAME,B25001_001E", "for": "county:*", "in": f"state:{state_fips}", "key": key})
        r.raise_for_status()
        rows = r.json()
        cache.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows[1:], columns=rows[0]).to_csv(cache, index=False)  # raw response only; key never written
    df = pd.read_csv(cache, dtype=str)
    df["housing_units"] = pd.to_numeric(df["B25001_001E"], errors="coerce")
    df["county_norm"] = df["NAME"].str.split(",").str[0].map(norm_county)
    df["geoid5"] = df["state"] + df["county"]
    return df[["geoid5", "county_norm", "housing_units"]]


def county_jobs(state_abbr: str, cfg: dict) -> pd.DataFrame:
    """LODES total jobs by county (first 5 digits of the workplace block code)."""
    path = download(lodes.LODES_URL.format(st=state_abbr.lower(), year=cfg["census"]["lodes_year"]),
                    RAW / "lodes" / f"{state_abbr.lower()}_wac_S000_JT00_{cfg['census']['lodes_year']}.csv.gz")
    w = pd.read_csv(path, dtype={"w_geocode": str}, usecols=["w_geocode", "C000"])
    w["geoid5"] = w["w_geocode"].str.zfill(15).str[:5]
    return w.groupby("geoid5", as_index=False)["C000"].sum().rename(columns={"C000": "jobs_total"})


def build_footprints(cfg: dict | None = None, rule: str | None = None) -> pd.DataFrame:
    """Full county table: group assignment + share + FIPS + housing units + jobs. Saved to processed/county_groups.csv.

    Raises if any footprint county cannot be matched to a Census FIPS (no silent drops).
    """
    cfg = cfg or load_config()
    rule = rule or cfg["shared_county_rule"]
    load_env()
    key = os.environ[cfg["census"]["api_key_env"]]
    terr, ba, sales = load_861()
    asg = assign_counties(terr, ba, cfg["balancing_authorities"])
    parts = []
    for st in sorted(asg["state"].unique()):
        hu = county_housing_units(STATE_FIPS[st], cfg["census"]["acs_year"], key)
        parts.append(hu.merge(county_jobs(st, cfg), on="geoid5", how="left").assign(state=st))
    ref = pd.concat(parts)
    hu_idx = ref.set_index(["state", "county_norm"])["housing_units"]
    asg = add_shares(asg, terr, utility_customers(sales), hu_idx, rule)
    out = asg.merge(ref, on=["state", "county_norm"], how="left")
    bad = out[out["geoid5"].isna() | out["housing_units"].isna()]
    if len(bad):
        raise ValueError(f"footprint counties without FIPS/housing units: {bad[['state','county_name']].drop_duplicates().values.tolist()}")
    if out["jobs_total"].isna().any():
        raise ValueError("footprint counties without LODES jobs")
    out["utilities"] = out["utilities"].map(lambda u: ";".join(u))
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROCESSED / f"county_groups_{rule}.csv", index=False)
    if rule == cfg["shared_county_rule"]:
        out.to_csv(PROCESSED / "county_groups.csv", index=False)
    return out
