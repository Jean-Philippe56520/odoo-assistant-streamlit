import sys
import uuid
from pathlib import Path

import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from odoo_import.lead_service import (
    PROSPECTION_TAG,
    add_audit_trail,
    build_title,
    build_vals_from_answers,
    create_new_lead,
    prepare_lead_preview,
    update_existing_lead,
    validate_lead_data,
)
from odoo_import.odoo_client import (
    find_team_ventes,
    get_active_sales_users,
    odoo_connect,
)
from odoo_streamlit.auth import require_simple_auth, render_logout
from odoo_streamlit.browser_state import (
    FORM_FIELD_KEYS,
    build_draft_from_session,
    clear_local_draft,
    get_browser_snapshot,
    has_meaningful_draft,
    mark_current_session,
    render_connection_watchdog,
    restore_draft_to_session_state,
    save_local_draft,
)

st.set_page_config(page_title="Saisie prospection Odoo V2", layout="centered")

APP_STATE_KEYS = (
    "form_data",
    "preview_data",
    "preview_vals",
    "existing_id",
    "existing_data",
    "seller_name",
    "seller_user_id",
    "result_banner",
    "pending_form_reset",
    "pending_preview_reset",
    "pending_local_draft_clear",
    "streamlit_session_id",
    "draft_restored",
    "draft_prompt_dismissed",
    "session_reset_acknowledged",
)


@st.cache_resource
def get_odoo():
    uid, models = odoo_connect()
    return uid, models


@st.cache_data(ttl=300)
def get_sales_users():
    uid, models = get_odoo()
    return get_active_sales_users(models, uid)


@st.cache_data(ttl=300)
def get_team_id():
    uid, models = get_odoo()
    return find_team_ventes(models, uid)


def _empty_form_data():
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
    }


