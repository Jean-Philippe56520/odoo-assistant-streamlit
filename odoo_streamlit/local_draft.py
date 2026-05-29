from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

import streamlit as st

from odoo_streamlit.constants import (
    FORM_FIELD_KEYS,
    LOCAL_DRAFT_KEY,
    LOCAL_DRAFT_STORAGE_COMPONENT_KEY,
    LOCAL_DRAFT_TTL_DAYS,
)

try:
    from streamlit_local_storage import LocalStorage
except Exception:  # pragma: no cover - fallback si la dépendance n'est pas installée
    LocalStorage = None


LOCAL_DRAFT_VERSION = 1
_STORAGE_SESSION_KEY = "_abm_local_draft_storage"


def init_local_draft_storage():
    """Initialise le composant localStorage et le garde en session."""
    if LocalStorage is None:
        st.session_state["local_draft_available"] = False
        st.session_state["local_draft_error"] = "Dépendance streamlit-local-storage indisponible."
        return None

    try:
        if _STORAGE_SESSION_KEY not in st.session_state:
            st.session_state[_STORAGE_SESSION_KEY] = LocalStorage(key=LOCAL_DRAFT_STORAGE_COMPONENT_KEY)
        st.session_state["local_draft_available"] = True
        return st.session_state[_STORAGE_SESSION_KEY]
    except Exception as exc:
        # Le stockage local est une couche de confort : il ne doit jamais bloquer l'app.
        st.session_state["local_draft_available"] = False
        st.session_state["local_draft_error"] = str(exc)
        return None


def refresh_local_draft_state(storage=None) -> dict[str, Any] | None:
    """Charge le brouillon local navigateur et le place en session_state."""
    payload = load_local_draft(storage=storage)
    st.session_state["available_local_draft"] = payload
    return payload


def save_local_draft(data: dict[str, Any] | None, status: str = "unsent", lead_id: int | None = None, storage=None) -> None:
    """Sauvegarde la dernière saisie dans le localStorage du navigateur."""
    if not data:
        return

    storage = storage or st.session_state.get(_STORAGE_SESSION_KEY) or init_local_draft_storage()
    if storage is None:
        return

    now = datetime.now()
    payload = {
        "version": LOCAL_DRAFT_VERSION,
        "status": status,
        "lead_id": lead_id,
        "saved_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(days=LOCAL_DRAFT_TTL_DAYS)).isoformat(timespec="seconds"),
        "data": _serialize_form_data(data),
    }

    try:
        storage.setItem(
            LOCAL_DRAFT_KEY,
            json.dumps(payload, ensure_ascii=False),
            key=f"set_{LOCAL_DRAFT_KEY}_{int(now.timestamp() * 1000)}",
        )
        st.session_state["available_local_draft"] = payload
    except Exception as exc:
        st.session_state["local_draft_error"] = str(exc)


def mark_local_draft_sent(data: dict[str, Any] | None, lead_id: int | None, storage=None) -> None:
    save_local_draft(data=data, status="sent", lead_id=lead_id, storage=storage)


def load_local_draft(storage=None) -> dict[str, Any] | None:
    storage = storage or st.session_state.get(_STORAGE_SESSION_KEY) or init_local_draft_storage()
    if storage is None:
        return None

    try:
        raw = storage.getItem(LOCAL_DRAFT_KEY)
    except Exception as exc:
        st.session_state["local_draft_error"] = str(exc)
        return None

    if not raw:
        return None

    if isinstance(raw, dict):
        payload = raw
    else:
        try:
            payload = json.loads(raw)
        except Exception:
            clear_local_draft(storage=storage)
            return None

    if not isinstance(payload, dict):
        clear_local_draft(storage=storage)
        return None

    if _is_expired(payload):
        clear_local_draft(storage=storage)
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        clear_local_draft(storage=storage)
        return None

    payload["data"] = _deserialize_form_data(data)
    return payload


def clear_local_draft(storage=None) -> None:
    storage = storage or st.session_state.get(_STORAGE_SESSION_KEY) or init_local_draft_storage()
    if storage is None:
        st.session_state["available_local_draft"] = None
        return

    try:
        storage.deleteItem(LOCAL_DRAFT_KEY, key=f"delete_{LOCAL_DRAFT_KEY}_{int(datetime.now().timestamp() * 1000)}")
    except Exception:
        try:
            storage.eraseItem(LOCAL_DRAFT_KEY, key=f"erase_{LOCAL_DRAFT_KEY}_{int(datetime.now().timestamp() * 1000)}")
        except Exception as exc:
            st.session_state["local_draft_error"] = str(exc)

    st.session_state["available_local_draft"] = None


def _serialize_form_data(data: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for key in FORM_FIELD_KEYS:
        value = data.get(key)
        if isinstance(value, (date, datetime)):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def _deserialize_form_data(data: dict[str, Any]) -> dict[str, Any]:
    restored: dict[str, Any] = {}
    for key in FORM_FIELD_KEYS:
        value = data.get(key)
        if key == "activity_custom_date" and isinstance(value, str) and value:
            try:
                restored[key] = date.fromisoformat(value[:10])
            except ValueError:
                restored[key] = value
        else:
            restored[key] = value
    return restored


def _is_expired(payload: dict[str, Any]) -> bool:
    expires_at = payload.get("expires_at")
    if not expires_at:
        return False

    try:
        return datetime.fromisoformat(expires_at) < datetime.now()
    except Exception:
        return False
