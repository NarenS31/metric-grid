"""METRIC-Grid Streamlit app. Phase 3 shell: loads only data/frozen/ and shows the scaled scenario.

The full two-map comparison UI arrives in Phase 4. Nothing here touches the network.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # src/, so `streamlit run` works without PYTHONPATH

import streamlit as st

from metric_grid import frozen

DISTRICT_SENTENCE = ("The Elliott regional event anchors this scenario. NC-08 load and required reduction are modeled "
                     "district-scale estimates, not observed utility circuit values.")

consts = frozen.load_constants()
zones = frozen.load_zones()

st.title("METRIC-Grid")
st.subheader("Same target, different burden.")
st.caption("Public-data planning simulator, not an operational switching tool.")
st.markdown(f"**Modeled scenario** · {consts['scenario']['name']} · built {consts['built_utc'][:10]}")
st.info(DISTRICT_SENTENCE)
c1, c2, c3 = st.columns(3)
c1.metric("Modeled NC-08 load (07:00)", f"{consts['D_NC08_mw']:,.0f} MW", help="modeled district estimate")
c2.metric("Modeled required reduction", f"{consts['T_NC08_mw']:.1f} MW", help="modeled district estimate")
c3.metric("Zones (protected)", f"{consts['n_zones']} ({consts['n_protected']})", help=consts["zone_note"])
st.caption(f"Zones are {consts['zone_note']}. Phase 3 shell: maps and plans come in Phase 4.")
