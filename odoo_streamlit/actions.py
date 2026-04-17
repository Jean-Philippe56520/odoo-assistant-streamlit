import streamlit as st

from odoo_import.lead_service import (
    add_audit_trail,
    build_vals_from_answers,
    create_new_lead,
    update_existing_lead,
)
from odoo_import.odoo_client import create_activity_for_lead
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

        result = update_lead(existing_id, vals)

        activity_feedback = _try_create_activity(existing_id, vals)

        if result.success:
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
        else:
            _set_banner(
                "warning",
                f"Mise à jour envoyée, mais confirmation Odoo incomplète. {result.message}",
            )

        request_full_reset(clear_banner=False)
        st.rerun()

    if action == "Créer un nouveau lead quand même":
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
        else:
            _set_banner(
                "warning",
                f"Création envoyée, mais confirmation Odoo incomplète. {result.message}",
            )

        request_full_reset(clear_banner=False)
        st.rerun()

    _set_banner(
        "warning",
        "Opération annulée. Aucune piste n'a été créée ni modifiée.",
    )
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
    else:
        _set_banner(
            "warning",
            (
                "La création a été lancée, mais la confirmation Odoo n'a pas pu être relue. "
                f"{result.message}"
            ),
        )

    request_full_reset(clear_banner=False)
    st.rerun()


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
