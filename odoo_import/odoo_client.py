import http.client
import socket
import time
import xmlrpc.client
from typing import Optional
from urllib.parse import urlparse

from .config import (
    ODOO_URL,
    ODOO_DB,
    ODOO_USER,
    ODOO_API_KEY,
    LEAD_MODEL,
    TAG_MODEL,
    TEAM_MODEL,
    USER_MODEL,
    get_missing_odoo_settings,
)
from .console_utils import ERR, DIM


XMLRPC_RETRY_ATTEMPTS = 3
XMLRPC_RETRY_DELAY_SECONDS = 0.4
XMLRPC_TIMEOUT_SECONDS = 30

ACTIVITY_MODEL = "mail.activity"
ACTIVITY_TYPE_MODEL = "mail.activity.type"


class TimeoutTransport(xmlrpc.client.Transport):
    def __init__(self, timeout: int = XMLRPC_TIMEOUT_SECONDS, use_datetime: bool = False):
        super().__init__(use_datetime=use_datetime)
        self._timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        try:
            connection.timeout = self._timeout
        except Exception:
            pass
        return connection


class TimeoutSafeTransport(xmlrpc.client.SafeTransport):
    def __init__(self, timeout: int = XMLRPC_TIMEOUT_SECONDS, use_datetime: bool = False):
        super().__init__(use_datetime=use_datetime)
        self._timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        try:
            connection.timeout = self._timeout
        except Exception:
            pass
        return connection


RETRYABLE_EXCEPTIONS = (
    http.client.CannotSendRequest,
    http.client.ResponseNotReady,
    ConnectionResetError,
    BrokenPipeError,
    TimeoutError,
    socket.timeout,
    xmlrpc.client.ProtocolError,
)


def _validate_odoo_configuration():
    missing = get_missing_odoo_settings()
    if missing:
        raise RuntimeError("Configuration Odoo manquante : " + ", ".join(missing))


def _get_common_endpoint() -> str:
    _validate_odoo_configuration()
    return f"{ODOO_URL}/xmlrpc/2/common"


def _get_object_endpoint() -> str:
    _validate_odoo_configuration()
    return f"{ODOO_URL}/xmlrpc/2/object"


def _get_url_scheme() -> str:
    if not ODOO_URL:
        return ""
    return urlparse(ODOO_URL).scheme.lower()


def _build_transport():
    if _get_url_scheme() == "https":
        return TimeoutSafeTransport()
    return TimeoutTransport()


def _build_common_proxy():
    return xmlrpc.client.ServerProxy(
        _get_common_endpoint(),
        allow_none=True,
        use_datetime=True,
        transport=_build_transport(),
    )


def _build_object_proxy():
    return xmlrpc.client.ServerProxy(
        _get_object_endpoint(),
        allow_none=True,
        use_datetime=True,
        transport=_build_transport(),
    )


def odoo_connect():
    _validate_odoo_configuration()

    common = _build_common_proxy()
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

    return uid, _build_object_proxy()


def execute_kw(
    uid: int,
    model: str,
    method: str,
    args: Optional[list] = None,
    kwargs: Optional[dict] = None,
):
    _validate_odoo_configuration()

    args = args or []
    kwargs = kwargs or {}
    last_error: Optional[Exception] = None

    for attempt in range(1, XMLRPC_RETRY_ATTEMPTS + 1):
        try:
            models = _build_object_proxy()
            return models.execute_kw(
                ODOO_DB,
                uid,
                ODOO_API_KEY,
                model,
                method,
                args,
                kwargs,
            )
        except xmlrpc.client.Fault:
            raise
        except RETRYABLE_EXCEPTIONS as exc:
            last_error = exc
            if attempt >= XMLRPC_RETRY_ATTEMPTS:
                break
            time.sleep(XMLRPC_RETRY_DELAY_SECONDS * attempt)
        except Exception as exc:
            raise RuntimeError(f"Erreur Odoo sur {model}.{method} : {exc}") from exc

    raise RuntimeError(
        f"Erreur réseau XML-RPC sur {model}.{method} après {XMLRPC_RETRY_ATTEMPTS} tentatives : {last_error}"
    )


def find_or_create_tag(models, uid, tag_name: str) -> int:
    tag_name = str(tag_name or "").strip()
    if not tag_name:
        raise ValueError("Le nom du tag est vide.")

    ids = execute_kw(
        uid,
        TAG_MODEL,
        "search",
        args=[[("name", "=", tag_name)]],
        kwargs={"limit": 1},
    )
    if ids:
        return _normalize_record_id(ids[0])

    created = execute_kw(
        uid,
        TAG_MODEL,
        "create",
        args=[[{"name": tag_name}]],
    )
    return _normalize_record_id(created)


