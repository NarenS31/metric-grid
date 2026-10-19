"""Every sentence the page builds from model numbers. No hand-typed results: all values come from solved plans and zone data."""
import pandas as pd

from metric_grid.model.optimizer import PairResult


def headline(r: PairResult) -> str:
    """'Same 92 MW cut. N fewer electric-heat households in the dark.' (flips to 'more' when that is what the numbers say)."""
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
