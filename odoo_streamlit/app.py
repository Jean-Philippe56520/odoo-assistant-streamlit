import sys
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import extra_streamlit_components as stx

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from odoo_import.commercial_wizard import (
    PROSPECTION_TAG,
    build_title,
    build_vals_from_answers,
    detect_existing_lead,
    read_lead_summary,
    validate_email,
    validate_phone,
    ensure_minimum_contact,
)
from odoo_import.config import ODOO_DB, ODOO_API_KEY, LEAD_MODEL
from odoo_import.odoo_client import odoo_connect, find_team_ventes, get_active_sales_users

st.set_page_config(page_title="Saisie prospection Odoo V2", layout="centered")


@st.cache_resource
def get_cookie_manager():
    return stx.CookieManager()


def require_simple_auth():
    username = st.secrets["auth_simple"]["username"]
    password = st.secrets["auth_simple"]["password"]
    cookie_name = st.secrets["auth_simple"]["cookie_name"]
    cookie_key = st.secrets["auth_simple"]["cookie_key"]
    cookie_expiry_days = int(st.secrets["auth_simple"].get("cookie_expiry_days", 30))

    cookie_manager = get_cookie_manager()

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if "auth_user" not in st.session_state:
        st.session_state["auth_user"] = ""

    existing_cookie = cookie_manager.get(cookie_name)
    expected_cookie_value = f"{username}:{cookie_key}"

    if existing_cookie == expected_cookie_value:
        st.session_state["authenticated"] = True
        st.session_state["auth_user"] = username
        return

    if not st.session_state["authenticated"]:
        st.title("Accès privé ABM")
        st.caption("Connexion requise pour accéder à l'application.")

        input_user = st.text_input("Identifiant")
        input_pass = st.text_input("Mot de passe", type="password")
        remember_me = st.checkbox("Rester connecté 30 jours", value=True)

        if st.button("Se connecter", type="primary"):
            if input_user == username and input_pass == password:
                st.session_state["authenticated"] = True
                st.session_state["auth_user"] = input_user

                if remember_me:
                    cookie_manager.set(
                        cookie_name,
                        expected_cookie_value,
                        expires_at=datetime.now() + timedelta(days=cookie_expiry_days),
                    )

                st.rerun()
            else:
                st.error("Identifiants incorrects.")

        st.stop()


def render_logout():
    cookie_name = st.secrets["auth_simple"]["cookie_name"]
    cookie_manager = get_cookie_manager()

    with st.sidebar:
        st.markdown("### Session")
        st.write(f"Connecté : {st.session_state.get('auth_user', '-')}")
        if st.button("Se déconnecter", use_container_width=True):
            cookie_manager.delete(cookie_name)
            st.session_state["authenticated"] = False
            st.session_state["auth_user"] = ""
            st.rerun()


def add_audit_trail(vals, actor_user, seller_name, mode):
    stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    audit_block = (
        f"--- Trace application ---\n"
        f"Action : {mode}\n"
        f"Compte connecté : {actor_user or '-'}\n"
        f"Commercial sélectionné : {seller_name or '-'}\n"
        f"Date : {stamp}"
    )

    current_description = (vals.get("description") or "").strip()
    if current_description:
        vals["description"] = f"{audit_block}\n\n{current_description}"
    else:
        vals["description"] = audit_block

    return vals


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


