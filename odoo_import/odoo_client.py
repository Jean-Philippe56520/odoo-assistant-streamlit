import re
import xmlrpc.client

try:
    from .config import (
        ODOO_URL,
        ODOO_DB,
        ODOO_USER,
        ODOO_API_KEY,
        LEAD_MODEL,
        TAG_MODEL,
        TEAM_MODEL,
        USER_MODEL,
    )
    from .console_utils import ERR, WARN, DIM
except ImportError:
    from config import (
        ODOO_URL,
        ODOO_DB,
        ODOO_USER,
        ODOO_API_KEY,
        LEAD_MODEL,
        TAG_MODEL,
        TEAM_MODEL,
        USER_MODEL,
    )
    from console_utils import ERR, WARN, DIM


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
    except Exception as exc:
        raise RuntimeError(f"Connexion Odoo impossible : {exc}") from exc

    if not uid:
        raise RuntimeError("Authentification Odoo échouée.")

    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


def find_or_create_tag(models, uid, tag_name: str) -> int:
    ids = models.execute_kw(
        ODOO_DB,
        uid,
        ODOO_API_KEY,
        TAG_MODEL,
        "search",
        [[("name", "=", tag_name)]],
        {"limit": 1},
    )
    if ids:
        return ids[0]

    return models.execute_kw(
        ODOO_DB,
        uid,
        ODOO_API_KEY,
        TAG_MODEL,
        "create",
        [{"name": tag_name}],
    )


def find_team_ventes(models, uid):
    ids = models.execute_kw(
        ODOO_DB,
        uid,
        ODOO_API_KEY,
        TEAM_MODEL,
        "search",
        [[("name", "ilike", "Ventes")]],
        {"limit": 1},
    )
    return ids[0] if ids else None


def get_active_sales_users(models, uid):
    return models.execute_kw(
        ODOO_DB,
        uid,
        ODOO_API_KEY,
        USER_MODEL,
        "search_read",
        [[("active", "=", True)]],
        {"fields": ["id", "name", "login"], "order": "name asc"},
    )


def _digits_only(value):
    return re.sub(r"\D", "", str(value or ""))


def _clean_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _build_reason(field, label, reason_type):
    return {"field": field, "label": label, "type": reason_type}


def lead_exists(models, uid, email=None, phone=None, mobile=None, company=None, city=None, zip_code=None):
    """
    Retourne un dictionnaire décrivant le lead suspect détecté, ou False.
    Priorité :
    1. email / téléphone / mobile exacts
    2. société + ville
    3. société + code postal
    """
    email = _clean_text(email)
    phone = _digits_only(phone)
    mobile = _digits_only(mobile)
    company = _clean_text(company)
    city = _clean_text(city)
    zip_code = _digits_only(zip_code)

    strong_terms = []
    if email:
        strong_terms.append(("email_from", "=", email))
    if phone:
        strong_terms.append(("phone", "=", phone))
    if mobile:
        strong_terms.append(("mobile", "=", mobile))

    if strong_terms:
        strong_domain = strong_terms if len(strong_terms) == 1 else ["|"] * (len(strong_terms) - 1) + strong_terms
        rows = models.execute_kw(
            ODOO_DB,
            uid,
            ODOO_API_KEY,
            LEAD_MODEL,
            "search_read",
            [strong_domain],
            {
                "fields": ["id", "email_from", "phone", "mobile", "partner_name", "city", "zip"],
                "limit": 5,
            },
        )
        for row in rows:
            reasons = []
            if email and _clean_text(row.get("email_from")) == email:
                reasons.append(_build_reason("email_from", "Email", "email_exact"))
            if phone and _digits_only(row.get("phone")) == phone:
                reasons.append(_build_reason("phone", "Téléphone", "phone_exact"))
            if mobile and _digits_only(row.get("mobile")) == mobile:
                reasons.append(_build_reason("mobile", "Mobile", "mobile_exact"))
            if reasons:
                return {
                    "lead_id": row["id"],
                    "match_level": "strong",
                    "reasons": reasons,
                }

    if company and (city or zip_code):
        soft_domain = [("partner_name", "=", company)]
        if city and zip_code:
            soft_domain += ["|", ("city", "=", city), ("zip", "=", zip_code)]
        elif city:
            soft_domain.append(("city", "=", city))
        elif zip_code:
            soft_domain.append(("zip", "=", zip_code))

        rows = models.execute_kw(
            ODOO_DB,
            uid,
            ODOO_API_KEY,
            LEAD_MODEL,
            "search_read",
            [soft_domain],
            {
                "fields": ["id", "partner_name", "city", "zip"],
                "limit": 5,
            },
        )
        for row in rows:
            row_company = _clean_text(row.get("partner_name"))
            row_city = _clean_text(row.get("city"))
            row_zip = _digits_only(row.get("zip"))
            reasons = []

            if row_company != company:
                continue

            if city and row_city == city:
                reasons.extend([
                    _build_reason("partner_name", "Société", "company_city"),
                    _build_reason("city", "Ville", "company_city"),
                ])
            elif zip_code and row_zip == zip_code:
                reasons.extend([
                    _build_reason("partner_name", "Société", "company_zip"),
                    _build_reason("zip", "Code postal", "company_zip"),
                ])

            if reasons:
                return {
                    "lead_id": row["id"],
                    "match_level": "soft",
                    "reasons": reasons,
                }

    return False
