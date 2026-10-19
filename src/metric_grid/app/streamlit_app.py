"""METRIC-Grid: one-page Streamlit app. Reads only data/frozen/ (no network). Every number comes from the model functions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # src/, so `streamlit run` works without PYTHONPATH

import pandas as pd
import streamlit as st

from metric_grid.app import copy, data, demand_panel, distribution, lookup, maps, provenance, theme
from metric_grid.config import ROOT
from metric_grid.model import harm
from metric_grid.model.optimizer import PairResult, PlanResult
from metric_grid.model.scenarios import county_breakdown, plain_summary

def _page_icon():
    """Favicon: the wordmark's 3x3 grid as a tiny image (no file needed)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for row in range(3):
        for col in range(3):
            on = (row + col) == 2
            d.rounded_rectangle([4 + col * 20, 4 + row * 20, 20 + col * 20, 20 + row * 20], radius=3, fill=theme.BLUE if on else theme.BORDER)
    return img


st.set_page_config(page_title="METRIC-Grid", page_icon=_page_icon(), layout="wide", initial_sidebar_state="auto")
st.markdown(theme.css(), unsafe_allow_html=True)

try:
    with st.spinner("Loading the frozen data…"):
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


def tile(value: str, label: str, sub: str, cls: str = "") -> str:
    return f"<div class='tile {cls}'><div class='v'>{value}</div><div class='l'>{label}</div><div class='s'>{sub}</div></div>"


def stat_tiles(r: PairResult) -> str:
    """The four first-screen tiles, all from the solved pair (typical megawatts-only plan vs vulnerability-aware plan). The words
    flip ('fewer'/'MORE', 'less'/'more') if the numbers do, so a tile never overstates."""
    b, w = r.baseline, r.weighted
    ehh = b.electric_heat_households - w.electric_heat_households
    harm_pct = 100 * (1 - w.h_human / b.h_human) if b.h_human else 0.0
    hh = w.households - b.households
    return "<div class='tiles'>" + "".join([
        tile(f"{r.target_mw:.0f} MW", "Cut by both plans", f"both plans cut {r.band_lo_mw:.1f} to {r.band_hi_mw:.1f} MW"),
        tile(f"{abs(ehh):,.0f}", "fewer electric-heat homes in the dark" if ehh >= 0 else "MORE electric-heat homes in the dark",
             "vs the typical megawatts-only plan", "good" if ehh >= 0 else "attn"),
        tile(f"{abs(harm_pct):.0f}%", "less vulnerability-weighted harm" if harm_pct >= 0 else "MORE vulnerability-weighted harm",
             "vs the typical megawatts-only plan", "good" if harm_pct >= 0 else "attn"),
        tile(f"{'+' if hh >= 0 else '-'}{abs(hh):,.0f}", "more total homes cut" if hh >= 0 else "fewer total homes cut",
             "vs the typical megawatts-only plan", "attn")]) + "</div>"


def plan_numbers(p: PlanResult) -> str:
    return f"{p.mw_shed:.1f} MW · {p.households:,.0f} homes · {p.electric_heat_households:,.0f} electric-heat homes"


