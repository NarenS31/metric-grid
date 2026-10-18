"""Static PNG figures for docs and README (matplotlib, Agg backend). The app itself uses pydeck/streamlit."""
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
    ax.text(7.1, ax.get_ylim()[1] - 1.2, "07:00 reference hour", fontsize=8)
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


if __name__ == "__main__":
    demand_figure()
