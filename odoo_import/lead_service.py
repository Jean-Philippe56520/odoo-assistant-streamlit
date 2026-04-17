from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from .config import LEAD_MODEL
from .odoo_client import execute_kw, find_or_create_tag, lead_exists


PROSPECTION_TAG = "Prospection"

DEFAULT_ACTIVITY_TYPE = "To-Do"
DEFAULT_ACTIVITY_SUMMARY = "Relance commerciale"
DEFAULT_ACTIVITY_DATE_MODE = "J+7"

ACTIVITY_TYPE_TO_XMLID_CANDIDATES = {
    "To-Do": [
        "mail.mail_activity_data_todo",
    ],
    "Appel": [
        "mail.mail_activity_data_call",
    ],
    "Email": [
        "mail.mail_activity_data_email",
    ],
}


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

    base = {
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

    activity_data, _ = normalize_activity_data(raw_data)
    base.update(activity_data)
    return base


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

    activity_data, activity_errors = normalize_activity_data(raw_data)
    data.update(activity_data)
    errors.extend(activity_errors)

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
    actor_text = normalize_text(actor_user) or "-"
    seller_text = normalize_text(seller_name) or "-"
    audit_block = (
        f"Action : {mode or '-'}\n"
        f"Date : {stamp}\n"
        f"Compte connecté : {actor_text}\n"
        f"Commercial affecté : {seller_text}"
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

    activity_vals = build_activity_vals_from_answers(
        data=data,
        seller_user_id=seller_user_id,
        uid=uid,
    )
    if activity_vals:
        vals["_activity_vals"] = activity_vals

    return vals


def build_activity_vals_from_answers(data: dict, seller_user_id: int, uid: int | None = None) -> dict | None:
    if not data.get("create_activity"):
        return None

    deadline = normalize_text(data.get("activity_deadline"))
    if not deadline:
        return None

    activity_type_label = normalize_text(data.get("activity_type")) or DEFAULT_ACTIVITY_TYPE
    summary = normalize_text(data.get("activity_summary")) or DEFAULT_ACTIVITY_SUMMARY

    activity_type_id = None
    if uid is not None:
        activity_type_id = resolve_activity_type_id(uid, activity_type_label)

    vals = {
        "res_model": LEAD_MODEL,
        "user_id": seller_user_id,
        "summary": summary,
        "date_deadline": deadline,
        "_activity_type_label": activity_type_label,
    }

    if activity_type_id:
        vals["activity_type_id"] = activity_type_id

    return vals


def resolve_activity_type_id(uid: int, activity_type_label: str) -> int | None:
    xmlids = ACTIVITY_TYPE_TO_XMLID_CANDIDATES.get(activity_type_label, [])

    for xmlid in xmlids:
        activity_type_id = _resolve_xmlid_to_res_id(uid, xmlid)
        if activity_type_id:
            return activity_type_id

    ids = execute_kw(
        uid,
        "mail.activity.type",
        "search",
        args=[[("name", "=", activity_type_label)]],
        kwargs={"limit": 1},
    )
    if ids:
        return ids[0]

    ids = execute_kw(
        uid,
        "mail.activity.type",
        "search",
        args=[[("name", "ilike", activity_type_label)]],
        kwargs={"limit": 1},
    )
    if ids:
        return ids[0]

    return None


def _resolve_xmlid_to_res_id(uid: int, xmlid: str) -> int | None:
    try:
        model_name, record_name = xmlid.split(".", 1)
    except ValueError:
        return None

    ids = execute_kw(
        uid,
        "ir.model.data",
        "search",
        args=[[("module", "=", model_name), ("name", "=", record_name)]],
        kwargs={"limit": 1},
    )
    if not ids:
        return None

    rows = execute_kw(
        uid,
        "ir.model.data",
        "read",
        args=[ids],
        kwargs={"fields": ["res_id"]},
    )
    if not rows:
        return None

    res_id = rows[0].get("res_id")
    return int(res_id) if res_id else None


def normalize_activity_data(raw_data: dict) -> tuple[dict, list[str]]:
    errors: list[str] = []

    create_activity = bool(raw_data.get("create_activity", False))
    activity_type = normalize_text(raw_data.get("activity_type")) or DEFAULT_ACTIVITY_TYPE
    activity_summary = normalize_text(raw_data.get("activity_summary")) or DEFAULT_ACTIVITY_SUMMARY
    activity_date_mode = normalize_text(raw_data.get("activity_date_mode")) or DEFAULT_ACTIVITY_DATE_MODE

    if not create_activity:
        return {
            "create_activity": False,
            "activity_type": DEFAULT_ACTIVITY_TYPE,
            "activity_summary": DEFAULT_ACTIVITY_SUMMARY,
            "activity_date_mode": DEFAULT_ACTIVITY_DATE_MODE,
            "activity_custom_date": None,
            "activity_deadline": None,
        }, errors

    if activity_type not in ("To-Do", "Appel", "Email"):
        errors.append("Le type d'activité est invalide.")

    if not activity_summary:
        errors.append("Le résumé de l'activité est obligatoire.")

    if activity_date_mode not in ("J+7", "J+30", "Choisir une date"):
        errors.append("Le mode de date de relance est invalide.")
        activity_date_mode = DEFAULT_ACTIVITY_DATE_MODE

    custom_date = raw_data.get("activity_custom_date")
    deadline = None

    if activity_date_mode == "J+7":
        deadline = date.today() + timedelta(days=7)
    elif activity_date_mode == "J+30":
        deadline = date.today() + timedelta(days=30)
    elif activity_date_mode == "Choisir une date":
        deadline = _coerce_to_date(custom_date)
        if deadline is None:
            errors.append("La date personnalisée de relance est invalide.")

    if deadline and deadline < date.today():
        errors.append("La date de relance ne peut pas être dans le passé.")

    return {
        "create_activity": True,
        "activity_type": activity_type,
        "activity_summary": activity_summary,
        "activity_date_mode": activity_date_mode,
        "activity_custom_date": deadline if activity_date_mode == "Choisir une date" else None,
        "activity_deadline": deadline.isoformat() if deadline else None,
    }, errors


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
    lead_vals = _extract_lead_vals(vals)
    raw_lead_id = execute_kw(uid, LEAD_MODEL, "create", args=[[lead_vals]])
    lead_id = _normalize_record_id(raw_lead_id)

    return LeadActionResult(
        success=True,
        action="create",
        lead_id=lead_id,
        message=f"Piste créée dans Odoo (ID {lead_id})",
    )


def update_existing_lead(models, uid, lead_id, vals):
    lead_id = _normalize_record_id(lead_id)
    lead_vals = _extract_lead_vals(vals)

    execute_kw(uid, LEAD_MODEL, "write", args=[[lead_id], lead_vals])

    return LeadActionResult(
        success=True,
        action="update",
        lead_id=lead_id,
        message=f"Piste mise à jour (ID {lead_id})",
    )


def _extract_lead_vals(vals: dict) -> dict:
    clean = dict(vals)
    clean.pop("_activity_vals", None)
    return clean


def _normalize_record_id(value) -> int:
    """
    Sécurise les IDs renvoyés par XML-RPC.
    Odoo renvoie normalement un int, mais on a observé ici des listes du type [21101].
    """
    if isinstance(value, int):
        return value

    if isinstance(value, list):
        if not value:
            raise ValueError("ID Odoo vide.")
        if len(value) != 1:
            raise ValueError(f"ID Odoo invalide (liste multiple) : {value}")
        return _normalize_record_id(value[0])

    if isinstance(value, tuple):
        if not value:
            raise ValueError("ID Odoo vide.")
        if len(value) != 1:
            raise ValueError(f"ID Odoo invalide (tuple multiple) : {value}")
        return _normalize_record_id(value[0])

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError("ID Odoo vide.")

        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if not inner:
                raise ValueError("ID Odoo vide.")
            return _normalize_record_id(inner)

        return int(raw)

    raise ValueError(f"Format d'ID Odoo non géré : {value!r}")


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

        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue

    return None
