from datetime import datetime

import streamlit as st

from odoo_import.lead_service import (
    add_audit_trail,
    build_vals_from_answers,
    create_new_lead,
    update_existing_lead,
)
from odoo_import.odoo_client import create_activity_for_lead
from odoo_streamlit.debug import add_debug_event
from odoo_streamlit.local_draft import mark_local_draft_sent, save_local_draft
from odoo_streamlit.services import get_odoo
from odoo_streamlit.state import request_full_reset


def create_lead(vals):
    uid, models = get_odoo()
    return create_new_lead(models, uid, vals)


def update_lead(lead_id, vals):
    uid, models = get_odoo()
    return update_existing_lead(models, uid, lead_id, vals)


def create_activity_after_lead(lead_id, vals):
    """
    Crée l'activité si un payload activité est présent dans vals.
    Retourne un dict uniforme pour simplifier les messages UI.
    """
    activity_vals = (vals or {}).get("_activity_vals")
    if not activity_vals:
        return {
            "created": False,
            "activity_id": None,
            "message": "Aucune activité à créer.",
        }

    uid, _models = get_odoo()
    activity_id = create_activity_for_lead(uid, lead_id, activity_vals)

    return {
        "created": True,
        "activity_id": activity_id,
        "message": f"Activité créée (ID {activity_id}).",
    }


def process_duplicate_action(action, preview_data, existing_data, existing_id, team_id):
    if action == "Mettre à jour le lead existant":
        vals = build_vals_from_answers(
            preview_data,
            team_id,
            st.session_state["seller_user_id"],
            replace_tags=False,
            existing_description=existing_data.get("description") if existing_data else None,
        )
        vals = add_audit_trail(
            vals,
            actor_user=st.session_state.get("auth_user", ""),
            seller_name=st.session_state.get("seller_name", ""),
            mode="mise à jour lead existant",
        )

        _preserve_draft(preview_data, vals)
        add_debug_event("lead_update_started", {"existing_id": existing_id})

        with st.spinner("Mise à jour Odoo en cours. Ne fermez pas cette page..."):
            result = update_lead(existing_id, vals)

        if result.success:
            activity_feedback = _try_create_activity(existing_id, vals)

            if activity_feedback["status"] == "created":
                _set_banner(
                    "success",
                    (
                        f"Piste bien prise en compte par Odoo. Mise à jour confirmée (ID {result.lead_id}). "
                        f"Activité créée (ID {activity_feedback['activity_id']})."
                    ),
                )
            elif activity_feedback["status"] == "error":
                _set_banner(
                    "warning",
                    (
                        f"Piste mise à jour dans Odoo (ID {result.lead_id}), "
                        f"mais l'activité n'a pas pu être créée : {activity_feedback['message']}"
                    ),
                )
            else:
                _set_banner(
                    "success",
                    f"Piste bien prise en compte par Odoo. Mise à jour confirmée (ID {result.lead_id}).",
                )

            add_debug_event("lead_update_success", {"lead_id": result.lead_id})
            _clear_draft_after_success(result.lead_id, preview_data)
            request_full_reset(clear_banner=False)
            st.rerun()

        _set_banner(
            "warning",
            (
                "La mise à jour n'a pas été confirmée dans Odoo. "
                "Votre saisie a été conservée. Vous pouvez réessayer. "
                f"Détail : {result.message}"
            ),
        )
        add_debug_event("lead_update_failed", {"existing_id": existing_id, "message": result.message})
        st.rerun()

    elif action == "Créer un nouveau lead quand même":
        vals = build_vals_from_answers(
            preview_data,
            team_id,
            st.session_state["seller_user_id"],
            replace_tags=True,
            existing_description=None,
        )
        vals = add_audit_trail(
            vals,
            actor_user=st.session_state.get("auth_user", ""),
            seller_name=st.session_state.get("seller_name", ""),
            mode="création nouveau lead malgré doublon",
        )

        _preserve_draft(preview_data, vals)
        add_debug_event("lead_create_despite_duplicate_started", {"existing_id": existing_id})

        with st.spinner("Envoi vers Odoo en cours. Ne fermez pas cette page..."):
            result = create_lead(vals)

        if result.success:
            activity_feedback = _try_create_activity(result.lead_id, vals)

            if activity_feedback["status"] == "created":
                _set_banner(
                    "success",
                    (
                        f"Piste bien prise en compte par Odoo. Nouveau lead créé et confirmé (ID {result.lead_id}). "
                        f"Activité créée (ID {activity_feedback['activity_id']})."
                    ),
                )
            elif activity_feedback["status"] == "error":
                _set_banner(
                    "warning",
                    (
                        f"Lead créé dans Odoo (ID {result.lead_id}), "
                        f"mais l'activité n'a pas pu être créée : {activity_feedback['message']}"
                    ),
                )
            else:
                _set_banner(
                    "success",
                    f"Piste bien prise en compte par Odoo. Nouveau lead créé et confirmé (ID {result.lead_id}).",
                )

            add_debug_event("lead_create_despite_duplicate_success", {"lead_id": result.lead_id})
            _clear_draft_after_success(result.lead_id, preview_data)
            request_full_reset(clear_banner=False)
            st.rerun()

        _set_banner(
            "warning",
            (
                "La création n'a pas été confirmée dans Odoo. "
                "Votre saisie a été conservée. Vous pouvez réessayer. "
                f"Détail : {result.message}"
            ),
        )
        add_debug_event("lead_create_despite_duplicate_failed", {"message": result.message})
        st.rerun()

    else:
        _set_banner(
            "warning",
            "Opération annulée. Aucune piste n'a été créée ni modifiée.",
        )
        add_debug_event("duplicate_action_cancelled", {"existing_id": existing_id})
        request_full_reset(clear_banner=False)
        st.rerun()


