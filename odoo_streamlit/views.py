from __future__ import annotations

from datetime import date, datetime
from typing import Any

import streamlit as st

from odoo_import.lead_service import PROSPECTION_TAG, build_title
from odoo_streamlit.constants import APP_CAPTION, APP_TITLE


def render_page_header():
    st.title(APP_TITLE)
    st.caption(APP_CAPTION)


def render_banner():
    banner = st.session_state.get("result_banner")
    if not banner:
        return

    if banner["status"] == "success":
        st.success(banner["message"], icon="✅")
    elif banner["status"] == "warning":
        st.warning(banner["message"], icon="⚠️")
    else:
        st.error(banner["message"], icon="❌")


def show_existing(existing):
    st.markdown("### Lead détecté")
    if not existing:
        st.warning("Impossible de lire le détail du lead détecté.")
        return

    seller = "-"
    user_id = existing.get("user_id")
    if isinstance(user_id, list) and len(user_id) >= 2:
        seller = user_id[1]

    st.write(f"**Titre :** {existing.get('name') or '-'}")
    st.write(f"**Société :** {existing.get('partner_name') or '-'}")
    st.write(f"**Contact :** {existing.get('contact_name') or '-'}")
    st.write(f"**Email :** {existing.get('email_from') or '-'}")
    st.write(f"**Téléphone :** {existing.get('phone') or '-'}")
    st.write(f"**Mobile :** {existing.get('mobile') or '-'}")
    st.write(f"**Vendeur actuel :** {seller}")

    description = existing.get("description")
    if description:
        with st.expander("Description actuelle du lead", expanded=False):
            st.text(description)


def show_preview(preview_vals, raw_data, seller_name):
    st.subheader("Prévisualisation")

    st.write(f"**Compte connecté :** {st.session_state.get('auth_user') or '-'}")
    st.write(f"**Commercial :** {seller_name}")
    st.write(f"**Titre :** {build_title(raw_data)}")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Contact")
        st.write(f"**Entreprise :** {raw_data.get('partner_name') or '-'}")
        st.write(f"**Contact :** {raw_data.get('contact_name') or '-'}")
        st.write(f"**Téléphone :** {raw_data.get('phone') or '-'}")
        st.write(f"**Mobile :** {raw_data.get('mobile') or '-'}")
        st.write(f"**Email :** {raw_data.get('email_from') or '-'}")

    with col2:
        st.markdown("#### Adresse")
        st.write(f"**Adresse :** {raw_data.get('street') or '-'}")
        st.write(f"**Complément :** {raw_data.get('street2') or '-'}")
        st.write(f"**Code postal :** {raw_data.get('zip') or '-'}")
        st.write(f"**Ville :** {raw_data.get('city') or '-'}")

    st.markdown("#### Informations commerciales")
    st.write(f"**Équipement actuel :** {raw_data.get('current_equipment') or '-'}")
    st.write(f"**Commentaire libre :** {raw_data.get('free_comment') or '-'}")

    st.markdown("#### Activité de relance")
    if raw_data.get("create_activity"):
        activity_type = raw_data.get("activity_type") or "-"
        activity_summary = raw_data.get("activity_summary") or "-"
        activity_date_mode = raw_data.get("activity_date_mode") or "-"
        activity_deadline = raw_data.get("activity_deadline")

        st.write("**Activité planifiée :** Oui")
        st.write(f"**Type :** {activity_type}")
        st.write(f"**Résumé :** {activity_summary}")
        st.write(f"**Mode de date :** {activity_date_mode}")
        st.write(f"**Date de relance :** {_format_deadline(activity_deadline)}")
    else:
        st.write("**Activité planifiée :** Non")

    if preview_vals.get("description"):
        with st.expander("Notes générées pour Odoo", expanded=False):
            st.text(preview_vals["description"])

    activity_vals = preview_vals.get("_activity_vals")
    if activity_vals:
        with st.expander("Activité qui sera créée dans Odoo", expanded=False):
            st.write(f"**Modèle lié :** {activity_vals.get('res_model') or '-'}")
            st.write("**Enregistrement lié :** lead créé juste après validation")
            st.write(f"**Type d'activité Odoo :** {activity_vals.get('_activity_type_label') or '-'}")
            st.write(f"**Résumé :** {activity_vals.get('summary') or '-'}")
            st.write(f"**Date d'échéance :** {_format_deadline(activity_vals.get('date_deadline'))}")
            st.write(f"**Assigné à :** {seller_name}")

    st.write(f"**Étiquette :** {PROSPECTION_TAG}")



