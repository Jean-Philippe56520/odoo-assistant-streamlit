import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .config import LEAD_MODEL
from .odoo_client import execute_kw, find_or_create_tag, lead_exists


PROSPECTION_TAG = "Prospection"


@dataclass
class ValidationResult:
    cleaned_data: dict
    errors: list[str] = field(default_factory=list)


@dataclass
class ExistingLeadMatch:
    lead_id: int
    summary: Optional[dict]
    match_reason: str = "coordonnees"


@dataclass
class LeadPreviewResult:
    is_valid: bool
    cleaned_data: dict
    vals: Optional[dict]
    errors: list[str] = field(default_factory=list)
    existing_match: Optional[ExistingLeadMatch] = None


@dataclass
class LeadActionResult:
    success: bool
    action: str
    lead_id: Optional[int] = None
    message: str = ""


def normalize_text(value):
    return str(value or "").strip()


def normalize_email(value):
    return normalize_text(value).lower()


def normalize_phone(value):
    raw = normalize_text(value)
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw)


def comparable_phone(value):
    return re.sub(r"\D", "", normalize_text(value))


def validate_email(value):
    email = normalize_email(value)
    if not email:
        return True, None, ""
    if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return True, None, email
    return False, "Email invalide.", None


def validate_phone(value):
    phone = normalize_phone(value)
    if not phone:
        return True, None, ""
    digits = comparable_phone(phone)
    if len(digits) < 8:
        return False, "Téléphone trop court.", None
    return True, None, phone


def ensure_minimum_contact(data):
    return any(normalize_text(data.get(k)) for k in ("phone", "mobile", "email_from"))


def normalize_form_data(raw_data: dict) -> dict:
    phone_ok, _, phone = validate_phone(raw_data.get("phone", ""))
    mobile_ok, _, mobile = validate_phone(raw_data.get("mobile", ""))
    email_ok, _, email_from = validate_email(raw_data.get("email_from", ""))

    return {
        "partner_name": normalize_text(raw_data.get("partner_name")),
        "contact_name": normalize_text(raw_data.get("contact_name")),
        "phone": phone if phone_ok else normalize_text(raw_data.get("phone")),
        "mobile": mobile if mobile_ok else normalize_text(raw_data.get("mobile")),
        "email_from": email_from if email_ok else normalize_text(raw_data.get("email_from")),
        "street": normalize_text(raw_data.get("street")),
        "street2": normalize_text(raw_data.get("street2")),
        "zip": normalize_text(raw_data.get("zip")),
        "city": normalize_text(raw_data.get("city")),
        "current_equipment": normalize_text(raw_data.get("current_equipment")),
        "free_comment": normalize_text(raw_data.get("free_comment")),
    }


def validate_lead_data(raw_data: dict) -> ValidationResult:
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
        "partner_name": normalize_text(raw_data.get("partner_name")),
        "contact_name": normalize_text(raw_data.get("contact_name")),
        "phone": phone if phone is not None else "",
        "mobile": mobile if mobile is not None else "",
        "email_from": email_from if email_from is not None else "",
        "street": normalize_text(raw_data.get("street")),
        "street2": normalize_text(raw_data.get("street2")),
        "zip": normalize_text(raw_data.get("zip")),
        "city": normalize_text(raw_data.get("city")),
        "current_equipment": normalize_text(raw_data.get("current_equipment")),
        "free_comment": normalize_text(raw_data.get("free_comment")),
    }

    if not data["partner_name"]:
        errors.append("Le nom de l'entreprise est obligatoire.")

    if not ensure_minimum_contact(data):
        errors.append("Il faut au moins un moyen de contact : téléphone, mobile ou email.")

    return ValidationResult(cleaned_data=data, errors=errors)


def build_title(data):
    company = normalize_text(data.get("partner_name"))
    contact = normalize_text(data.get("contact_name"))

    if company and contact:
        return f"{company} - {contact}"
    if company:
        return f"Prospection - {company}"
    return "Piste sans nom"


def build_new_note_block(data):
    parts = []
    stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    parts.append(f"--- Saisie prospection du {stamp} ---")

    current_equipment = normalize_text(data.get("current_equipment"))
    if current_equipment:
        parts.append(f"📌 Équipement actuel\n{current_equipment}")

    free_comment = normalize_text(data.get("free_comment"))
    if free_comment:
        parts.append(f"📌 Commentaire libre\n{free_comment}")

    return "\n\n".join(parts)


def build_description_for_create(data):
    block = build_new_note_block(data)
    return block if block.strip() else ""


