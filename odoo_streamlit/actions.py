import streamlit as st

from odoo_import.lead_service import add_audit_trail, build_vals_from_answers, create_new_lead, update_existing_lead
from odoo_streamlit.services import get_odoo
from odoo_streamlit.state import request_full_reset


def create_lead(vals):
    uid, models = get_odoo()
    return create_new_lead(models, uid, vals)


def update_lead(lead_id, vals):
    uid, models = get_odoo()
    return update_existing_lead(models, uid, lead_id, vals)


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

        if result.success:
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


def _set_banner(status, message):
    st.session_state["result_banner"] = {
        "status": status,
        "message": message,
    }
