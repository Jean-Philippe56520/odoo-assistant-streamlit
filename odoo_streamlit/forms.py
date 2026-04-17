from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import streamlit as st

from odoo_import.lead_service import validate_lead_data
from odoo_streamlit.constants import (
    ACTIVITY_CUSTOM_DATE_LABEL,
    ACTIVITY_DATE_LABEL,
    ACTIVITY_DATE_MODES,
    ACTIVITY_PREVIEW_LABEL,
    ACTIVITY_SECTION_TITLE,
    ACTIVITY_SUMMARY_LABEL,
    ACTIVITY_SUMMARY_PLACEHOLDER,
    ACTIVITY_TOGGLE_HELP,
    ACTIVITY_TOGGLE_LABEL,
    ACTIVITY_TYPE_LABEL,
    ACTIVITY_TYPE_LABELS,
    DEFAULT_ACTIVITY_DATE_MODE,
    DEFAULT_ACTIVITY_SUMMARY,
    DEFAULT_ACTIVITY_TYPE,
    ERROR_ACTIVITY_CUSTOM_DATE_INVALID,
    ERROR_ACTIVITY_DATE_PAST,
    ERROR_ACTIVITY_DATE_REQUIRED,
    ERROR_ACTIVITY_SUMMARY_REQUIRED,
    ERROR_ACTIVITY_TYPE_REQUIRED,
)


def validate_form(raw_data: dict[str, Any]):
    """
    Validation globale du formulaire.

    - Valide les champs lead via lead_service.validate_lead_data
    - Valide les champs activité localement
    - Retourne une structure cleaned_data prête à être utilisée ensuite
    """
    result = validate_lead_data(raw_data)
    cleaned_data = dict(result.cleaned_data)
    errors = list(result.errors)

    activity_data, activity_errors = _validate_activity_data(raw_data)
    cleaned_data.update(activity_data)
    errors.extend(activity_errors)

    return errors, cleaned_data


def render_lead_form(seller_names):
    """
    Rend le formulaire principal de saisie.
    Retourne :
    - submitted: bool
    - seller_name: str
    - raw_data: dict
    """
    form_data = st.session_state["form_data"]

    with st.form("lead_form"):
        seller_name = st.selectbox(
            "Commercial",
            seller_names,
            index=_get_seller_index(seller_names),
            key="seller_selectbox",
        )

        st.subheader("Contact")
        partner_name = st.text_input(
            "Nom de l'entreprise *",
            value=form_data["partner_name"],
            key="partner_name",
        )
        contact_name = st.text_input(
            "Nom du contact",
            value=form_data["contact_name"],
            key="contact_name",
        )
        phone_raw = st.text_input(
            "Téléphone",
            value=form_data["phone"],
            key="phone",
        )
        mobile_raw = st.text_input(
            "Mobile",
            value=form_data["mobile"],
            key="mobile",
        )
        email_raw = st.text_input(
            "Email",
            value=form_data["email_from"],
            key="email_from",
        )

        st.subheader("Adresse")
        street = st.text_input(
            "Adresse",
            value=form_data["street"],
            key="street",
        )
        street2 = st.text_input(
            "Complément d'adresse",
            value=form_data["street2"],
            key="street2",
        )
        zip_code = st.text_input(
            "Code postal",
            value=form_data["zip"],
            key="zip",
        )
        city = st.text_input(
            "Ville",
            value=form_data["city"],
            key="city",
        )

        st.subheader("Notes")
        current_equipment = st.text_area(
            "Équipement actuel",
            value=form_data["current_equipment"],
            key="current_equipment",
        )
        free_comment = st.text_area(
            "Commentaire libre",
            value=form_data["free_comment"],
            key="free_comment",
        )

        st.divider()
        activity_ui = _render_activity_section(form_data)

        submitted = st.form_submit_button("Prévisualiser", type="primary")

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
        # Bloc activité
        "create_activity": activity_ui["create_activity"],
        "activity_type": activity_ui["activity_type"],
        "activity_summary": activity_ui["activity_summary"],
        "activity_date_mode": activity_ui["activity_date_mode"],
        "activity_custom_date": activity_ui["activity_custom_date"],
    }
    return submitted, seller_name, raw_data


def _render_activity_section(form_data: dict[str, Any]) -> dict[str, Any]:
    """
    Bloc UX pour la planification optionnelle d'activité.
    """
    st.subheader(ACTIVITY_SECTION_TITLE)

    create_activity = st.checkbox(
        ACTIVITY_TOGGLE_LABEL,
        value=bool(form_data.get("create_activity", False)),
        help=ACTIVITY_TOGGLE_HELP,
        key="create_activity",
    )

    if not create_activity:
        st.caption("Aucune activité planifiée pour cette piste.")
        return {
            "create_activity": False,
            "activity_type": DEFAULT_ACTIVITY_TYPE,
            "activity_summary": DEFAULT_ACTIVITY_SUMMARY,
            "activity_date_mode": DEFAULT_ACTIVITY_DATE_MODE,
            "activity_custom_date": _coerce_date(
                form_data.get("activity_custom_date"),
                default=_compute_deadline_from_mode(DEFAULT_ACTIVITY_DATE_MODE),
            ),
        }

    activity_type = st.selectbox(
        ACTIVITY_TYPE_LABEL,
        ACTIVITY_TYPE_LABELS,
        index=_get_activity_type_index(form_data.get("activity_type")),
        key="activity_type",
    )

    activity_summary = st.text_input(
        ACTIVITY_SUMMARY_LABEL,
        value=form_data.get("activity_summary") or DEFAULT_ACTIVITY_SUMMARY,
        placeholder=ACTIVITY_SUMMARY_PLACEHOLDER,
        key="activity_summary",
    )

    activity_date_mode = st.radio(
        ACTIVITY_DATE_LABEL,
        ACTIVITY_DATE_MODES,
        index=_get_activity_date_mode_index(form_data.get("activity_date_mode")),
        horizontal=True,
        key="activity_date_mode",
    )

    computed_date = _resolve_activity_date_for_display(
        activity_date_mode=activity_date_mode,
        custom_date=form_data.get("activity_custom_date"),
    )

    custom_date_value = _coerce_date(
        form_data.get("activity_custom_date"),
        default=computed_date,
    )

    if activity_date_mode == "Choisir une date":
        custom_date_value = st.date_input(
            ACTIVITY_CUSTOM_DATE_LABEL,
            value=custom_date_value,
            min_value=date.today(),
            format="DD/MM/YYYY",
            key="activity_custom_date",
        )
        computed_date = custom_date_value
    else:
        st.session_state["activity_custom_date"] = computed_date

    st.caption(f"{ACTIVITY_PREVIEW_LABEL} : {_format_date_fr(computed_date)}")

    return {
        "create_activity": True,
        "activity_type": activity_type,
        "activity_summary": activity_summary,
        "activity_date_mode": activity_date_mode,
        "activity_custom_date": custom_date_value,
    }