def merge_descriptions(existing_description, data):
    new_block = build_new_note_block(data).strip()
    old = normalize_text(existing_description)

    if old and new_block:
        return f"{old}\n\n{new_block}"
    if new_block:
        return new_block
    return old


def add_audit_trail(vals, actor_user=None, seller_name=None, mode=None):
    stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    audit_block = (
        f"--- Trace application ---\n"
        f"Action : {mode or '-'}\n"
        f"Compte connecté : {actor_user or '-'}\n"
        f"Commercial sélectionné : {seller_name or '-'}\n"
        f"Date : {stamp}"
    )

    current_description = normalize_text(vals.get("description"))
    if current_description:
        vals["description"] = f"{audit_block}\n\n{current_description}"
    else:
        vals["description"] = audit_block

    return vals


def build_vals_from_answers(data, team_id, seller_user_id, replace_tags=True, existing_description=None):
    uid = data.get("_uid")

    vals = {
        "name": build_title(data),
        "user_id": seller_user_id,
    }

    for field_name in (
        "partner_name",
        "contact_name",
        "email_from",
        "phone",
        "mobile",
        "street",
        "street2",
        "zip",
        "city",
    ):
        value = normalize_text(data.get(field_name))
        if value:
            vals[field_name] = value

    if team_id:
        vals["team_id"] = team_id

    if replace_tags:
        description = build_description_for_create(data)
    else:
        description = merge_descriptions(existing_description, data)

    if description:
        vals["description"] = description

    if uid is not None:
        tag_id = find_or_create_tag(None, uid, PROSPECTION_TAG)
        vals["tag_ids"] = [(6, 0, [tag_id])] if replace_tags else [(4, tag_id)]

    return vals


def detect_existing_lead(models, uid, data):
    email = normalize_email(data.get("email_from"))
    phone = normalize_phone(data.get("phone"))
    mobile = normalize_phone(data.get("mobile"))
    return lead_exists(None, uid, email, phone, mobile)


def read_lead_summary(models, uid, lead_id):
    if not lead_id:
        return None

    try:
        rows = execute_kw(
            uid,
            LEAD_MODEL,
            "read",
            args=[[lead_id]],
            kwargs={
                "fields": [
                    "name",
                    "partner_name",
                    "contact_name",
                    "email_from",
                    "phone",
                    "mobile",
                    "user_id",
                    "description",
                ]
            },
        )
        return rows[0] if rows else None
    except Exception:
        return None


def prepare_lead_preview(
    uid,
    models,
    raw_data,
    team_id,
    seller_user_id,
    seller_name=None,
    actor_user=None,
    audit_mode="prévisualisation",
):
    validation = validate_lead_data(raw_data)
    if validation.errors:
        return LeadPreviewResult(
            is_valid=False,
            cleaned_data=validation.cleaned_data,
            vals=None,
            errors=validation.errors,
            existing_match=None,
        )

    work_data = dict(validation.cleaned_data)
    work_data["_uid"] = uid
    if actor_user is not None:
        work_data["_actor_user"] = actor_user

    existing_id = detect_existing_lead(models, uid, work_data)
    existing_data = read_lead_summary(models, uid, existing_id) if existing_id else None

    vals = build_vals_from_answers(
        work_data,
        team_id,
        seller_user_id,
        replace_tags=existing_id is None,
        existing_description=existing_data.get("description") if existing_data else None,
    )

    if audit_mode:
        vals = add_audit_trail(
            vals,
            actor_user=actor_user,
            seller_name=seller_name,
            mode=audit_mode,
        )

    existing_match = None
    if existing_id:
        existing_match = ExistingLeadMatch(
            lead_id=existing_id,
            summary=existing_data,
        )

    return LeadPreviewResult(
        is_valid=True,
        cleaned_data=work_data,
        vals=vals,
        errors=[],
        existing_match=existing_match,
    )


def create_new_lead(models, uid, vals):
    lead_id = execute_kw(uid, LEAD_MODEL, "create", args=[[vals]])
    return LeadActionResult(
        success=True,
        action="create",
        lead_id=lead_id,
        message=f"Piste créée dans Odoo (ID {lead_id})",
    )


def update_existing_lead(models, uid, lead_id, vals):
    execute_kw(uid, LEAD_MODEL, "write", args=[[lead_id], vals])
    return LeadActionResult(
        success=True,
        action="update",
        lead_id=lead_id,
        message=f"Piste mise à jour (ID {lead_id})",
    )
