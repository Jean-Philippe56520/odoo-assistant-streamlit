from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from odoo_streamlit.actions import process_create_action, process_duplicate_action
from odoo_streamlit.auth import render_logout, require_simple_auth
from odoo_streamlit.constants import APP_STATE_KEYS
from odoo_streamlit.forms import render_lead_form, validate_form
from odoo_streamlit.services import compute_preview, get_odoo, get_sales_users, get_team_id
from odoo_streamlit.state import apply_pending_resets, init_state, request_preview_reset
from odoo_streamlit.views import render_banner, render_page_header, show_existing, show_preview

st.set_page_config(page_title="Saisie prospection Odoo V2", layout="centered")


def render_form_messages():
    errors = st.session_state.get("form_errors") or []
    warnings = st.session_state.get("form_warnings") or []

    if errors:
        st.error("Prévisualisation bloquée : corrigez les points suivants.")
        for error in errors:
            st.write(f"- {error}")

    if warnings:
        st.warning("Prévisualisation autorisée, mais vérifiez les points suivants.")
        for warning in warnings:
            st.write(f"- {warning}")


require_simple_auth()
render_logout(APP_STATE_KEYS)

init_state()
apply_pending_resets()

render_page_header()
render_banner()
render_form_messages()

try:
    uid, models = get_odoo()
    sales_users = get_sales_users()
    team_id = get_team_id()
except Exception as e:
    st.error(f"Erreur de connexion à Odoo : {e}")
    st.stop()

if not sales_users:
    st.error("Aucun vendeur actif n'a été trouvé dans Odoo.")
    st.stop()

seller_options = {user["name"]: user["id"] for user in sales_users}
seller_names = list(seller_options.keys())

submitted, seller_name, raw_data = render_lead_form(seller_names)

if submitted:
    st.session_state["result_banner"] = None
    st.session_state["form_data"] = raw_data
    st.session_state["form_errors"] = []
    st.session_state["form_warnings"] = []

    blocking_errors, warnings, clean_data = validate_form(raw_data)

    if blocking_errors:
        st.session_state["form_errors"] = blocking_errors
        st.session_state["form_warnings"] = warnings
        request_preview_reset()
        st.rerun()

    preview = compute_preview(
        clean_data,
        seller_name,
        seller_options[seller_name],
        actor_user=st.session_state.get("auth_user", ""),
    )

    if not preview.is_valid:
        st.session_state["form_errors"] = preview.errors or ["La prévisualisation a échoué."]
        st.session_state["form_warnings"] = warnings
        request_preview_reset()
        st.rerun()

    st.session_state["preview_data"] = preview.cleaned_data
    st.session_state["preview_vals"] = preview.vals
    st.session_state["existing_id"] = preview.existing_match.lead_id if preview.existing_match else None
    st.session_state["existing_data"] = preview.existing_match.summary if preview.existing_match else None
    st.session_state["seller_name"] = seller_name
    st.session_state["seller_user_id"] = seller_options[seller_name]
    st.session_state["form_errors"] = []
    st.session_state["form_warnings"] = warnings

    st.rerun()

preview_data = st.session_state.get("preview_data")
preview_vals = st.session_state.get("preview_vals")
existing_id = st.session_state.get("existing_id")
existing_data = st.session_state.get("existing_data")
seller_name = st.session_state.get("seller_name")

if preview_data and preview_vals:
    st.divider()
    show_preview(preview_vals, preview_data, seller_name)

    if existing_id:
        st.warning(f"Un lead similaire existe déjà (ID {existing_id}).")
        st.caption(
            "Le système signale une similarité. Vous décidez ensuite de mettre à jour, "
            "créer quand même, ou annuler."
        )

        show_existing(existing_data)

        action = st.radio(
            "Choisissez une action",
            (
                "Mettre à jour le lead existant",
                "Créer un nouveau lead quand même",
                "Annuler",
            ),
            key="duplicate_action_radio",
        )

        confirm = st.checkbox("Je confirme cette action", key="confirm_existing")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Valider l'action", type="primary", key="validate_existing_action"):
                if not confirm:
                    st.error("Merci de confirmer l'action.")
                else:
                    process_duplicate_action(
                        action=action,
                        preview_data=preview_data,
                        existing_data=existing_data,
                        existing_id=existing_id,
                        team_id=team_id,
                    )

        with col2:
            if st.button("Revenir à la saisie", key="back_to_form_existing"):
                request_preview_reset()
                st.rerun()

    else:
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Créer la piste", type="primary", key="create_new_lead"):
                process_create_action(preview_data, team_id)

        with col2:
            if st.button("Modifier la saisie", key="back_to_form_create"):
                request_preview_reset()
                st.rerun()