def render_local_draft_recovery(on_restore, on_delete):
    payload = st.session_state.get("available_local_draft")
    if not payload:
        return

    data = payload.get("data") or {}
    if not data:
        return

    status = payload.get("status")
    lead_id = payload.get("lead_id")
    saved_at = _format_saved_at(payload.get("saved_at"))
    partner_name = data.get("partner_name") or "-"
    city = data.get("city") or "-"

    if status == "sent":
        title = "Dernière saisie envoyée retrouvée"
        lead_text = f" avec l'ID {lead_id}" if lead_id else ""
        body = (
            f"Cette saisie a déjà été confirmée dans Odoo{lead_text}. "
            "Vous pouvez la reprendre comme base d'une nouvelle saisie, mais vérifiez avant de recréer."
        )
        button_label = "Reprendre cette saisie"
        icon = "✅"
    else:
        title = "Brouillon non envoyé retrouvé"
        body = (
            "Une saisie précédente a été retrouvée sur cet appareil. "
            "Elle n'a peut-être pas été confirmée dans Odoo."
        )
        button_label = "Restaurer le brouillon"
        icon = "📝"

    with st.expander(f"{icon} {title}", expanded=(status != "sent")):
        if status == "sent":
            st.info(body)
        else:
            st.warning(body)

        st.caption(f"Saisie sauvegardée : {partner_name} - {city}" + (f" | {saved_at}" if saved_at else ""))
        st.caption("Ce brouillon est sauvegardé uniquement dans le navigateur de cet appareil.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button(button_label, key="restore_local_browser_draft"):
                on_restore(payload)
        with col2:
            if st.button("Supprimer ce brouillon", key="delete_local_browser_draft"):
                on_delete()


def render_draft_recovery(on_restore, on_ignore):
    draft = st.session_state.get("last_unsent_draft")
    if not draft:
        return

    if st.session_state.get("preview_data"):
        return

    with st.expander("Brouillon de sécurité disponible", expanded=False):
        st.warning(
            "Une saisie récente est conservée en sécurité. "
            "Vous pouvez la restaurer si le formulaire s'est vidé ou si l'envoi n'a pas abouti."
        )

        partner_name = draft.get("partner_name") or "-"
        city = draft.get("city") or "-"
        st.caption(f"Dernière saisie conservée : {partner_name} - {city}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Restaurer ma dernière saisie", key="restore_last_unsent_draft"):
                on_restore(draft)

        with col2:
            if st.button("Ignorer ce brouillon", key="ignore_last_unsent_draft"):
                on_ignore()


def render_debug_events():
    show_debug = False
    try:
        show_debug = bool(st.secrets.get("SHOW_DEBUG", False))
    except Exception:
        show_debug = False

    if not show_debug:
        return

    events = st.session_state.get("debug_events") or []
    local_error = st.session_state.get("local_draft_error")
    if not events and not local_error:
        return

    with st.expander("Diagnostic technique", expanded=False):
        st.caption("Journal local de la session, utile pendant les tests terrain.")
        if local_error:
            st.warning(f"Stockage navigateur : {local_error}")
        st.write(events)



def _format_saved_at(value: Any) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value))
    except Exception:
        return str(value)
    return f"sauvegardée le {_format_date_fr(parsed.date())} à {parsed.strftime('%H:%M')}"


def _format_deadline(value: Any) -> str:
    parsed = _coerce_to_date(value)
    if not parsed:
        return "-"

    return _format_date_fr(parsed)


def _coerce_to_date(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None

        # Format ISO attendu côté métier
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            pass

        # Tolérance jj/mm/aaaa
        try:
            return datetime.strptime(raw, "%d/%m/%Y").date()
        except ValueError:
            return None

    return None


def _format_date_fr(value: date) -> str:
    jours = [
        "lundi",
        "mardi",
        "mercredi",
        "jeudi",
        "vendredi",
        "samedi",
        "dimanche",
    ]
    mois = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    return f"{jours[value.weekday()]} {value.day} {mois[value.month - 1]} {value.year}"
