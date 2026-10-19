"""Static PNG figures for docs and README (matplotlib, Agg backend). The app itself uses inline SVG maps and Streamlit."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from metric_grid.config import ROOT, load_config
from metric_grid.ingest import eia930
from metric_grid.ingest.common import PROCESSED


def demand_figure(out_path=ROOT / "docs" / "figures" / "demand_elliott.png") -> None:
    """Hourly demand for each footprint group on 2022-12-24 (local), shed-start markers, KCLT temperature."""
    cfg = load_config()
    eia = pd.read_csv(PROCESSED / "eia930_demand.csv", parse_dates=["period_utc"])
    eia["local_time"] = eia["period_utc"].dt.tz_convert(cfg["scenario"]["local_tz"])
    wide = eia930.group_demand(eia, cfg)
    day = wide[wide["local_time"].dt.strftime("%Y-%m-%d") == cfg["scenario"]["date"]]
    temp = pd.read_csv(PROCESSED / "kclt_temp.csv", parse_dates=["local_time"], date_format="ISO8601")
    temp["local_time"] = pd.to_datetime(temp["local_time"], utc=True).dt.tz_convert(cfg["scenario"]["local_tz"])
    temp = temp[temp["local_time"].dt.strftime("%Y-%m-%d") == cfg["scenario"]["date"]]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    hours = day["local_time"].dt.hour + day["local_time"].dt.minute / 60
    for g in cfg["balancing_authorities"]:
        ax.plot(hours, day[g["key"]] / 1000, marker="o", ms=3, label=f"{g['name']} ({'+'.join(g['eia930_respondents'])})")
    ax.axvline(6 + 14 / 60, color="grey", ls="--", lw=1)
    ax.text(6.3, ax.get_ylim()[0] + 0.5, "shed begins 6:14 (DEC)", fontsize=8, color="grey")
    ax.axvline(7, color="black", lw=1)
    ax.text(7.1, ax.get_ylim()[1] - 1.2, "hour ending 07:00", fontsize=8)
    ax.set_xlabel("Hour of day, 2022-12-24 (local, EST)")
    ax.set_ylabel("Observed demand (GW)")
    ax2 = ax.twinx()
    ax2.plot(temp["local_time"].dt.hour + temp["local_time"].dt.minute / 60, temp["temp_f"], color="tab:gray", lw=1, ls=":")
    ax2.set_ylabel("KCLT temperature (F), display only", color="tab:gray")
    ax.set_title("Winter Storm Elliott: observed balancing-authority demand (EIA-930)")
    ax.legend(loc="center right", fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130)




def zone_map_figure(out_path=ROOT / "docs" / "figures" / "zone_map_L.png") -> None:
    """Zones coloured by estimated zone load L_i (MW); protected zones hatched with a heavy outline. Reads data/frozen only."""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    from metric_grid import frozen

    zones = frozen.load_zones()
    consts = frozen.load_constants()
    fig, ax = plt.subplots(figsize=(8, 7.5))
    zones.plot(column="L_mw", cmap="viridis", edgecolor="white", linewidth=0.3, legend=True, ax=ax,
               legend_kwds={"label": "Estimated zone load L_i, hour ending 07:00 (MW, modeled district estimate)", "shrink": 0.7})
    prot = zones[zones["protected"]]
    prot.plot(facecolor="none", edgecolor="black", linewidth=1.6, hatch="///", ax=ax)
    frozen.load_district().boundary.plot(ax=ax, color="#d95f02", linewidth=2.2)
    ax.legend(handles=[Patch(facecolor="none", edgecolor="black", hatch="///", label="protected (hospital, nursing home, water treatment)"),
                       Line2D([0], [0], color="#d95f02", lw=2.2, label="NC-08 district outline (tracts shown whole)")],
              loc="lower left", fontsize=8)
    ax.set_axis_off()
    ax.set_title(f"NC-08 census tract zones: {consts['n_zones']} zones, {consts['n_protected']} protected\n"
                 f"D_NC08 = {consts['D_NC08_mw']:,.0f} MW (modeled), T_NC08 = {consts['T_NC08_mw']:.1f} MW (modeled)", fontsize=10)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130)


def alpha_tradeoff_figure(out_path=ROOT / "docs" / "figures" / "alpha_tradeoff.png", compact: bool = False) -> None:
    """Percent change of the harm-weighted plan vs the load-only baseline across alpha. Reads data/frozen only.

    Shows the households-cut change next to the harm numbers: the weighted plan cuts MORE households at every alpha.
    compact=True makes a narrower figure with larger type, for the app's card.
    """
    import pandas as pd

    from metric_grid import frozen

    df = pd.DataFrame(frozen.load_alpha_sweep())
    fs = 11 if compact else 8
    fig, ax = plt.subplots(figsize=(6.2, 5.6) if compact else (9, 5.2))
    ax.axhline(0, color="black", lw=0.8)
    ax.plot(df["alpha"], df["human_change_pct"], marker="o", color="#0072B2", lw=2.4, label="Vulnerability-weighted households cut")
    ax.plot(df["alpha"], df["econ_change_pct"], marker="s", color="#E69F00", lw=2.4, label="Interruption cost (2013 dollars)")
    ax.plot(df["alpha"], df["households_change_pct"], marker="^", color="#555555", lw=1.8, ls="--", label="Households cut (all households)")
    for _, r in df.iterrows():
        ax.annotate(f"{r['households_change']:+,.0f} hh", (r["alpha"], r["households_change_pct"]), textcoords="offset points",
                    xytext=(0, 9), ha="center", fontsize=fs, color="#555555")
    ax.set_xticks(df["alpha"])
    ax.margins(x=0.14)  # room for the end labels
    ax.tick_params(labelsize=fs)
    ax.set_xlabel("alpha (0 = cost only, 1 = human harm only)" if compact else "alpha   (0 = economic cost only  <->  1 = human harm only)", fontsize=fs)
    ax.set_ylabel("Vulnerability-aware plan vs baseline (%)" if compact else "Harm-weighted plan vs load-only baseline (%)", fontsize=fs)
    title = ("Below zero = less modeled harm.\nThe plan cuts MORE households at every alpha." if compact else
             "Same MW target, different burden (modeled)\nBelow zero = less modeled harm; the weighted plan cuts MORE households at every alpha")
    ax.set_title(title, fontsize=fs + 1)
    ax.legend(loc="upper right", fontsize=fs - 1 if compact else fs)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130)


if __name__ == "__main__":
    demand_figure()
    zone_map_figure()
    alpha_tradeoff_figure()
