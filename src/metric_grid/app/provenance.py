"""Methods & sources drawer content. UI_SOURCES ties every kind of number on the page to named datasets (and a label)."""
DISTRICT_SENTENCE = ("The Elliott regional event anchors this scenario. NC-08 load and required reduction are modeled "
                     "district-scale estimates, not observed utility circuit values.")

# UI number -> (label shown to the reader, tokens that must each match a dataset name in constants["datasets"])
UI_SOURCES = {
    "Modeled NC-08 load, required reduction (MW)": ("modeled district estimate",
        ["EIA-930", "EIA Form 861", "NREL", "Census ACS", "LEHD LODES", "SC Office of Regulatory Staff", "FERC-NERC"]),
    "Estimated zone load (MW)": ("modeled district estimate", ["Census ACS", "LEHD LODES", "NREL", "EIA-930"]),
    "SVI (zone shading, tooltips, flip strip)": ("tract-level index, 0 to 1", ["Social Vulnerability Index"]),
    "Households, electric-heat share and households": ("ACS 5-year estimate", ["Census ACS"]),
    "Jobs": ("LODES count", ["LEHD LODES"]),
    "Interruption cost (2013 dollars)": ("modeled", ["LBNL"]),
    "Protected zones": ("OpenStreetMap points; coverage incomplete", ["OpenStreetMap"]),
    "Reduction ratio r (each utility's maximum firm load shed, MW)": ("sourced, regional", ["SC Office of Regulatory Staff", "FERC-NERC"]),
    "Demand panel (predicted vs actual DUK+CPLE demand, error by temperature)": ("modeled demand estimate; not a utility forecast",
        ["EIA-930", "KCLT"]),
    "Load-only plan set (the N equivalent plans, their ranges and counts)": ("modeled; generated with a fixed seed",
        ["Census ACS", "LEHD LODES", "NREL", "EIA-930", "LBNL"]),
    "Zone boundaries": ("census tract zones, not utility boundaries", ["Census TIGER"]),
    "Harm weights, alpha, band width, county cap": ("judgment calls set in config.yaml", []),
}


def datasets_table(consts: dict) -> str:
    """HTML table of every dataset: name, vintage, URL."""
    rows = "".join(f"<tr><td>{d['name']}</td><td>{d['vintage']}</td><td>{d['url']}</td></tr>" for d in consts["datasets"])
    return f"<table class='t'><tr><th>Source</th><th>Date / vintage</th><th>URL</th></tr>{rows}</table>"


def number_sources_table(consts: dict) -> str:
    """HTML table: each kind of number on the page, its label, and the datasets behind it (names resolved from constants)."""
    rows = ""
    for what, (label, tokens) in UI_SOURCES.items():
        names = []
        for tok in tokens:
            names += [d["name"] for d in consts["datasets"] if tok in d["name"]]
        rows += f"<tr><td>{what}</td><td>{label}</td><td>{'; '.join(dict.fromkeys(names)) or 'config.yaml (documented in ASSUMPTIONS.md)'}</td></tr>"
    return f"<table class='t'><tr><th>Number</th><th>Label</th><th>Source</th></tr>{rows}</table>"
