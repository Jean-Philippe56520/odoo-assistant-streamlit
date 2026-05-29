from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from odoo_streamlit.actions import process_create_action, process_duplicate_action
from odoo_streamlit.constants import FORM_FIELD_KEYS
from odoo_streamlit.debug import add_debug_event
from odoo_streamlit.local_draft import (
    clear_local_draft,
    init_local_draft_storage,
    refresh_local_draft_state,
    save_local_draft,
)
from odoo_streamlit.auth import render_logout, require_simple_auth
from odoo_streamlit.constants import APP_STATE_KEYS
from odoo_streamlit.forms import render_lead_form, validate_form
from odoo_streamlit.services import compute_preview, get_odoo, get_sales_users, get_team_id
from odoo_streamlit.state import apply_pending_resets, init_state, request_preview_reset
from odoo_streamlit.views import (
    render_banner,
    render_debug_events,
    render_draft_recovery,
    render_last_sent_recovery,
    render_local_draft_recovery,
    render_scroll_to_top_if_requested,
    render_page_header,
    show_existing,
    show_preview,
)

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


def restore_last_unsent_draft(draft):
    st.session_state["form_data"] = dict(draft)

    for key in FORM_FIELD_KEYS:
        if key in draft:
            st.session_state[key] = draft[key]

    st.session_state["draft_restored"] = True
    st.session_state["result_banner"] = {
        "status": "warning",
        "message": "Brouillon restauré. Vérifiez les informations avant de prévisualiser à nouveau.",
    }
    add_debug_event("draft_restored", {"partner_name": draft.get("partner_name"), "city": draft.get("city")})
    request_preview_reset()
    st.rerun()


def ignore_last_unsent_draft():
    st.session_state["last_unsent_draft"] = None
    st.session_state["last_unsent_vals"] = None
    st.session_state["draft_restored"] = False
    st.session_state["available_local_draft"] = None
    clear_local_draft()
    add_debug_event("draft_ignored")
    st.rerun()


def restore_local_draft(payload):
    data = dict((payload or {}).get("data") or {})
    if not data:
        return

    st.session_state["form_data"] = data
    st.session_state["last_unsent_draft"] = data

    for key in FORM_FIELD_KEYS:
        if key in data:
            st.session_state[key] = data[key]

    status = (payload or {}).get("status")
    lead_id = (payload or {}).get("lead_id")
    if status == "sent" and lead_id:
        message = (
            f"Dernière saisie envoyée restaurée. Attention : cette piste a déjà été "
            f"confirmée dans Odoo avec l'ID {lead_id}. Vérifiez avant de recréer."
        )
    else:
        message = "Brouillon local restauré. Vérifiez les informations avant de prévisualiser à nouveau."

    st.session_state["draft_restored"] = True
    st.session_state["result_banner"] = {"status": "warning", "message": message}
    add_debug_event(
        "local_draft_restored",
        {"status": status, "lead_id": lead_id, "partner_name": data.get("partner_name"), "city": data.get("city")},
    )
    request_preview_reset()
    st.rerun()


def forget_last_sent_draft():
    st.session_state["last_sent_draft"] = None
    st.session_state["last_sent_lead_id"] = None
    st.session_state["last_sent_at"] = None
    st.session_state["available_local_draft"] = None
    # Quand l'utilisateur masque la reprise, on supprime aussi la copie navigateur
    # pour éviter de réafficher le bloc au rechargement.
    clear_local_draft()
    add_debug_event("last_sent_draft_hidden")
    st.rerun()


def delete_local_draft():
    clear_local_draft()
    st.session_state["last_sent_draft"] = None
    st.session_state["last_sent_lead_id"] = None
    st.session_state["last_sent_at"] = None
    st.session_state["last_unsent_draft"] = None
    st.session_state["last_unsent_vals"] = None
    add_debug_event("local_draft_deleted")
    st.rerun()


require_simple_auth()
render_logout(APP_STATE_KEYS)

init_state()
local_draft_storage = init_local_draft_storage()
refresh_local_draft_state(local_draft_storage)
apply_pending_resets()

render_page_header()
render_banner()
render_form_messages()
render_scroll_to_top_if_requested()
render_local_draft_recovery(restore_local_draft, delete_local_draft)
if not st.session_state.get("available_local_draft"):
    render_draft_recovery(restore_last_unsent_draft, ignore_last_unsent_draft)
if not st.session_state.get("available_local_draft") and not st.session_state.get("last_unsent_draft"):
    render_last_sent_recovery(restore_local_draft, forget_last_sent_draft)

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
    st.session_state["last_unsent_draft"] = dict(raw_data)
    save_local_draft(raw_data, status="unsent", storage=local_draft_storage)
    st.session_state["form_errors"] = []
    st.session_state["form_warnings"] = []
    add_debug_event("preview_submitted", {"partner_name": raw_data.get("partner_name"), "city": raw_data.get("city")})

    blocking_errors, warnings, clean_data = validate_form(raw_data)

    if blocking_errors:
        st.session_state["form_errors"] = blocking_errors
        st.session_state["form_warnings"] = warnings
        st.session_state["scroll_to_top_requested"] = True
        request_preview_reset()
        st.rerun()

    try:
        with st.spinner("Prévisualisation en cours. Ne fermez pas cette page..."):
            preview = compute_preview(
                clean_data,
                seller_name,
                seller_options[seller_name],
                actor_user=st.session_state.get("auth_user", ""),
            )
    except Exception as exc:
        st.session_state["form_errors"] = [
            "La prévisualisation n'a pas pu être générée. Votre saisie a été conservée."
        ]
        st.session_state["form_warnings"] = warnings
        st.session_state["scroll_to_top_requested"] = True
        add_debug_event("preview_exception", {"message": str(exc)})
        request_preview_reset()
        st.rerun()

    if not preview.is_valid:
        st.session_state["form_errors"] = preview.errors or ["La prévisualisation a échoué."]
        st.session_state["form_warnings"] = warnings
        st.session_state["scroll_to_top_requested"] = True
        add_debug_event("preview_failed", {"errors": st.session_state["form_errors"]})
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
    add_debug_event("preview_success", {"existing_id": st.session_state["existing_id"]})

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


render_debug_events()
