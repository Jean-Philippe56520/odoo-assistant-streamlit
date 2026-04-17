from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from odoo_streamlit.constants import (
    DEFAULT_ACTIVITY_DATE_MODE,
    DEFAULT_ACTIVITY_SUMMARY,
    DEFAULT_ACTIVITY_TYPE,
    DEFAULT_DUPLICATE_ACTION,
    FORM_FIELD_KEYS,
)


def empty_form_data() -> dict:
    """
    Valeurs par défaut du formulaire principal.

    Important :
    - le bloc activité reste optionnel
    - mais lorsqu'il est activé, il doit déjà avoir des valeurs cohérentes
    """
    return {
        "partner_name": "",
        "contact_name": "",
        "phone": "",
        "mobile": "",
        "email_from": "",
        "street": "",
        "street2": "",
        "zip": "",
        "city": "",
        "current_equipment": "",
        "free_comment": "",
        "create_activity": False,
        "activity_type": DEFAULT_ACTIVITY_TYPE,
        "activity_summary": DEFAULT_ACTIVITY_SUMMARY,
        "activity_date_mode": DEFAULT_ACTIVITY_DATE_MODE,
        "activity_custom_date": date.today() + timedelta(days=7),
    }


def init_state():
    """
    Initialise la session Streamlit.
    """
    defaults = {
        "form_data": empty_form_data(),
        "preview_data": None,
        "preview_vals": None,
        "existing_id": None,
        "existing_data": None,
        "seller_name": None,
        "seller_user_id": None,
        "result_banner": None,
        "pending_form_reset": False,
        "pending_preview_reset": False,
        "form_errors": [],
        "form_warnings": [],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    _ensure_form_widget_defaults()


def apply_pending_resets():
    """
    Applique les resets différés après action utilisateur.
    """
    if st.session_state.get("pending_form_reset"):
        _reset_form_and_preview_state()
        _reset_form_widgets()
        st.session_state["pending_form_reset"] = False
        st.session_state["pending_preview_reset"] = False

    elif st.session_state.get("pending_preview_reset"):
        _reset_preview_state()
        st.session_state["pending_preview_reset"] = False


def request_preview_reset():
    """
    Demande l'effacement de la prévisualisation sans effacer la saisie.
    """
    st.session_state["pending_preview_reset"] = True


def request_full_reset(clear_banner: bool = False):
    """
    Demande l'effacement complet du formulaire et de la prévisualisation.
    """
    if clear_banner:
        st.session_state["result_banner"] = None
    st.session_state["pending_form_reset"] = True


def _reset_form_and_preview_state():
    st.session_state["form_data"] = empty_form_data()
    st.session_state["form_errors"] = []
    st.session_state["form_warnings"] = []
    _reset_preview_state()


def _reset_preview_state():
    st.session_state["preview_data"] = None
    st.session_state["preview_vals"] = None
    st.session_state["existing_id"] = None
    st.session_state["existing_data"] = None
    st.session_state["seller_name"] = None
    st.session_state["seller_user_id"] = None
    st.session_state["confirm_existing"] = False
    st.session_state["duplicate_action_radio"] = DEFAULT_DUPLICATE_ACTION


def _reset_form_widgets():
    """
    Réinitialise les widgets Streamlit visibles.
    """
    defaults = empty_form_data()

    for key in FORM_FIELD_KEYS:
        st.session_state[key] = defaults[key]

    st.session_state["form_errors"] = []
    st.session_state["form_warnings"] = []
    st.session_state["confirm_existing"] = False
    st.session_state["duplicate_action_radio"] = DEFAULT_DUPLICATE_ACTION

    if "seller_selectbox" in st.session_state:
        del st.session_state["seller_selectbox"]


def _ensure_form_widget_defaults():
    """
    S'assure que tous les widgets du formulaire ont une valeur cohérente,
    y compris après évolution du schéma du formulaire.
    """
    defaults = empty_form_data()

    for key in FORM_FIELD_KEYS:
        if key not in st.session_state:
            st.session_state[key] = defaults[key]

    if "confirm_existing" not in st.session_state:
        st.session_state["confirm_existing"] = False

    if "duplicate_action_radio" not in st.session_state:
        st.session_state["duplicate_action_radio"] = DEFAULT_DUPLICATE_ACTION
