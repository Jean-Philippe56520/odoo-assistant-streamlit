from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st


def add_debug_event(event: str, payload: dict[str, Any] | None = None) -> None:
    """
    Conserve un journal court en session pour diagnostiquer les incidents terrain.

    Le journal reste volontairement local à la session Streamlit : il n'écrit pas
    de données personnelles sur disque et ne modifie pas les appels Odoo.
    """
    events = st.session_state.get("debug_events") or []
    events.append(
        {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "payload": payload or {},
        }
    )
    st.session_state["debug_events"] = events[-20:]