def _init_state():
    defaults = {
        "form_data": {
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
        },
        "preview_data": None,
        "preview_vals": None,
        "existing_id": None,
        "existing_data": None,
        "seller_name": None,
        "seller_user_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_preview_only():
    for key in ("preview_data", "preview_vals", "existing_id", "existing_data", "seller_name", "seller_user_id"):
        st.session_state[key] = None


def reset_all():
    _init_state()
    st.session_state["form_data"] = {
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
    reset_preview_only()


def validate_form(raw_data):
    errors = []

    ok, msg, phone = validate_phone(raw_data.get("phone", ""))
    if not ok:
        errors.append(msg)

    ok, msg, mobile = validate_phone(raw_data.get("mobile", ""))
    if not ok:
        errors.append(msg)

    ok, msg, email_from = validate_email(raw_data.get("email_from", ""))
    if not ok:
        errors.append(msg)

    data = {
        "partner_name": (raw_data.get("partner_name") or "").strip(),
        "contact_name": (raw_data.get("contact_name") or "").strip(),
        "phone": phone,
        "mobile": mobile,
        "email_from": email_from,
        "street": (raw_data.get("street") or "").strip(),
        "street2": (raw_data.get("street2") or "").strip(),
        "zip": (raw_data.get("zip") or "").strip(),
        "city": (raw_data.get("city") or "").strip(),
        "current_equipment": (raw_data.get("current_equipment") or "").strip(),
        "free_comment": (raw_data.get("free_comment") or "").strip(),
    }

    if not data["partner_name"]:
        errors.append("Le nom de l'entreprise est obligatoire.")

    if not ensure_minimum_contact(data):
        errors.append("Il faut au moins un moyen de contact : téléphone, mobile ou email.")

    return errors, data


def compute_preview(data, seller_name, seller_user_id):
    uid, models = get_odoo()
    work_data = dict(data)
    work_data["_uid"] = uid
    work_data["_models"] = models
    work_data["_actor_user"] = st.session_state.get("auth_user", "")

    existing_id = detect_existing_lead(models, uid, work_data)
    existing_data = read_lead_summary(models, uid, existing_id) if existing_id else None

    preview_vals = build_vals_from_answers(
        work_data,
        get_team_id(),
        seller_user_id,
        replace_tags=existing_id is None,
        existing_description=existing_data.get("description") if existing_data else None,
    )

    preview_vals = add_audit_trail(
        preview_vals,
        actor_user=st.session_state.get("auth_user", ""),
        seller_name=seller_name,
        mode="prévisualisation",
    )

    st.session_state["preview_data"] = work_data
    st.session_state["preview_vals"] = preview_vals
    st.session_state["existing_id"] = existing_id
    st.session_state["existing_data"] = existing_data
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
    return models.execute_kw(
        ODOO_DB,
        uid,
        ODOO_API_KEY,
        LEAD_MODEL,
        "create",
        [vals],
    )


def update_lead(lead_id, vals):
    uid, models = get_odoo()
    return models.execute_kw(
        ODOO_DB,
        uid,
        ODOO_API_KEY,
        LEAD_MODEL,
        "write",
        [[lead_id], vals],
    )


require_simple_auth()
render_logout()

_init_state()
st.title("Saisie prospection Odoo V2")
st.caption("Version web sécurisée par identifiant partagé, avec contrôle des leads similaires et confirmation finale.")

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

with st.form("lead_form"):
    seller_name = st.selectbox(
        "Commercial",
        seller_names,
        index=seller_names.index(st.session_state["seller_name"]) if st.session_state["seller_name"] in seller_names else 0,
    )

    st.subheader("Contact")
    partner_name = st.text_input("Nom de l'entreprise *", value=st.session_state["form_data"]["partner_name"])
    contact_name = st.text_input("Nom du contact", value=st.session_state["form_data"]["contact_name"])
    phone_raw = st.text_input("Téléphone", value=st.session_state["form_data"]["phone"])
    mobile_raw = st.text_input("Mobile", value=st.session_state["form_data"]["mobile"])
    email_raw = st.text_input("Email", value=st.session_state["form_data"]["email_from"])

    st.subheader("Adresse")
    street = st.text_input("Adresse", value=st.session_state["form_data"]["street"])
    street2 = st.text_input("Complément d'adresse", value=st.session_state["form_data"]["street2"])
    zip_code = st.text_input("Code postal", value=st.session_state["form_data"]["zip"])
    city = st.text_input("Ville", value=st.session_state["form_data"]["city"])

    st.subheader("Notes")
    current_equipment = st.text_area("Équipement actuel", value=st.session_state["form_data"]["current_equipment"])
    free_comment = st.text_area("Commentaire libre", value=st.session_state["form_data"]["free_comment"])

    submitted = st.form_submit_button("Prévisualiser")

if submitted:
    raw_data = {
        "partner_name": partner_name,
        "contact_name": contact_name,
        "phone": phone_raw,
        "mobile": mobile_raw,
        "email_from": email_raw,
        "street": street,
        "street2": street2,
        "zip": zip_code,
        "city": city,
        "current_equipment": current_equipment,
        "free_comment": free_comment,
    }

    st.session_state["form_data"] = raw_data

    errors, clean_data = validate_form(raw_data)
    if errors:
        reset_preview_only()
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
        )
        confirm = st.checkbox("Je confirme cette action", key="confirm_existing")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Valider l'action", type="primary"):
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
                    update_lead(existing_id, vals)
                    st.success(f"Lead mis à jour (ID {existing_id}).")
                    reset_all()
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
                    lead_id = create_lead(vals)
                    st.success(f"Nouveau lead créé (ID {lead_id}).")
                    reset_all()
                    st.rerun()
                else:
                    st.info("Opération annulée.")
                    reset_all()
                    st.rerun()
        with col2:
            if st.button("Revenir à la saisie"):
                reset_preview_only()
                st.rerun()
    else:
        confirm = st.checkbox("Je confirme la création de cette piste", key="confirm_create")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Créer la piste", type="primary"):
                if not confirm:
                    st.error("Merci de confirmer la création.")
                else:
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
                    lead_id = create_lead(vals)
                    st.success(f"Piste créée dans Odoo (ID {lead_id}).")
                    reset_all()
                    st.rerun()
        with col2:
            if st.button("Modifier la saisie"):
                reset_preview_only()
                st.rerun()