def section(title: str, lede: str, anchor: str, source: tuple[str, str] | None = None) -> None:
    """Section heading with an anchor for the sidebar navigation, one sentence of explanation and (optionally) the kind of data shown."""
    src = f"<p class='src'><span class='kind'>{source[0]}</span> · {source[1]}</p>" if source else ""
    st.markdown(f"<div class='sec' id='{anchor}'><h2>{title}</h2><p class='lede'>{lede}</p>{src}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- 1. sidebar shell
# controls are read from session state before they are drawn, so the tiles above them can use the current result
def _pct() -> float:
    return st.session_state["pct"] if st.session_state.get("pct") is not None else ELLIOTT_PCT


view = data.get_view(st.session_state["alpha"], _pct(), st.session_state["cap"])
r = view["pair"]
rec = view["record"]
dist, lo_key = rec["loadonly"], rec["loadonly_key"]
n_plans, lo_counts, lo_metrics = dist["n"], A["lo_counts"][rec["loadonly_key"]], A["lo_metrics"][rec["loadonly_key"]]
H = st.session_state["alpha"] * zh["Hhat_human"] + (1 - st.session_state["alpha"]) * zh["Hhat_econ"]
H.index = zh["zone_id"]

when = pd.Timestamp(consts["scenario"]["date"]).strftime("%b %d, %Y").replace(" 0", " ")
NAV = [("overview", "Overview"), ("compare", f"Compared with {n_plans} plans"), ("priority", "Priority zones"), ("lookup", "Look up a zone"),
       ("robust", "How robust is this?")] + ([("forecast", "Why forecasts aren't enough")] if A["panel"] else []) + [("methods", "Methods & sources")]
with st.sidebar:
    st.markdown(f"<div class='brand'>{theme.LOGO_SVG}<span class='name'>Metric<b>Grid</b></span></div>"
                "<nav class='nav' aria-label='Sections'>" + "".join(f"<a href='#{k}'>{v}</a>" for k, v in NAV) + "</nav>"
                f"<div class='side-meta'>Modeled planning scenario for North Carolina's 8th Congressional District.<span class='k'>Scenario date</span>"
                f"<span class='mono'>{consts['scenario']['date']}</span><span class='k'>Data built</span><span class='mono'>{consts['built_utc'][:10]}</span>"
                "<span class='k'>Runs offline from frozen public data.</span></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- 2. page header and the primary insight
ehh_gap = r.baseline.electric_heat_households - r.weighted.electric_heat_households
hh_gap = r.weighted.households - r.baseline.households
insight = (f"{consts['scenario']['name'].split(',')[0]}, {when}: two ways to cut the same {r.target_mw:.0f} MW across NC-08. "
           f"Against the typical megawatts-only plan, the vulnerability-aware plan puts <b>{abs(ehh_gap):,.0f} {'fewer' if ehh_gap >= 0 else 'MORE'}</b> "
           f"electric-heat homes in the dark and cuts <b>{abs(hh_gap):,.0f} {'more' if hh_gap >= 0 else 'fewer'}</b> homes in total.")
st.markdown(
    "<div id='overview' class='pagehead'><div><p class='crumb'>NC-08 · Modeled scenario</p>"
    "<h1 class='title'>Same power cut. Different people in the dark.</h1>"
    f"<p class='deck'>{insight}</p></div>"
    f"<div class='fresh'>Data built <span class='mono'>{consts['built_utc'][:10]}</span><br/>Scenario <span class='mono'>{consts['scenario']['date']}</span></div></div>",
    unsafe_allow_html=True)
st.markdown(stat_tiles(r), unsafe_allow_html=True)

# ---------------------------------------------------------------- 2. one slim controls bar
with st.container(border=True):
    k1, k2, k3, k4 = st.columns([2.3, 2.7, 1.9, 0.8], gap="medium", vertical_alignment="center")
    with k1:
        st.segmented_control("Reduction", PCTS, key="pct", label_visibility="collapsed",
                             format_func=lambda p: "Elliott" if p == ELLIOTT_PCT else f"{p:g}%")
    with k2:
        st.select_slider("Prioritize: Business cost ←→ People at risk", options=ALPHAS, key="alpha", format_func=lambda a: f"{a:.2f}")
    with k3:
        st.toggle(f"Limit any county to {cap_share:.0%}", key="cap")
    with k4:
        st.button("Reset", on_click=reset_demo)

if view["note"]:
    st.markdown(f"<div class='note{' warn' if view.get('infeasible') else ''}'>{view['note']}</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- 3. two maps (inline SVG: no WebGL, no external requests)
layers = st.cache_resource(lambda: maps.static_layers(zones, A["district"]))()
mc1, mc2 = st.columns(2, gap="medium")
for col, title, short, plan, mid in (
        (mc1, f"Megawatts only (typical of {n_plans} plans)", "typical megawatts-only plan", r.baseline, "map-mw"),
        (mc2, "Vulnerability-aware", "vulnerability-aware plan", r.weighted, "map-va")):
    with col:
        st.markdown(f"<p class='maptitle'>{title}</p>", unsafe_allow_html=True)
        st.markdown(maps.map_svg(zones, layers, set(plan.zone_ids), short, mid, freq=lo_counts if mid == "map-mw" else None,
                             n_plans=n_plans, label=f"Map of NC-08: {title}"), unsafe_allow_html=True)
        st.markdown(f"<p class='mapnums'>{plan_numbers(plan)}</p>", unsafe_allow_html=True)
st.markdown(
    "<div class='legend'><span><span class='sw' style='background:#1E2C48'></span><span class='sw' style='background:#506896'></span>kept on (lighter = more vulnerable)</span>"
    "<span><span class='sw' style='background:#F3BD69'></span>cut (both maps)</span>"
    "<span><span class='sw' style='background:repeating-linear-gradient(45deg,#111A2E,#111A2E 2px,#C9D3E6 2px,#C9D3E6 3px)'></span>hospital or water plant, never cut</span>"
    "<span><span class='sw' style='background:#2A2F3D'></span>no data</span></div>", unsafe_allow_html=True)
cap_txt = f" · No county takes more than {cap_share:.0%} of either plan's cut" if view["cap_applied"] else ""
st.markdown(f"<p class='fine'>Modeled planning scenario · not Duke's method · not an operational switching tool · details in Methods{cap_txt}</p>",
            unsafe_allow_html=True)

# ---------------------------------------------------------------- 4a. distribution strip
section(f"Compared with {n_plans} megawatts-only plans",
        "Many different plans meet the same megawatt target, so no single megawatts-only plan is the answer. Each grey dot is one of them; "
        "the blue circle is the vulnerability-aware plan.", "compare",
        ("Derived", "solved from modeled zone loads and public census, CDC, LBNL and LODES data; hover a dot for its value"))
st.markdown(f"<div class='honest'>{copy.range_line(dist)}<br/>{plain_summary(r)}</div>", unsafe_allow_html=True)
st.markdown("<div class='legend'><span><span class='sw' style='background:#6B7C96;border-radius:50%'></span>each megawatts-only plan</span>"
            "<span><span class='sw' style='background:#D5DDEB;transform:rotate(45deg)'></span>the typical one (left map)</span>"
            "<span><span class='sw' style='background:#6EA8FE;border-radius:50%'></span>vulnerability-aware plan</span></div>", unsafe_allow_html=True)
typ = {"electric_heat_households": r.baseline.electric_heat_households, "h_human": r.baseline.h_human,
       "h_econ": r.baseline.h_econ, "households": r.baseline.households}
wtd = {"electric_heat_households": r.weighted.electric_heat_households, "h_human": r.weighted.h_human,
       "h_econ": r.weighted.h_econ, "households": r.weighted.households}
vals = {k: lo_metrics[k].tolist() for k in typ}
specs = distribution.specs(vals, typ, wtd)
for row in (specs[:2], specs[2:]):
    for col, (title, spec) in zip(st.columns(2, gap="large"), row):
        with col, st.container(border=True):
            spec["height"] = 190
            st.vega_lite_chart(spec, width="stretch")
st.caption(distribution.caption(dist))

# ---------------------------------------------------------------- 4b. priority table
sens = A["sens"]
rows = pd.DataFrame(sens["rows"])
pcfg = cfg["priority_list"]
section("Vulnerable zones most often cut when only megawatts count",
        f"Zones with a CDC Social Vulnerability Index (SVI) of {pcfg['svi_min']:.2f} or more, or an electric-heat share of "
        f"{pcfg['electric_heat_min']:.0%} or more, ranked by how many of the {n_plans} megawatts-only plans cut them.", "priority",
        ("Derived", "SVI is CDC/ATSDR; electric-heat share is an American Community Survey estimate; cut counts come from the plan set"))
with st.container(border=True):
    body = "".join(
        f"<tr><td>{p['zone_id']}</td><td>{p['COUNTY'].replace(' County', '')}</td><td>{p['RPL_THEMES']:.2f}</td>"
        f"<td>{p['share_electric_heat']:.0%}</td><td>{p['occupied_units']:,.0f}</td>"
        f"<td>{p['loadonly_cut_share']:.0%} ({p['loadonly_cut_count']} of {n_plans})</td>"
        f"<td>{'Yes' if p['vuln_aware_cuts'] else 'No'} (cut in {p['vuln_aware_cut_settings']} of {p['n_settings']} settings)</td></tr>"
        for p in sens["priority_list"])
    st.markdown(f"<div class='prio'><table class='t'><tr><th>Zone</th><th>County</th><th>{copy.tip('SVI', 'SVI')}</th><th>Electric heat</th><th>Households</th>"
                f"<th>% of megawatts-only plans that cut it</th><th>Vulnerability-aware plan cuts it?</th></tr>{body}</table></div>", unsafe_allow_html=True)
    st.markdown("<p class='fine'><b>The megawatts-only plans are not a uniform sample of all such plans, so these frequencies are indicative, not exact.</b> "
                "This is what the model shows, not a finding about specific neighborhoods. Follow-ups to consider: outreach, backup-power "
                "planning, resilience-hub siting, request utility network data. Never a switching recommendation.</p>", unsafe_allow_html=True)
spared, cut_instead = copy.flip_lines(zh, r, H, lo_counts, n_plans)
with st.expander(f"All {len(spared) + len(cut_instead)} zones that differ between the two plans"):
    f1, f2 = st.columns(2, gap="large")
    with f1:
        st.markdown("<div class='flipcol'><h4>Kept on in the vulnerability-aware plan (cut in the typical megawatts-only plan)</h4>" +
                    "".join(f"<div class='flip'>{x}</div>" for x in spared) + "</div>", unsafe_allow_html=True)
    with f2:
        st.markdown("<div class='flipcol'><h4>Cut instead (kept on in the typical megawatts-only plan)</h4>" +
                    "".join(f"<div class='flip'>{x}</div>" for x in cut_instead) + "</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- 4c. look up a zone
section("Look up a zone", "Pick any zone to see its status under each plan and the arithmetic behind its score, or check three example public buildings.", "lookup",
        ("Modeled", "load is a modeled district estimate; household and job counts are ACS and LODES values"))
z1, z2 = st.columns([1, 1.25], gap="large")
with z1, st.container(border=True):
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
                    f"Typical megawatts-only plan: **{status(r.baseline)}** · Vulnerability-aware plan: **{status(r.weighted)}**  \n"
                    f"{lo_counts.get(zid, 0)} of {n_plans} megawatts-only plans cut this zone.")
        code = (
            f"inputs   households = {z['N_households']:,.0f}, SVI = {svi}, electric heat = {eh}, jobs = {z['jobs_total']:,.0f}\n"
            f"load     {z['L_mw']:.2f} MW (modeled) = district load x this zone's share of weight\n"
            f"         weight = {z['housing_units']:,.0f} units x {consts['kw_per_unit']:.2f} kW + {z['jobs_total']:,.0f} jobs x {consts['kw_per_job']:.2f} kW\n"
            f"people   at-risk score = households x ({ws} x SVI + {we} x heat) = {z['H_human']:,.1f}\n"
            f"cost     interruption cost = households x ${c_res} + jobs x ${c_job:.2f} = ${z['H_econ']:,.0f} (2013 dollars)\n"
            f"scaled   people {z['Hhat_human']:.3f}, cost {z['Hhat_econ']:.3f} (each scaled 0 to 1)\n"
            f"blend    {alpha:.2f} x {z['Hhat_human']:.3f} + {1 - alpha:.2f} x {z['Hhat_econ']:.3f} = {H.loc[zid]:.3f}")
        st.code(code, language=None, wrap_lines=True)
    else:
        st.caption("Select a zone to see its inputs and the formula with its numbers substituted.")
with z2, st.container(border=True):
    st.markdown("**Example locations**")
    st.markdown("<p class='fine'>Three example public buildings (no home addresses, no live geocoder), chosen to illustrate "
                "differences between the plans. Status is for the census tract zone the building sits in, under the current "
                "controls.</p>", unsafe_allow_html=True)
    lrows = lookup.lookup_rows(zones, cfg["example_locations"], r)
    st.markdown("<div class='loc'><table class='t'><tr><th>Location</th><th>Zone</th><th>Typical megawatts-only</th><th>Vulnerability-aware</th><th>Megawatts-only plans that cut it</th></tr>" + "".join(
        f"<tr><td>{x['label']}</td><td>{x['zone_id']}</td><td>{x['baseline']}</td><td>{x['weighted']}</td><td>{lo_counts.get(x['zone_id'], 0)} of {n_plans}</td></tr>" for x in lrows)
        + "</table></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- 4d. robustness
section("How robust is this?", f"We re-ran the comparison under {len(rows)} different settings of the controls and assumptions. Here is how often the result holds.", "robust",
        ("Calculated", "each setting re-solves both plans; changes are relative to that setting's typical megawatts-only plan"))
n = len(rows)
beat_h = int((rows["human_change_pct"] < 0).sum())
beat_c = int((rows["econ_change_pct"] < 0).sum())
more_hh = int((rows["households_change"] > 0).sum())
zero = rows[rows["human_change_pct"] >= 0]
pos = rows[rows["alpha"] > 0]
cap_row = rows[rows["county_cap"].notna()].iloc[0]
why = f" (the {len(zero)} that put all the weight on business cost, which ignores people at risk)" if len(zero) else ""
N = int(rows["n_plans"].iloc[0])
x1, x2 = st.columns([1, 1.1], gap="large")
with x1, st.container(border=True):
    st.markdown(
        f"<p style='margin:0'><b>{beat_h} of {n}</b> settings beat the typical megawatts-only plan on vulnerability-weighted households{why}; "
        f"<b>{beat_c} of {n}</b> on interruption cost (2013 dollars); in <b>{more_hh} of {n}</b> the vulnerability-aware plan "
        f"cuts <b>more</b> total households.</p>"
        f"<p class='fine'>Against all {N} megawatts-only plans, in the {len(pos)} settings that weigh people at risk at all it has fewer "
        f"vulnerability-weighted households than {int(pos['beats_human'].min())} to {int(pos['beats_human'].max())} of them and fewer electric-heat "
        f"households than {int(pos['beats_ehh'].min())} to {int(pos['beats_ehh'].max())}; on interruption cost it beats "
        f"{int(pos['beats_cost'].min())} to {int(pos['beats_cost'].max())} (cost matters less as the slider moves toward people at risk).</p>"
        f"<p class='fine'>With the {cap_share:.0%} county cap ON: vulnerability-weighted households {cap_row['human_change_pct']:+.0f}%, cost "
        f"{cap_row['econ_change_pct']:+.0f}%, {cap_row['households_change']:+,.0f} households (vs that setting's typical plan).</p>"
        f"<p class='fine'>Zones the vulnerability-aware plan cuts in every setting: {len(sens['classes']['always'])}; in some: "
        f"{len(sens['classes']['sometimes'])}; never: {len(sens['classes']['never'])}; protected: {len(sens['classes']['protected'])}.</p>",
        unsafe_allow_html=True)
with x2, st.container(border=True):
    st.markdown("**Moving the slider, plan by plan**")
    st.markdown("<div class='legend'><span><span class='sw' style='background:#6EA8FE;border-radius:50%'></span>vulnerability-weighted households</span>"
                "<span><span class='sw' style='background:#70E1C8;border-radius:50%'></span>interruption cost (2013 dollars)</span>"
                "<span><span class='sw' style='background:#F3BD69;border-radius:50%'></span>total households cut</span></div>", unsafe_allow_html=True)
    st.vega_lite_chart(distribution.tradeoff_spec(A["sweep"]), width="stretch")
    st.caption("Below zero = less. The plan cuts MORE total households at every slider position.")

# ---------------------------------------------------------------- 4e. demand panel (hidden if its frozen file is missing)
panel = A["panel"]
if panel:
    section("Why forecasts aren't enough", panel["label"], "forecast",
            ("Observed + modeled", "demand is observed EIA-930 data; the prediction line is this project's model, trained without the Elliott month"))
    pc1, pc2 = st.columns([1.7, 1], gap="large")
    with pc1, st.container(border=True):
        st.vega_lite_chart(demand_panel.chart_spec(panel), width="stretch")
    with pc2:
        st.markdown(f"<p class='honest'>{demand_panel.sentence(panel, demand_panel.total_shed_mw(consts))}</p>", unsafe_allow_html=True)
        st.markdown(f"<div class='tmp'>{demand_panel.temperature_table(panel)}</div>", unsafe_allow_html=True)
        st.markdown(f"<p class='fine'>{demand_panel.coldest_note(panel)}</p>", unsafe_allow_html=True)

# ---------------------------------------------------------------- 4f. methods & sources (everything technical)
st.markdown("<div class='sec' id='methods'></div>", unsafe_allow_html=True)
with st.expander("Methods & sources"):
    g = consts["groups"]
    st.markdown("**This is not Duke's method, not an operational switching tool, and the zones are census tracts, not utility "
                "boundaries.** Everything here is a planning scenario built from public data. Costs are in 2013 dollars.")
    st.markdown(f"**District scaling.** {provenance.DISTRICT_SENTENCE} Load is scaled from two utilities' balancing-authority demand "
                f"(Duke Energy Carolinas {g['DEC']['D_group_mw']:,.0f} MW and Duke Energy Progress {g['DEP']['D_group_mw']:,.0f} MW in the hour ending 07:00, that is 06:00 to 07:00; "
                f"EIA labels each hour by its end) using a modeled weight (housing units and jobs): D_NC08 = sum of D_utility x W_NC08-in-utility / W_utility = "
                f"{consts['D_NC08_mw']:,.0f} MW; required reduction T_NC08 = {consts['T_NC08_mw']:.1f} MW.")
    st.markdown(f"**Reduction ratio r.** {consts['r_definition']}. r (Carolinas) = {g['DEC']['r']:.4f}, r (Progress) = {g['DEP']['r']:.4f}.")
    band_word = copy.tip("target band", "target band", cfg)
    band_txt = f"Both plans cut between {r.band_lo_mw:.1f} and {r.band_hi_mw:.1f} MW"
    band_txt += f" ({band_word} widened to {r.delta_pct_used:.0f}% to find a solution)." if r.widened else f" ({band_word}: target plus {r.delta_pct_used:.0f}%)."
    st.markdown(f"**Shared target band.** {band_txt} Both plans must cut between T and T + delta, delta = {cfg['optimizer']['band_pct']:.0f}% of T "
                f"(widened to at most {max(cfg['optimizer']['band_widen_pct']):.0f}% if needed): load is shed in discrete blocks and operators cannot "
                "hit an exact MW.")
    st.markdown("**Controls.** The slider is a value judgment, not math: it blends two normalized scores per zone (vulnerability-weighted "
                "households and interruption cost); the settings used are alpha = 0 (business cost only) to 1 (people at risk only).")
    st.markdown(f"**Interruption cost.** Survey-based {copy.tip('Interruption Cost Estimate (ICE)', 'ICE')} values for a 1-hour interruption, in 2013 dollars (not inflated).",
                unsafe_allow_html=True)
    lo_meta = A["loadonly_method"]
    st.markdown(f"**Load-only comparison set.** Many different plans meet the MW target equally well, so one \"load-only baseline\" would be arbitrary. "
                f"The page compares against {n_plans} distinct plans that meet the target and overshoot it by at most {lo_meta['near_opt_pct']:.0f}% "
                f"(generated deterministically with a fixed seed and random zone costs; a wide cross-section of the near-optimal plans, not a uniform "
                f"sample). The left map shows the one closest to the median on four measures (households, electric-heat households, vulnerability-weighted "
                f"households, interruption cost). The vulnerability-aware plan is one optimum of its objective.")
    st.markdown(f"**Protected facilities.** Zones containing a hospital, nursing home or water treatment plant are never cut "
                f"({consts['n_protected']} zones, {consts['protected_load_mw'] / consts['D_NC08_mw']:.1%} of modeled load). This may protect more modeled load than necessary, and the OpenStreetMap facility "
                "data may be incomplete. Fire and police stations are not excluded (they commonly have backup generation).")
    st.markdown(f"**Data and map notes.** Scenario date {consts['scenario']['date']}; data built {consts['built_utc'][:10]}. Maps are drawn from the census tracts shown whole "
                "(the teal line is the NC-08 outline); hover a zone for its details.")
    for w in A["warnings"]:
        st.markdown(f"Data note: {w}")
    with st.expander("Stress test: all settings"):
        show = rows[["setting", "alpha", "w_svi", "human_change_pct", "econ_change_pct", "households_change"]].rename(columns={
            "human_change_pct": "human harm %", "econ_change_pct": "cost % (2013$)", "households_change": "households cut +/-"})
        st.dataframe(show.round(1), hide_index=True, width="stretch")
    st.markdown(f"**Critical facilities.** {consts['n_protected']} zones with a hospital, nursing home or water treatment plant are never cut; the facility data may be incomplete.")
    st.markdown("**Sources**", unsafe_allow_html=True)
    st.markdown(provenance.datasets_table(consts), unsafe_allow_html=True)
    st.markdown("**Where each number on this page comes from**", unsafe_allow_html=True)
    st.markdown(provenance.number_sources_table(consts), unsafe_allow_html=True)