def _init_state():
    defaults = {
        "form_data": _empty_form_data(),
        "preview_data": None,
        "preview_vals": None,
        "existing_id": None,
        "existing_data": None,
        "seller_name": None,
        "seller_user_id": None,
        "result_banner": None,
        "pending_form_reset": False,
        "pending_preview_reset": False,
        "pending_local_draft_clear": False,
        "draft_restored": False,
        "draft_prompt_dismissed": False,
        "session_reset_acknowledged": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if "streamlit_session_id" not in st.session_state:
        st.session_state["streamlit_session_id"] = str(uuid.uuid4())


def _clear_form_widget_state():
    for key in FORM_FIELD_KEYS:
        st.session_state[key] = ""

    st.session_state["confirm_existing"] = False
    st.session_state["duplicate_action_radio"] = "Mettre à jour le lead existant"

    if "seller_selectbox" in st.session_state:
        del st.session_state["seller_selectbox"]


def _apply_pending_resets():
    if st.session_state.get("pending_local_draft_clear"):
        clear_local_draft(component_key="pending_clear_local_draft")
        st.session_state["pending_local_draft_clear"] = False

    if st.session_state.get("pending_form_reset"):
        st.session_state["form_data"] = _empty_form_data()
        st.session_state["preview_data"] = None
        st.session_state["preview_vals"] = None
        st.session_state["existing_id"] = None
        st.session_state["existing_data"] = None
        st.session_state["seller_name"] = None
        st.session_state["seller_user_id"] = None
        st.session_state["draft_restored"] = False
        st.session_state["draft_prompt_dismissed"] = False

        _clear_form_widget_state()

        st.session_state["pending_form_reset"] = False
        st.session_state["pending_preview_reset"] = False

    elif st.session_state.get("pending_preview_reset"):
        st.session_state["preview_data"] = None
        st.session_state["preview_vals"] = None
        st.session_state["existing_id"] = None
        st.session_state["existing_data"] = None
        st.session_state["confirm_existing"] = False
        st.session_state["duplicate_action_radio"] = "Mettre à jour le lead existant"
        st.session_state["pending_preview_reset"] = False


def request_preview_reset():
    st.session_state["pending_preview_reset"] = True


def request_full_reset(clear_banner=False, clear_local_draft_after_rerun=False):
    if clear_banner:
        st.session_state["result_banner"] = None
    if clear_local_draft_after_rerun:
        st.session_state["pending_local_draft_clear"] = True
    st.session_state["pending_form_reset"] = True


def validate_form(raw_data):
    result = validate_lead_data(raw_data)
    return result.errors, result.cleaned_data


def compute_preview(data, seller_name, seller_user_id):
    uid, models = get_odoo()

    preview = prepare_lead_preview(
        uid=uid,
        models=models,
        raw_data=data,
        team_id=get_team_id(),
        seller_user_id=seller_user_id,
        seller_name=seller_name,
        actor_user=st.session_state.get("auth_user", ""),
        audit_mode="prévisualisation",
    )

    st.session_state["preview_data"] = preview.cleaned_data
    st.session_state["preview_vals"] = preview.vals
    st.session_state["existing_id"] = preview.existing_match.lead_id if preview.existing_match else None
    st.session_state["existing_data"] = preview.existing_match.summary if preview.existing_match else None
    st.session_state["seller_name"] = seller_name
    st.session_state["seller_user_id"] = seller_user_id


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


def show_preview(preview_vals, raw_data, seller_name):
    st.subheader("Prévisualisation")
    st.write(f"**Compte connecté :** {st.session_state.get('auth_user') or '-'}")
    st.write(f"**Commercial :** {seller_name}")
    st.write(f"**Titre :** {build_title(raw_data)}")
    st.write(f"**Entreprise :** {raw_data.get('partner_name') or '-'}")
    st.write(f"**Contact :** {raw_data.get('contact_name') or '-'}")
    st.write(f"**Téléphone :** {raw_data.get('phone') or '-'}")
    st.write(f"**Mobile :** {raw_data.get('mobile') or '-'}")
    st.write(f"**Email :** {raw_data.get('email_from') or '-'}")
    st.write(f"**Adresse :** {raw_data.get('street') or '-'}")
    st.write(f"**Complément :** {raw_data.get('street2') or '-'}")
    st.write(f"**Code postal :** {raw_data.get('zip') or '-'}")
    st.write(f"**Ville :** {raw_data.get('city') or '-'}")
    st.write(f"**Équipement actuel :** {raw_data.get('current_equipment') or '-'}")
    st.write(f"**Commentaire libre :** {raw_data.get('free_comment') or '-'}")
    if preview_vals.get("description"):
        with st.expander("Notes générées pour Odoo", expanded=False):
            st.text(preview_vals["description"])
    st.write(f"**Étiquette :** {PROSPECTION_TAG}")


def create_lead(vals):
    uid, models = get_odoo()
    return create_new_lead(models, uid, vals)


def update_lead(lead_id, vals):
    uid, models = get_odoo()
    return update_existing_lead(models, uid, lead_id, vals)


def get_raw_form_data_from_session():
    return {key: str(st.session_state.get(key, "") or "") for key in FORM_FIELD_KEYS}


def sync_form_data_from_widgets():
    st.session_state["form_data"] = get_raw_form_data_from_session()


def handle_form_change():
    sync_form_data_from_widgets()
    request_preview_reset()


def ensure_form_widgets_initialized():
    form_data = st.session_state.get("form_data") or _empty_form_data()
    for key in FORM_FIELD_KEYS:
        if key not in st.session_state:
            st.session_state[key] = form_data.get(key, "")


def render_session_reset_block(snapshot, seller_names):
    draft = snapshot.get("draft") or {}
    draft_exists = snapshot.get("draft_exists", False)

    st.error("Session réinitialisée", icon="⚠️")
    st.write(
        "L'application a redémarré pendant votre absence. "
        "Par sécurité, rechargez l'application avant de continuer."
    )

    if draft_exists:
        st.info(
            "Un brouillon non envoyé a été retrouvé sur cet appareil. "
            "Il sera conservé après rechargement."
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Reprendre le brouillon", type="primary", key="restore_draft_after_reset"):
                restore_draft_to_session_state(draft, seller_names=seller_names)
                st.session_state["session_reset_acknowledged"] = True
                st.session_state["result_banner"] = {
                    "status": "success",
                    "message": "Brouillon restauré. Vérifiez les informations avant de prévisualiser.",
                }
                st.rerun()
        with col2:
            if st.button("Effacer et recommencer", key="clear_draft_after_reset"):
                st.session_state["session_reset_acknowledged"] = True
                st.session_state["pending_local_draft_clear"] = True
                request_full_reset(clear_banner=True)
                st.session_state["result_banner"] = {
                    "status": "warning",
                    "message": "Brouillon supprimé. Vous pouvez recommencer une nouvelle saisie.",
                }
                st.rerun()
        with col3:
            if st.button("Recharger l'application", key="reload_after_reset"):
                st.session_state["session_reset_acknowledged"] = True
                st.session_state["result_banner"] = {
                    "status": "warning",
                    "message": "Session réinitialisée acceptée. Le brouillon reste disponible si vous souhaitez le reprendre.",
                }
                st.rerun()
    else:
        st.warning("Aucun brouillon local n'a été retrouvé.")
        if st.button("Recharger l'application", type="primary", key="reload_after_reset_no_draft"):
            st.session_state["session_reset_acknowledged"] = True
            st.session_state["result_banner"] = {
                "status": "warning",
                "message": "Session réinitialisée acceptée. Vous pouvez recommencer une nouvelle saisie.",
            }
            st.rerun()

    st.stop()


def render_draft_prompt(draft, seller_names):
    if not has_meaningful_draft(draft):
        return
    if st.session_state.get("draft_prompt_dismissed"):
        return
    if has_meaningful_draft(get_raw_form_data_from_session()):
        return

    st.info("Un brouillon non envoyé a été retrouvé sur cet appareil.")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Reprendre le brouillon", type="primary", key="restore_existing_draft"):
            restore_draft_to_session_state(draft, seller_names=seller_names)
            st.rerun()
    with col2:
        if st.button("Effacer le brouillon", key="clear_existing_draft"):
            st.session_state["pending_local_draft_clear"] = True
            st.session_state["draft_prompt_dismissed"] = True
            request_full_reset(clear_banner=True)
            st.rerun()
    with col3:
        if st.button("Ignorer", key="dismiss_existing_draft"):
            st.session_state["draft_prompt_dismissed"] = True
            st.rerun()


def display_banner():
    banner = st.session_state.get("result_banner")
    if not banner:
        return
    if banner["status"] == "success":
        st.success(banner["message"], icon="✅")
    elif banner["status"] == "warning":
        st.warning(banner["message"], icon="⚠️")
    else:
        st.error(banner["message"], icon="❌")


require_simple_auth()
render_logout(APP_STATE_KEYS)

_init_state()
_apply_pending_resets()
render_connection_watchdog()

st.title("Saisie prospection Odoo V2")
st.caption("Version web sécurisée par identifiant partagé, avec contrôle des leads similaires et confirmation finale.")

display_banner()

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

snapshot = get_browser_snapshot(st.session_state["streamlit_session_id"])
status = snapshot.get("status")

if status == "session_reset" and not st.session_state.get("session_reset_acknowledged"):
    render_session_reset_block(snapshot, seller_names=seller_names)
else:
    mark_current_session(st.session_state["streamlit_session_id"], component_key=f"mark_session_{status}")

ensure_form_widgets_initialized()
render_draft_prompt(snapshot.get("draft") or {}, seller_names=seller_names)

current_seller = st.session_state.get("seller_selectbox") or st.session_state.get("seller_name")
if current_seller not in seller_options:
    current_seller = seller_names[0]

seller_name = st.selectbox(
    "Commercial",
    seller_names,
    index=seller_names.index(current_seller),
    key="seller_selectbox",
    on_change=handle_form_change,
)
st.session_state["seller_name"] = seller_name
st.session_state["seller_user_id"] = seller_options[seller_name]

st.subheader("Contact")
st.text_input("Nom de l'entreprise *", key="partner_name", on_change=handle_form_change)
st.text_input("Nom du contact", key="contact_name", on_change=handle_form_change)
st.text_input("Téléphone", key="phone", on_change=handle_form_change)
st.text_input("Mobile", key="mobile", on_change=handle_form_change)
st.text_input("Email", key="email_from", on_change=handle_form_change)

st.subheader("Adresse")
st.text_input("Adresse", key="street", on_change=handle_form_change)
st.text_input("Complément d'adresse", key="street2", on_change=handle_form_change)
st.text_input("Code postal", key="zip", on_change=handle_form_change)
st.text_input("Ville", key="city", on_change=handle_form_change)

st.subheader("Notes")
st.text_area("Équipement actuel", key="current_equipment", on_change=handle_form_change)
st.text_area("Commentaire libre", key="free_comment", on_change=handle_form_change)

sync_form_data_from_widgets()
current_draft = build_draft_from_session(seller_name=seller_name)
save_local_draft(current_draft, component_key="save_current_form_draft")

submitted = st.button("Prévisualiser", type="primary", key="preview_button")

if submitted:
    st.session_state["result_banner"] = None

    raw_data = get_raw_form_data_from_session()
    st.session_state["form_data"] = raw_data

    errors, clean_data = validate_form(raw_data)
    if errors:
        request_preview_reset()
        for error in errors:
            st.error(error)
    else:
        compute_preview(clean_data, seller_name, seller_options[seller_name])

preview_data = st.session_state["preview_data"]
preview_vals = st.session_state["preview_vals"]
existing_id = st.session_state["existing_id"]
existing_data = st.session_state["existing_data"]

if preview_data and preview_vals:
    st.divider()
    show_preview(preview_vals, preview_data, st.session_state["seller_name"])

    if existing_id:
        st.warning(f"Un lead similaire existe déjà (ID {existing_id}).")
        st.caption("Le système signale une similarité. Vous décidez ensuite de mettre à jour, créer quand même, ou annuler.")
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
                elif action == "Mettre à jour le lead existant":
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
                        st.session_state["result_banner"] = {
                            "status": "success",
                            "message": f"Piste bien prise en compte par Odoo. Mise à jour confirmée (ID {result.lead_id}). Brouillon local supprimé.",
                        }
                    else:
                        st.session_state["result_banner"] = {
                            "status": "warning",
                            "message": f"Mise à jour envoyée, mais confirmation Odoo incomplète. {result.message}",
                        }

                    request_full_reset(clear_banner=False, clear_local_draft_after_rerun=result.success)
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
                    result = create_lead(vals)

                    if result.success:
                        st.session_state["result_banner"] = {
                            "status": "success",
                            "message": f"Piste bien prise en compte par Odoo. Nouveau lead créé et confirmé (ID {result.lead_id}). Brouillon local supprimé.",
                        }
                    else:
                        st.session_state["result_banner"] = {
                            "status": "warning",
                            "message": f"Création envoyée, mais confirmation Odoo incomplète. {result.message}",
                        }

                    request_full_reset(clear_banner=False, clear_local_draft_after_rerun=result.success)
                    st.rerun()

                else:
                    st.session_state["result_banner"] = {
                        "status": "warning",
                        "message": "Opération annulée. Aucune piste n'a été créée ni modifiée.",
                    }
                    request_full_reset(clear_banner=False, clear_local_draft_after_rerun=False)
                    st.rerun()

        with col2:
            if st.button("Revenir à la saisie", key="back_to_form_existing"):
                request_preview_reset()
                st.rerun()

    else:
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Créer la piste", type="primary", key="create_new_lead"):
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
                    st.session_state["result_banner"] = {
                        "status": "success",
                        "message": f"Piste bien prise en compte par Odoo. Création confirmée (ID {result.lead_id}). Brouillon local supprimé.",
                    }
                else:
                    st.session_state["result_banner"] = {
                        "status": "warning",
                        "message": f"La création a été lancée, mais la confirmation Odoo n'a pas pu être relue. {result.message}",
                    }

                request_full_reset(clear_banner=False, clear_local_draft_after_rerun=result.success)
                st.rerun()

        with col2:
            if st.button("Modifier la saisie", key="back_to_form_create"):
                request_preview_reset()
                st.rerun()
