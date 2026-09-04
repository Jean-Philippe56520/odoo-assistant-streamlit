from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .config import LEAD_MODEL
from .odoo_client import execute_kw


MAX_DUPLICATE_CANDIDATES = 5
SEARCH_RESULT_LIMIT = 30
LEGAL_FORM_TOKENS = {
    "sa",
    "sarl",
    "sas",
    "sasu",
    "eurl",
    "sci",
    "societe",
    "ste",
}
LEAD_CANDIDATE_FIELDS = [
    "id",
    "name",
    "partner_name",
    "contact_name",
    "email_from",
    "phone",
    "mobile",
    "city",
    "zip",
    "user_id",
    "priority",
    "description",
]


@dataclass(frozen=True)
class LeadDuplicateCandidate:
    lead_id: int
    summary: dict
    match_level: str
    reasons: tuple[str, ...]

    @property
    def is_strong_match(self) -> bool:
        return self.match_level == "strong"


def normalize_email_for_match(value) -> str:
    return str(value or "").strip().lower()


def _ascii_words(value) -> list[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return []
    raw = "".join(
        char
        for char in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(char)
    )
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    return [token for token in raw.split() if token]


def normalize_company_name(value) -> str:
    tokens = [token for token in _ascii_words(value) if token not in LEGAL_FORM_TOKENS]
    return " ".join(tokens)


def normalize_city_name(value) -> str:
    return " ".join(_ascii_words(value))


def normalize_phone_for_match(value) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""

    # ABM prospecte principalement en France : on rapproche explicitement
    # les formats 06..., +33 6... et 0033 6... sans modifier les autres pays.
    if digits.startswith("0033") and len(digits) == 13:
        return "0" + digits[4:]
    if digits.startswith("33") and len(digits) == 11:
        return "0" + digits[2:]
    return digits


def _phone_search_chunks(canonical_phone: str) -> list[str]:
    if len(canonical_phone) < 8:
        return []

    tail = canonical_phone[-8:]
    aligned = [tail[index:index + 2] for index in range(0, len(tail), 2)]
    chunks = []
    for chunk in aligned:
        if len(chunk) == 2 and chunk not in chunks:
            chunks.append(chunk)

    # Les numéros très répétitifs donnent peu de paires uniques. On complète
    # avec des paires glissantes, sans jamais les utiliser comme preuve finale.
    if len(chunks) < 2:
        for index in range(0, len(tail) - 1):
            chunk = tail[index:index + 2]
            if chunk not in chunks:
                chunks.append(chunk)
            if len(chunks) >= 3:
                break

    return chunks[:4]


def _search_read(uid: int, domain: list, limit: int = SEARCH_RESULT_LIMIT) -> list[dict]:
    if not domain:
        return []
    return execute_kw(
        uid,
        LEAD_MODEL,
        "search_read",
        args=[domain],
        kwargs={
            "fields": LEAD_CANDIDATE_FIELDS,
            "limit": limit,
            "order": "id desc",
        },
    ) or []


def _merge_rows_by_id(target: dict[int, dict], rows: list[dict]):
    for row in rows:
        lead_id = row.get("id")
        if lead_id:
            target[int(lead_id)] = row


def _search_strong_candidate_rows(uid: int, data: dict) -> dict[int, dict]:
    rows_by_id: dict[int, dict] = {}
    email = normalize_email_for_match(data.get("email_from"))
    if email:
        _merge_rows_by_id(
            rows_by_id,
            _search_read(uid, [("email_from", "=ilike", email)]),
        )

    input_phones = {
        normalized
        for normalized in (
            normalize_phone_for_match(data.get("phone")),
            normalize_phone_for_match(data.get("mobile")),
        )
        if normalized
    }

    for canonical_phone in input_phones:
        chunks = _phone_search_chunks(canonical_phone)
        if not chunks:
            continue
        for field_name in ("phone", "mobile"):
            domain = [(field_name, "ilike", chunk) for chunk in chunks]
            _merge_rows_by_id(rows_by_id, _search_read(uid, domain))

    return rows_by_id


def _longest_search_token(normalized_value: str, minimum_length: int = 3) -> str:
    tokens = [token for token in normalized_value.split() if len(token) >= minimum_length]
    return max(tokens, key=len) if tokens else ""


def _search_company_city_rows(uid: int, data: dict) -> dict[int, dict]:
    company = normalize_company_name(data.get("partner_name"))
    city = normalize_city_name(data.get("city"))

    # Les noms trop courts sont volontairement ignorés pour réduire les faux positifs.
    if len(company) < 5 or len(city) < 2:
        return {}

    company_token = _longest_search_token(company)
    city_token = _longest_search_token(city, minimum_length=2)
    if not company_token or not city_token:
        return {}

    rows = _search_read(
        uid,
        [
            ("partner_name", "ilike", company_token),
            ("city", "ilike", city_token),
        ],
    )
    return {int(row["id"]): row for row in rows if row.get("id")}


def classify_lead_candidates(
    data: dict,
    rows: list[dict],
    limit: int = MAX_DUPLICATE_CANDIDATES,
) -> list[LeadDuplicateCandidate]:
    input_email = normalize_email_for_match(data.get("email_from"))
    input_phones = {
        normalized
        for normalized in (
            normalize_phone_for_match(data.get("phone")),
            normalize_phone_for_match(data.get("mobile")),
        )
        if normalized
    }
    input_company = normalize_company_name(data.get("partner_name"))
    input_city = normalize_city_name(data.get("city"))

    candidates = []
    for row in rows:
        lead_id = row.get("id")
        if not lead_id:
            continue

        reasons = []
        row_email = normalize_email_for_match(row.get("email_from"))
        if input_email and row_email == input_email:
            reasons.append("email")

        row_phones = {
            normalized
            for normalized in (
                normalize_phone_for_match(row.get("phone")),
                normalize_phone_for_match(row.get("mobile")),
            )
            if normalized
        }
        if input_phones and input_phones.intersection(row_phones):
            reasons.append("phone")

        same_company_city = (
            len(input_company) >= 5
            and input_company == normalize_company_name(row.get("partner_name"))
            and bool(input_city)
            and input_city == normalize_city_name(row.get("city"))
        )
        if same_company_city:
            reasons.append("company_city")

        if "email" in reasons or "phone" in reasons:
            level = "strong"
        elif "company_city" in reasons:
            level = "company_city"
        else:
            continue

        candidates.append(
            LeadDuplicateCandidate(
                lead_id=int(lead_id),
                summary=dict(row),
                match_level=level,
                reasons=tuple(reasons),
            )
        )

    def sort_key(candidate: LeadDuplicateCandidate):
        reason_score = ("email" in candidate.reasons) * 2 + ("phone" in candidate.reasons)
        level_score = 1 if candidate.is_strong_match else 0
        return (level_score, reason_score, candidate.lead_id)

    candidates.sort(key=sort_key, reverse=True)
    return candidates[:limit]


def find_lead_candidates(
    uid: int,
    data: dict,
    limit: int = MAX_DUPLICATE_CANDIDATES,
) -> list[LeadDuplicateCandidate]:
    rows_by_id = _search_strong_candidate_rows(uid, data)
    rows_by_id.update(_search_company_city_rows(uid, data))
    return classify_lead_candidates(data, list(rows_by_id.values()), limit=limit)
