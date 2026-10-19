"""Every sentence the page builds from model numbers. No hand-typed results: all values come from solved plans and zone data."""
import pandas as pd

from metric_grid.model.optimizer import PairResult


def headline(r: PairResult) -> str:
    """'Same {MW} MW cut. {N} fewer electric-heat households in the dark.' (flips to 'MORE' when that is what the numbers say)."""
    n = r.baseline.electric_heat_households - r.weighted.electric_heat_households
    mw = f"{r.target_mw:.0f}"
    if n > 0:
        tail = f"{n:,.0f} fewer electric-heat households in the dark."
    elif n < 0:
        tail = f"{abs(n):,.0f} MORE electric-heat households in the dark."
    else:
        tail = "The same number of electric-heat households in the dark."
    return f"Same {mw} MW cut. {tail}"


def flip_lines(zones: pd.DataFrame, r: PairResult, alpha_h: pd.Series) -> tuple[list[str], list[str]]:
    """(spared, cut_instead): one line per zone that differs. spared = cut in baseline, kept on in the vulnerability-aware plan.

    alpha_h is H_i(alpha) indexed by zone_id (the harm score the optimizer used)."""
    z = zones.set_index("zone_id")
    base, wtd = set(r.baseline.zone_ids), set(r.weighted.zone_ids)

    def line(zid: int) -> str:
        t = z.loc[zid]
        svi = "SVI n/a" if pd.isna(t["RPL_THEMES"]) else f"SVI {t['RPL_THEMES']:.2f}"
        eh = "" if pd.isna(t["share_electric_heat"]) else f", {t['share_electric_heat']:.0%} electric heat"
        return (f"<b>Zone {zid}</b> · {t['COUNTY'].replace(' County', '')} — {svi}{eh}, {t['occupied_units']:,.0f} households, "
                f"{t['L_mw']:.1f} MW est. load, harm score {alpha_h.loc[zid]:.2f}")
    spared = [line(i) for i in sorted(base - wtd, key=lambda i: -z.loc[i, "RPL_THEMES"] if pd.notna(z.loc[i, "RPL_THEMES"]) else 1)]
    cut = [line(i) for i in sorted(wtd - base, key=lambda i: -z.loc[i, "L_mw"])]
    return spared, cut


def dollars(x: float) -> str:
    return f"${x:,.0f}"


TOOLTIPS = {  # plain-language definitions shown on hover; numbers in them are filled from config by tip()
    "SVI": "Social Vulnerability Index (CDC/ATSDR, 2022): a tract's percentile rank from 0 (least vulnerable) to 1 (most vulnerable) "
           "among US tracts. It already includes age 65+, income, disability and housing factors.",
    "ICE": "Interruption Cost Estimate (Lawrence Berkeley National Laboratory): survey-based estimates of what a power interruption "
           "costs customers. Used here for a 1-hour interruption, in 2013 dollars (not inflated).",
    "census tract zone": "Each zone is one census tract. It is not a utility service boundary and is not verified against any "
                         "utility's network.",
    "target band": "Both plans must cut at least the required MW and at most {delta}% more (widened up to {widen}% only if no "
                   "combination of zones fits), because load is shed in blocks and operators cannot hit an exact MW.",
    "modeled": "A modeled district estimate: scaled down from two utilities' balancing-authority demand with housing units and "
               "jobs. Not an observed utility value.",
}


def tip(term: str, key: str, cfg: dict | None = None) -> str:
    """HTML span that shows the definition for `key` on hover (dotted underline, help cursor)."""
    text = TOOLTIPS[key]
    if cfg is not None:
        text = text.format(delta=f"{cfg['optimizer']['band_pct']:.0f}", widen=f"{max(cfg['optimizer']['band_widen_pct']):.0f}")
    return f"<span class='tip' title=\"{text}\">{term}</span>"
