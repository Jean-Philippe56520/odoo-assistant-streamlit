import xmlrpc.client
from .config import (
    ODOO_URL, ODOO_DB, ODOO_USER, ODOO_API_KEY,
    LEAD_MODEL, TAG_MODEL, TEAM_MODEL, USER_MODEL
)
from .console_utils import ERR, WARN, DIM

def odoo_connect():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    try:
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_API_KEY, {})
    except xmlrpc.client.Fault as fault:
        if "CONNECT privilege" in fault.faultString or "permission denied" in fault.faultString:
            print(ERR("\n❌ Accès refusé à la base Odoo configurée."))
            print(DIM(f"URL : {ODOO_URL}"))
            print(DIM(f"DB  : {ODOO_DB}"))
            print(DIM("➡️ Demande à l'admin Odoo de t'ajouter sur cette base."))
        raise

    if not uid:
        raise RuntimeError("Authentification Odoo échouée.")

    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


def find_or_create_tag(models, uid, tag_name: str) -> int:
    ids = models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY,
        TAG_MODEL, "search",
        [[("name", "=", tag_name)]],
        {"limit": 1}
    )
    if ids:
        return ids[0]
    return models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY,
        TAG_MODEL, "create",
        [{"name": tag_name}]
    )


def find_team_ventes(models, uid):
    ids = models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY,
        TEAM_MODEL, "search",
        [[("name", "ilike", "Ventes")]],
        {"limit": 1}
    )
    return ids[0] if ids else None


def get_active_sales_users(models, uid):
    return models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY,
        USER_MODEL, "search_read",
        [[("active", "=", True)]],
        {"fields": ["id", "name", "login"], "order": "name asc"}
    )


def lead_exists(models, uid, email, phone, mobile=None):
    """
    Doublon fiable sur coordonnées uniquement.
    GARDE-FOU : si aucun critère => False (jamais de search([])).
    OR email/phone/mobile.
    """
    email = (email or "").strip()
    phone = (phone or "").strip()
    mobile = (mobile or "").strip()

    if not (email or phone or mobile):
        return False

    terms = []
    if email:  terms.append(("email_from", "=", email))
    if phone:  terms.append(("phone", "=", phone))
    if mobile: terms.append(("mobile", "=", mobile))

    if len(terms) == 1:
        domain = terms
    else:
        domain = ["|"] * (len(terms) - 1) + terms

    ids = models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY,
        LEAD_MODEL, "search",
        [domain],
        {"limit": 1}
    )
    return ids[0] if ids else False