def find_team_ventes(models, uid):
    ids = execute_kw(
        uid,
        TEAM_MODEL,
        "search",
        args=[[("name", "ilike", "Ventes")]],
        kwargs={"limit": 1},
    )
    return _normalize_record_id(ids[0]) if ids else None


def get_active_sales_users(models, uid):
    return execute_kw(
        uid,
        USER_MODEL,
        "search_read",
        args=[[("active", "=", True)]],
        kwargs={"fields": ["id", "name", "login"], "order": "name asc"},
    )


def lead_exists(models, uid, email, phone, mobile=None):
    email = (email or "").strip()
    phone = (phone or "").strip()
    mobile = (mobile or "").strip()

    if not (email or phone or mobile):
        return False

    terms = []
    if email:
        terms.append(("email_from", "=", email))
    if phone:
        terms.append(("phone", "=", phone))
    if mobile:
        terms.append(("mobile", "=", mobile))

    if len(terms) == 1:
        domain = terms
    else:
        domain = ["|"] * (len(terms) - 1) + terms

    ids = execute_kw(
        uid,
        LEAD_MODEL,
        "search",
        args=[domain],
        kwargs={"limit": 1},
    )
    return _normalize_record_id(ids[0]) if ids else False


def get_model_id_by_name(uid: int, model_name: str) -> int:
    ids = execute_kw(
        uid,
        "ir.model",
        "search",
        args=[[("model", "=", model_name)]],
        kwargs={"limit": 1},
    )
    if not ids:
        raise RuntimeError(f"Modèle Odoo introuvable dans ir.model : {model_name}")
    return _normalize_record_id(ids[0])


def resolve_activity_type_by_name(uid: int, activity_type_name: str) -> int | None:
    activity_type_name = str(activity_type_name or "").strip()
    if not activity_type_name:
        return None

    ids = execute_kw(
        uid,
        ACTIVITY_TYPE_MODEL,
        "search",
        args=[[("name", "=", activity_type_name)]],
        kwargs={"limit": 1},
    )
    if ids:
        return _normalize_record_id(ids[0])

    ids = execute_kw(
        uid,
        ACTIVITY_TYPE_MODEL,
        "search",
        args=[[("name", "ilike", activity_type_name)]],
        kwargs={"limit": 1},
    )
    if ids:
        return _normalize_record_id(ids[0])

    return None


def get_default_todo_activity_type_id(uid: int) -> int | None:
    for candidate in ("To-Do", "Tâche", "Todo"):
        activity_type_id = resolve_activity_type_by_name(uid, candidate)
        if activity_type_id:
            return activity_type_id
    return None


def create_activity_for_lead(uid: int, lead_id: int, activity_vals: dict) -> int:
    if not lead_id:
        raise ValueError("lead_id manquant pour la création d'activité.")

    if not activity_vals:
        raise ValueError("activity_vals vide.")

    lead_id = _normalize_record_id(lead_id)

    summary = str(activity_vals.get("summary") or "").strip()
    date_deadline = str(activity_vals.get("date_deadline") or "").strip()
    user_id = _normalize_record_id(activity_vals.get("user_id"))
    activity_type_id = activity_vals.get("activity_type_id")
    activity_type_label = str(activity_vals.get("_activity_type_label") or "").strip()

    if not summary:
        raise ValueError("Le résumé de l'activité est obligatoire.")
    if not date_deadline:
        raise ValueError("La date d'échéance de l'activité est obligatoire.")

    if not activity_type_id:
        if activity_type_label:
            activity_type_id = resolve_activity_type_by_name(uid, activity_type_label)
        if not activity_type_id:
            activity_type_id = get_default_todo_activity_type_id(uid)

    if not activity_type_id:
        raise RuntimeError("Impossible de résoudre un type d'activité Odoo valide.")

    activity_type_id = _normalize_record_id(activity_type_id)
    res_model_id = get_model_id_by_name(uid, LEAD_MODEL)

    create_vals = {
        "res_model_id": res_model_id,
        "res_id": lead_id,
        "activity_type_id": activity_type_id,
        "summary": summary,
        "date_deadline": date_deadline,
        "user_id": user_id,
    }

    note = activity_vals.get("note")
    if note:
        create_vals["note"] = str(note)

    created = execute_kw(
        uid,
        ACTIVITY_MODEL,
        "create",
        args=[[create_vals]],
    )
    return _normalize_record_id(created)


def _normalize_record_id(value) -> int:
    """
    Sécurise tous les IDs venant d'Odoo / XML-RPC.
    Accepte :
    - 21101
    - "21101"
    - [21101]
    - ("21101",)
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