def process_create_action(preview_data, team_id):
    vals = build_vals_from_answers(
        preview_data,
        team_id,
        st.session_state["seller_user_id"],
        replace_tags=True,
        existing_description=None,
    )
    vals = add_audit_trail(
        vals,
        actor_user=st.session_state.get("auth_user", ""),
        seller_name=st.session_state.get("seller_name", ""),
        mode="création lead",
    )

    _preserve_draft(preview_data, vals)
    add_debug_event("lead_create_started", {"partner_name": preview_data.get("partner_name"), "city": preview_data.get("city")})

    with st.spinner("Envoi vers Odoo en cours. Ne fermez pas cette page..."):
        result = create_lead(vals)

    if result.success:
        activity_feedback = _try_create_activity(result.lead_id, vals)

        if activity_feedback["status"] == "created":
            _set_banner(
                "success",
                (
                    f"Piste bien prise en compte par Odoo. Création confirmée (ID {result.lead_id}). "
                    f"Activité créée (ID {activity_feedback['activity_id']})."
                ),
            )
        elif activity_feedback["status"] == "error":
            _set_banner(
                "warning",
                (
                    f"Lead créé dans Odoo (ID {result.lead_id}), "
                    f"mais l'activité n'a pas pu être créée : {activity_feedback['message']}"
                ),
            )
        else:
            _set_banner(
                "success",
                f"Piste bien prise en compte par Odoo. Création confirmée (ID {result.lead_id}).",
            )

        add_debug_event("lead_create_success", {"lead_id": result.lead_id})
        _clear_draft_after_success(result.lead_id, preview_data)
        request_full_reset(clear_banner=False)
        st.rerun()

    _set_banner(
        "warning",
        (
            "La création n'a pas été confirmée dans Odoo. "
            "Votre saisie a été conservée. Vous pouvez réessayer. "
            f"Détail : {result.message}"
        ),
    )
    add_debug_event("lead_create_failed", {"message": result.message})
    st.rerun()


def _preserve_draft(preview_data, vals):
    draft = dict(preview_data or {})
    st.session_state["last_unsent_draft"] = draft
    st.session_state["last_unsent_vals"] = dict(vals or {})
    save_local_draft(draft, status="unsent")


def _clear_draft_after_success(lead_id, preview_data=None):
    sent_draft = dict(preview_data or {}) if preview_data else None
    st.session_state["last_created_lead_id"] = lead_id
    st.session_state["last_sent_draft"] = sent_draft
    st.session_state["last_sent_lead_id"] = lead_id
    st.session_state["last_sent_at"] = datetime.now().isoformat(timespec="seconds")
    st.session_state["last_unsent_draft"] = None
    st.session_state["last_unsent_vals"] = None
    st.session_state["draft_restored"] = False
    if sent_draft:
        mark_local_draft_sent(sent_draft, lead_id=lead_id)


def _try_create_activity(lead_id, vals):
    """
    Ne casse pas le flux lead si l'activité échoue.
    """
    activity_vals = (vals or {}).get("_activity_vals")
    if not activity_vals:
        return {
            "status": "none",
            "activity_id": None,
            "message": "Aucune activité demandée.",
        }

    try:
        result = create_activity_after_lead(lead_id, vals)
        if result["created"]:
            return {
                "status": "created",
                "activity_id": result["activity_id"],
                "message": result["message"],
            }
        return {
            "status": "none",
            "activity_id": None,
            "message": result["message"],
        }
    except Exception as exc:
        return {
            "status": "error",
            "activity_id": None,
            "message": str(exc),
        }


def _set_banner(status, message):
    st.session_state["result_banner"] = {
        "status": status,
        "message": message,
    }