def _validate_activity_data(raw_data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Validation locale du bloc activité.
    """
    errors: list[str] = []

    create_activity = bool(raw_data.get("create_activity", False))

    if not create_activity:
        return {
            "create_activity": False,
            "activity_type": DEFAULT_ACTIVITY_TYPE,
            "activity_summary": DEFAULT_ACTIVITY_SUMMARY,
            "activity_date_mode": DEFAULT_ACTIVITY_DATE_MODE,
            "activity_custom_date": None,
            "activity_deadline": None,
        }, errors

    activity_type = str(raw_data.get("activity_type") or "").strip()
    activity_summary = str(raw_data.get("activity_summary") or "").strip()
    activity_date_mode = str(raw_data.get("activity_date_mode") or "").strip()
    activity_custom_date = raw_data.get("activity_custom_date")

    if not activity_type:
        errors.append(ERROR_ACTIVITY_TYPE_REQUIRED)
    elif activity_type not in ACTIVITY_TYPE_LABELS:
        errors.append(ERROR_ACTIVITY_TYPE_REQUIRED)

    if not activity_summary:
        errors.append(ERROR_ACTIVITY_SUMMARY_REQUIRED)

    if activity_date_mode not in ACTIVITY_DATE_MODES:
        activity_date_mode = DEFAULT_ACTIVITY_DATE_MODE

    deadline = None

    if activity_date_mode in ("J+7", "J+30"):
        deadline = _compute_deadline_from_mode(activity_date_mode)

    elif activity_date_mode == "Choisir une date":
        if activity_custom_date in (None, "", False):
            errors.append(ERROR_ACTIVITY_DATE_REQUIRED)
        else:
            deadline = _coerce_date(activity_custom_date)
            if deadline is None:
                errors.append(ERROR_ACTIVITY_CUSTOM_DATE_INVALID)

    if deadline is None:
        if activity_date_mode != "Choisir une date":
            errors.append(ERROR_ACTIVITY_DATE_REQUIRED)
    else:
        if deadline < date.today():
            errors.append(ERROR_ACTIVITY_DATE_PAST)

    return {
        "create_activity": True,
        "activity_type": activity_type or DEFAULT_ACTIVITY_TYPE,
        "activity_summary": activity_summary or DEFAULT_ACTIVITY_SUMMARY,
        "activity_date_mode": activity_date_mode,
        "activity_custom_date": deadline if activity_date_mode == "Choisir une date" else None,
        "activity_deadline": deadline.isoformat() if deadline else None,
    }, errors


def _get_seller_index(seller_names):
    seller_name = st.session_state.get("seller_name")
    if seller_name in seller_names:
        return seller_names.index(seller_name)
    return 0


def _get_activity_type_index(value: Any) -> int:
    if value in ACTIVITY_TYPE_LABELS:
        return ACTIVITY_TYPE_LABELS.index(value)
    return ACTIVITY_TYPE_LABELS.index(DEFAULT_ACTIVITY_TYPE)


def _get_activity_date_mode_index(value: Any) -> int:
    if value in ACTIVITY_DATE_MODES:
        return ACTIVITY_DATE_MODES.index(value)
    return ACTIVITY_DATE_MODES.index(DEFAULT_ACTIVITY_DATE_MODE)


def _compute_deadline_from_mode(mode: str) -> date:
    today = date.today()
    if mode == "J+30":
        return today + timedelta(days=30)
    return today + timedelta(days=7)


def _resolve_activity_date_for_display(activity_date_mode: str, custom_date: Any) -> date:
    if activity_date_mode == "Choisir une date":
        custom = _coerce_date(custom_date)
        if custom is not None and custom >= date.today():
            return custom
        return date.today()

    return _compute_deadline_from_mode(activity_date_mode)


def _coerce_date(value: Any, default: date | None = None) -> date | None:
    if value is None:
        return default

    if isinstance(value, date):
        return value

    if hasattr(value, "date"):
        try:
            return value.date()
        except Exception:
            return default

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return default

        for sep in ("-", "/"):
            parts = cleaned.split(sep)
            if len(parts) == 3:
                try:
                    if sep == "-":
                        year, month, day = map(int, parts)
                        return date(year, month, day)
                    day, month, year = map(int, parts)
                    return date(year, month, day)
                except Exception:
                    continue

    return default


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
