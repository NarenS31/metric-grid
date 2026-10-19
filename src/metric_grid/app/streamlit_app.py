"""METRIC-Grid: one-page Streamlit app. Reads only data/frozen/ (no network). Every number comes from the model functions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # src/, so `streamlit run` works without PYTHONPATH

import pandas as pd
import streamlit as st

from metric_grid.app import copy, data, demand_panel, distribution, lookup, maps, provenance, theme
from metric_grid.config import ROOT
from metric_grid.model import harm
from metric_grid.model.optimizer import PlanResult
from metric_grid.model.scenarios import county_breakdown, plain_summary

st.set_page_config(page_title="METRIC-Grid", page_icon=None, layout="wide", initial_sidebar_state="collapsed")
st.markdown(theme.CSS, unsafe_allow_html=True)

try:
    A = data.load_all()
except (FileNotFoundError, OSError) as exc:  # missing-data state: say exactly what to do, never a stack trace
    st.markdown("<div class='eyebrow'>METRIC-Grid</div><div class='headline'>The frozen data is missing.</div>", unsafe_allow_html=True)
    st.error(f"The app reads only the files in data/frozen/ and could not open them ({exc}). "
             "Run `make data` and `make freeze` (needs network and API keys once), or restore data/frozen/ from the repository.")
    st.stop()
cfg, consts, zones, zh = A["cfg"], A["consts"], A["zones"], A["zh"]
TOP_ZONE = int(A["sens"]["priority_list"][0]["zone_id"])  # the top "where to plan first" zone opens in the detail card
cap_share = cfg["optimizer"]["county_cap"]["max_share"]
PCTS = data.pct_options(consts, cfg)
ALPHAS = cfg["optimizer"]["alpha_grid"]
ELLIOTT_PCT = PCTS[0]
DEFAULTS = {"pct": ELLIOTT_PCT, "alpha": cfg["harm"]["alpha_default"], "cap": False, "zone": TOP_ZONE}


def _snap(value: float, options: list) -> float:
    return min(options, key=lambda o: abs(o - value))


def init_state() -> None:
    """Defaults, overridable once per session by URL query (?alpha=1&pct=10&cap=1&zone=23): deep links and screenshots."""
    if "init" in st.session_state:
        return
    q = st.query_params
    s = st.session_state
    s["pct"] = _snap(float(q["pct"]), PCTS) if "pct" in q else DEFAULTS["pct"]
    s["alpha"] = _snap(float(q["alpha"]), ALPHAS) if "alpha" in q else DEFAULTS["alpha"]
    s["cap"] = q.get("cap") == "1"
    s["zone"] = int(q["zone"]) if "zone" in q and str(q["zone"]).isdigit() else TOP_ZONE
    s["init"] = True


def reset_demo() -> None:
    for k, v in DEFAULTS.items():
        st.session_state[k] = v


init_state()


def metric(label: str, value: str, sub: str = "") -> str:
    return f"<div class='metric'><div class='l'>{label}</div><div class='v'>{value}</div><div class='s'>{sub}&nbsp;</div></div>"


def plan_metrics(p: PlanResult) -> str:
    cells = [
        metric("MW cut", f"{p.mw_shed:.1f}", f"{p.overshed_mw:.2f} MW over target"),
        metric("Households cut", f"{p.households:,.0f}", f"{p.n_zones} zones"),
        metric("Electric-heat households cut", f"{p.electric_heat_households:,.0f}", "ACS estimate"),
        metric("Vulnerability-weighted households", f"{p.h_human:,.0f}", f"households × {copy.tip('SVI', 'SVI')}-based index"),
        metric(copy.tip("Interruption cost", "ICE"), copy.dollars(p.h_econ), "2013 dollars, 1 hour"),
        metric("Jobs in cut zones", f"{p.jobs:,.0f}", "LODES count"),
    ]
    return "<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem 1rem'>" + "".join(cells) + "</div>"


# ---------------------------------------------------------------- 1. top bar
st.markdown(
    "<div class='topbar'><span class='brand'>METRIC-Grid</span><span class='pill'>North Carolina's 8th District</span>"
    "<span class='pill accent'>Modeled scenario</span></div>"
    f"<p class='tagline'>Same target, different burden. · Public-data planning simulator, not an operational switching tool. · "
    f"Scenario date {consts['scenario']['date']} · Data built {consts['built_utc'][:10]}</p>", unsafe_allow_html=True)

left, right = st.columns([1.55, 1], gap="large")

# ---------------------------------------------------------------- 4. controls (built first: the headline needs their values)
with right:
    with st.container(border=True):
        st.markdown("<div class='serif' style='font-size:1.15rem;font-weight:700'>Controls</div>", unsafe_allow_html=True)
        st.select_slider(
            "Required reduction (% of modeled NC-08 load)", options=PCTS, key="pct",
            format_func=lambda p: f"{p:.2f}% · {consts['D_NC08_mw'] * p / 100:.0f} MW" + (" · Elliott" if p == ELLIOTT_PCT else ""))
        st.select_slider("Business cost ↔ Human harm", options=ALPHAS, key="alpha", format_func=lambda a: f"{a:.2f}")
        st.caption("0 = weigh interruption cost only · 1 = weigh vulnerability-weighted households only")
        st.toggle(f"Limit any one county to {cap_share:.0%} of the cut", key="cap")
        st.button("Reset demo", on_click=reset_demo)

view = data.get_view(st.session_state["alpha"], st.session_state["pct"], st.session_state["cap"])
r = view["pair"]
rec = view["record"]
dist, lo_key = rec["loadonly"], rec["loadonly_key"]
n_plans, lo_counts, lo_metrics = dist["n"], A["lo_counts"][rec["loadonly_key"]], A["lo_metrics"][rec["loadonly_key"]]
H = st.session_state["alpha"] * zh["Hhat_human"] + (1 - st.session_state["alpha"]) * zh["Hhat_econ"]
H.index = zh["zone_id"]

# ---------------------------------------------------------------- 2-3. eyebrow, headline, honest line
with left:
    when = pd.Timestamp(consts["scenario"]["date"]).strftime("%b %d, %Y").replace(" 0", " ")
    st.markdown(f"<div class='eyebrow'>{consts['scenario']['name'].split(',')[0]} · {when} · modeled district estimate</div>",
                unsafe_allow_html=True)
    st.markdown(f"<div class='headline'>{copy.headline(r)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='honest'>{copy.range_line(dist)}<br/>{plain_summary(r)}</div>", unsafe_allow_html=True)
    st.markdown(f"<p class='scaling'>{provenance.DISTRICT_SENTENCE}</p>", unsafe_allow_html=True)
    for w in A["warnings"]:
        st.markdown(f"<p class='scaling'>Data note: {w}</p>", unsafe_allow_html=True)

if view["note"]:
    st.markdown(f"<div class='note{' warn' if view.get('infeasible') else ''}'>{view['note']}</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- 5. two maps
vs = maps.view_state(A["district"])
district_gj = A["district"].__geo_interface__
hatch = st.cache_resource(lambda: maps.hatch_features(zones))()
st.markdown(
    f"<div class='legend'><span><span class='sw' style='background:#F0EBFC'></span>low {copy.tip('SVI', 'SVI')} (kept on)</span>"
    f"<span><span class='sw' style='background:#4628AA'></span>high {copy.tip('SVI', 'SVI')} (kept on)</span>"
    "<span><span class='sw' style='background:#16121F'></span>cut</span>"
    "<span><span class='sw' style='background:repeating-linear-gradient(45deg,#fff,#fff 2px,#1C1A24 2px,#1C1A24 3px)'></span>"
    "hatched outline = protected, never cut</span>"
    f"<span><span class='sw' style='background:#CDC8D7'></span>no {copy.tip('SVI', 'SVI')} data</span>"
    "<span><span class='sw' style='background:transparent;border:2px solid #5B3FD6'></span>NC-08 outline (tracts shown whole)</span></div>",
    unsafe_allow_html=True)
mc1, mc2 = st.columns(2, gap="medium")
for col, title, sub, short, plan in (
        (mc1, f"A typical load-only plan (median of {n_plans} equivalent plans)",
         "Meets the same MW band and ignores who lives there; one of many equivalent plans, the one closest to the median on four measures",
         "typical load-only plan", r.baseline),
        (mc2, "Vulnerability-aware plan", "Lowest modeled harm for the same MW band", "vulnerability-aware plan", r.weighted)):
    with col:
        st.markdown(f"<div class='maptitle'>{title}</div><div class='mapsub'>{sub}</div>", unsafe_allow_html=True)
        fc = maps.zone_collection(zones, set(plan.zone_ids), short, freq=lo_counts, n_plans=n_plans)
        st.pydeck_chart(maps.build_deck(fc, hatch, district_gj, vs), height=500)
        st.markdown(plan_metrics(plan), unsafe_allow_html=True)
band_txt = f"Both plans cut between {r.band_lo_mw:.1f} and {r.band_hi_mw:.1f} MW"
band_word = copy.tip("target band", "target band", cfg)
band_txt += f" ({band_word} widened to {r.delta_pct_used:.0f}% to find a solution)." if r.widened else f" ({band_word}: target plus {r.delta_pct_used:.0f}%)."
cap_txt = f" No county takes more than {cap_share:.0%} of either plan's cut." if view["cap_applied"] else ""
st.markdown(f"<p class='cap'>{band_txt}{cap_txt} Cost is in 2013 dollars.</p>", unsafe_allow_html=True)

cb1, cb2 = st.columns(2, gap="medium")
for col, plan in ((cb1, r.baseline), (cb2, r.weighted)):
    with col:
        b = county_breakdown(zh, plan)
        st.caption("Where it lands: " + "; ".join(
            f"{i.replace(' County', '')} {row.share_of_cut:.0%} ({int(row.zones)} zones, {row.households:,.0f} households)" for i, row in b.iterrows()))

# ---------------------------------------------------------------- 5b. distribution strip
with st.container(border=True):
    st.markdown(f"<div class='serif' style='font-size:1.2rem;font-weight:700'>Where the vulnerability-aware plan falls among {n_plans} equivalent load-only plans</div>",
                unsafe_allow_html=True)
    st.markdown("<p class='scaling'>Grey dots: each equivalent load-only plan (same MW band, near-minimal overshoot). Dark diamond: the typical plan on the "
                "left map. Violet circle: the vulnerability-aware plan. Many plans tie, so a single load-only plan is arbitrary; the dots show the "
                "whole range.</p>", unsafe_allow_html=True)
    cols = st.columns(4, gap="medium")
    typ = {"electric_heat_households": r.baseline.electric_heat_households, "h_human": r.baseline.h_human,
           "h_econ": r.baseline.h_econ, "households": r.baseline.households}
    wtd = {"electric_heat_households": r.weighted.electric_heat_households, "h_human": r.weighted.h_human,
           "h_econ": r.weighted.h_econ, "households": r.weighted.households}
    vals = {k: lo_metrics[k].tolist() for k in typ}
    for col, (title, spec) in zip(cols, distribution.specs(vals, typ, wtd)):
        with col:
            st.vega_lite_chart(spec, width="stretch")
    st.caption(distribution.caption(dist))

# ---------------------------------------------------------------- 6. flip strip
spared, cut_instead = copy.flip_lines(zh, r, H, lo_counts, n_plans)
with st.container(border=True):
    st.markdown(f"<div class='eyebrow' style='margin-top:.2rem'>Flip strip · {len(spared) + len(cut_instead)} zones differ between the plans</div>",
                unsafe_allow_html=True)
    f1, f2 = st.columns(2, gap="large")
    with f1:
        st.markdown("<div class='flipcol'><h4>Kept on in the vulnerability-aware plan (cut in the typical load-only plan)</h4>" +
                    "".join(f"<div class='flip'>{x}</div>" for x in spared) + "</div>", unsafe_allow_html=True)
    with f2:
        st.markdown("<div class='flipcol'><h4>Cut instead (kept on in the typical load-only plan)</h4>" +
                    "".join(f"<div class='flip'>{x}</div>" for x in cut_instead) + "</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- 7. three cards
c1, c2, c3 = st.columns([1.15, 1, 1.05], gap="medium")
sens = A["sens"]
rows = pd.DataFrame(sens["rows"])

with c1, st.container(border=True):
    st.markdown("<div class='serif' style='font-size:1.2rem;font-weight:700'>Where to plan first</div>", unsafe_allow_html=True)
    st.markdown("<p class='scaling'>Zones the typical load-only plan cuts that the vulnerability-aware plan spares in every setting with "
                "alpha above 0, most vulnerable first. The last column is how often the equivalent load-only plans cut the zone: it is low, "
                "because those plans differ a lot, so read the list as an illustration, not a ranking.</p>", unsafe_allow_html=True)
    body = "".join(
        f"<tr><td>{p['zone_id']}</td><td>{p['COUNTY'].replace(' County', '')}</td><td>{p['RPL_THEMES']:.2f}</td>"
        f"<td>{p['share_electric_heat']:.0%}</td><td>{p['occupied_units']:,.0f}</td>"
        f"<td>{p['loadonly_cut_share']:.0%}</td><td>{'cut at alpha 0' if p['cut_at_alpha0'] else ''}</td></tr>" for p in sens["priority_list"])
    st.markdown(f"<table class='t'><tr><th>Zone</th><th>County</th><th>{copy.tip('SVI', 'SVI')}</th><th>Electric heat</th><th>Households</th><th>Load-only plans that cut it</th><th>Note</th></tr>"
                f"{body}</table>", unsafe_allow_html=True)
    st.markdown("<p class='scaling' style='margin-top:.5rem'><b>This is what the model spares across settings, not a finding about "
                "specific neighborhoods.</b> Follow-ups to consider: outreach, backup-power planning, resilience-hub siting, "
                "request utility network data. Never a switching recommendation.</p>", unsafe_allow_html=True)
    st.markdown(f"<p class='scaling'>Critical facilities: {consts['n_protected']} zones with a hospital, nursing home or water treatment "
                f"plant are never cut ({consts['protected_load_mw'] / consts['D_NC08_mw']:.1%} of modeled load); the facility data may be "
                "incomplete.</p>", unsafe_allow_html=True)

with c2, st.container(border=True):
    st.markdown("<div class='serif' style='font-size:1.2rem;font-weight:700'>Zone detail</div>", unsafe_allow_html=True)
    zid_opts = [0] + [int(i) for i in sorted(zh["zone_id"])]
    zlab = zh.set_index("zone_id")["COUNTY"]
    st.selectbox("Zone", zid_opts, key="zone", format_func=lambda i: "Choose a zone…" if i == 0 else f"Zone {i} · {zlab.loc[i]}")
    zid = st.session_state["zone"]
    if zid:
        z = zh[zh["zone_id"] == zid].iloc[0]
        alpha = st.session_state["alpha"]
        ws, we = cfg["harm"]["w_svi"], cfg["harm"]["w_eheat"]
        c_res = cfg["harm"]["ice"]["residential_per_household_1h"]
        c_job = harm.commercial_cost_per_job(cfg, consts["kw_per_job"])["retail"]

        def status(p: PlanResult) -> str:
            return "CUT" if zid in p.zone_ids else ("protected, never cut" if z["protected"] else "kept on")

        badges = f"<span class='badge'>{copy.tip('census tract zone', 'census tract zone')}</span>" \
                 f"<span class='badge v'>{copy.tip('load: modeled', 'modeled')}</span>" + \
                 ("<span class='badge'>protected</span>" if z["protected"] else "")
        st.markdown(badges, unsafe_allow_html=True)
        svi = "n/a (no data)" if pd.isna(z["RPL_THEMES"]) else f"{z['RPL_THEMES']:.3f}"
        eh = "n/a" if pd.isna(z["share_electric_heat"]) else f"{z['share_electric_heat']:.3f}"
        st.markdown(f"**Zone {zid}** · {z['COUNTY']} · tract {z['GEOID']}  \n"
                    f"Typical load-only plan: **{status(r.baseline)}** · Vulnerability-aware plan: **{status(r.weighted)}**  \n"
                    f"{lo_counts.get(zid, 0)} of {n_plans} equivalent load-only plans cut this zone.")
        code = (
            f"inputs  households N = {z['N_households']:,.0f}, SVI = {svi}, electric heat = {eh}, jobs = {z['jobs_total']:,.0f}\n"
            f"load    L = D_NC08 x W / sum(W) = {z['L_mw']:.2f} MW (modeled)\n"
            f"        W = {z['housing_units']:,.0f} units x {consts['kw_per_unit']:.2f} kW + {z['jobs_total']:,.0f} jobs x {consts['kw_per_job']:.2f} kW\n"
            f"human   H_human = N x ({ws} x SVI + {we} x heat) = {z['H_human']:,.1f}\n"
            f"cost    H_econ = N x ${c_res} + jobs x ${c_job:.2f} = ${z['H_econ']:,.0f} (2013 dollars)\n"
            f"scaled  Hhat_human = {z['Hhat_human']:.3f}, Hhat_econ = {z['Hhat_econ']:.3f}\n"
            f"blend   H(alpha={alpha:.2f}) = {alpha:.2f} x {z['Hhat_human']:.3f} + {1 - alpha:.2f} x {z['Hhat_econ']:.3f} = {H.loc[zid]:.3f}")
        st.code(code, language=None, wrap_lines=True)
    else:
        st.caption("Select a zone to see its inputs and the harm formula with its numbers substituted.")

with c2, st.container(border=True):
    st.markdown("<div class='serif' style='font-size:1.2rem;font-weight:700'>Example locations</div>", unsafe_allow_html=True)
    st.markdown("<p class='scaling'>Three example public buildings (no home addresses, no live geocoder), chosen to illustrate "
                "differences between the plans. Status is for the census tract zone the building sits in, under the current "
                "controls.</p>", unsafe_allow_html=True)
    lrows = lookup.lookup_rows(zones, cfg["example_locations"], r)
    st.markdown("<table class='t'><tr><th>Location</th><th>Zone</th><th>Typical load-only</th><th>Vulnerability-aware</th><th>Load-only plans that cut it</th></tr>" + "".join(
        f"<tr><td>{x['label']}</td><td>{x['zone_id']}</td><td>{x['baseline']}</td><td>{x['weighted']}</td><td>{lo_counts.get(x['zone_id'], 0)} of {n_plans}</td></tr>" for x in lrows)
        + "</table>", unsafe_allow_html=True)

with c3, st.container(border=True):
    st.markdown("<div class='serif' style='font-size:1.2rem;font-weight:700'>How robust is this?</div>", unsafe_allow_html=True)
    n = len(rows)
    beat_h = int((rows["human_change_pct"] < 0).sum())
    beat_c = int((rows["econ_change_pct"] < 0).sum())
    more_hh = int((rows["households_change"] > 0).sum())
    zero = rows[rows["human_change_pct"] >= 0]
    pos = rows[rows["alpha"] > 0]
    cap_row = rows[rows["county_cap"].notna()].iloc[0]
    why = f" (the {len(zero)} that do not set alpha to 0, which ignores human harm)" if len(zero) else ""
    N = int(rows["n_plans"].iloc[0])
    st.markdown(
        f"<p style='font-size:.9rem'><b>{beat_h} of {n}</b> settings beat the typical load-only plan on human harm{why}; "
        f"<b>{beat_c} of {n}</b> on interruption cost (2013 dollars); in <b>{more_hh} of {n}</b> the vulnerability-aware plan "
        f"cuts <b>more</b> total households.</p>"
        f"<p style='font-size:.9rem'>Against all {N} equivalent load-only plans, in the {len(pos)} settings with alpha above 0 it has fewer "
        f"vulnerability-weighted households than {int(pos['beats_human'].min())} to {int(pos['beats_human'].max())} of them and fewer electric-heat "
        f"households than {int(pos['beats_ehh'].min())} to {int(pos['beats_ehh'].max())}; on interruption cost it beats "
        f"{int(pos['beats_cost'].min())} to {int(pos['beats_cost'].max())} (cost matters less as alpha rises).</p>"
        f"<p style='font-size:.9rem'>With the {cap_share:.0%} county cap ON: human harm {cap_row['human_change_pct']:+.0f}%, cost "
        f"{cap_row['econ_change_pct']:+.0f}%, {cap_row['households_change']:+,.0f} households (vs that setting's typical plan).</p>"
        f"<p class='scaling'>Zones the vulnerability-aware plan cuts in every setting: {len(sens['classes']['always'])}; in some: "
        f"{len(sens['classes']['sometimes'])}; never: {len(sens['classes']['never'])}; protected: {len(sens['classes']['protected'])}.</p>",
        unsafe_allow_html=True)
    st.image(str(ROOT / "data" / "frozen" / "alpha_tradeoff.png"), width="stretch")
    with st.expander("Stress test: all settings"):
        show = rows[["setting", "alpha", "w_svi", "human_change_pct", "econ_change_pct", "households_change"]].rename(columns={
            "human_change_pct": "human harm %", "econ_change_pct": "cost % (2013$)", "households_change": "households cut +/-"})
        st.dataframe(show.round(1), hide_index=True, width="stretch")

# ---------------------------------------------------------------- 7b. demand panel (hidden if its frozen file is missing)
panel = A["panel"]
if panel:
    with st.container(border=True):
        st.markdown("<div class='serif' style='font-size:1.2rem;font-weight:700'>Why forecasts aren't enough</div>", unsafe_allow_html=True)
        st.markdown(f"<p class='scaling'>{panel['label']}</p>", unsafe_allow_html=True)
        pc1, pc2 = st.columns([1.7, 1], gap="large")
        with pc1:
            st.vega_lite_chart(demand_panel.chart_spec(panel), width="stretch")
        with pc2:
            st.markdown(f"<p class='honest'>{demand_panel.sentence(panel, demand_panel.total_shed_mw(consts))}</p>", unsafe_allow_html=True)
            st.markdown(demand_panel.temperature_table(panel), unsafe_allow_html=True)
            st.markdown(f"<p class='scaling'>{demand_panel.coldest_note(panel)}</p>", unsafe_allow_html=True)

# ---------------------------------------------------------------- 8. methods & sources drawer
with st.expander("Methods & sources"):
    g = consts["groups"]
    st.markdown("**This is not Duke's method, not an operational switching tool, and the zones are census tracts, not utility "
                "boundaries.** Everything here is a planning scenario built from public data.")
    st.markdown(f"**District scaling.** {provenance.DISTRICT_SENTENCE} Load is scaled from two utilities' balancing-authority demand "
                f"(Duke Energy Carolinas {g['DEC']['D_group_mw']:,.0f} MW and Duke Energy Progress {g['DEP']['D_group_mw']:,.0f} MW in the hour ending 07:00, that is 06:00 to 07:00) "
                f"using a modeled weight (housing units and jobs): D_NC08 = sum of D_utility x W_NC08-in-utility / W_utility = "
                f"{consts['D_NC08_mw']:,.0f} MW; required reduction T_NC08 = {consts['T_NC08_mw']:.1f} MW.")
    st.markdown(f"**Reduction ratio r.** {consts['r_definition']}. r (Carolinas) = {g['DEC']['r']:.4f}, r (Progress) = {g['DEP']['r']:.4f}.")
    st.markdown(f"**Shared target band.** Both plans must cut between T and T + delta, delta = {cfg['optimizer']['band_pct']:.0f}% of T "
                f"(widened to at most {max(cfg['optimizer']['band_widen_pct']):.0f}% if needed): load is shed in discrete blocks and operators cannot "
                "hit an exact MW.")
    lo_meta = A["loadonly_method"]
    st.markdown(f"**Load-only comparison set.** Many different plans meet the MW target equally well, so one \"load-only baseline\" would be arbitrary. "
                f"The page compares against {n_plans} distinct plans that meet the target and overshoot it by at most {lo_meta['near_opt_pct']:.0f}% "
                f"(generated deterministically with a fixed seed and random zone costs; a wide cross-section of the near-optimal plans, not a uniform "
                f"sample). The left map shows the one closest to the median on four measures (households, electric-heat households, vulnerability-weighted "
                f"households, interruption cost).")
    st.markdown(f"**Protected facilities.** Zones containing a hospital, nursing home or water treatment plant are never cut "
                f"({consts['n_protected']} zones). This may protect more modeled load than necessary, and the OpenStreetMap facility "
                "data may be incomplete. Fire and police stations are not excluded (they commonly have backup generation).")
    st.markdown("**Sources**", unsafe_allow_html=True)
    st.markdown(provenance.datasets_table(consts), unsafe_allow_html=True)
    st.markdown("**Where each number on this page comes from**", unsafe_allow_html=True)
    st.markdown(provenance.number_sources_table(consts), unsafe_allow_html=True)
