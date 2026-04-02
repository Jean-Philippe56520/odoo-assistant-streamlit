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
)
from .console_utils import ERR, DIM


XMLRPC_RETRY_ATTEMPTS = 3
XMLRPC_RETRY_DELAY_SECONDS = 0.4
XMLRPC_TIMEOUT_SECONDS = 30


class TimeoutTransport(xmlrpc.client.Transport):
    """Transport XML-RPC HTTP avec timeout."""

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
    """Transport XML-RPC HTTPS avec timeout."""

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


COMMON_ENDPOINT = f"{ODOO_URL}/xmlrpc/2/common"
OBJECT_ENDPOINT = f"{ODOO_URL}/xmlrpc/2/object"
URL_SCHEME = urlparse(ODOO_URL).scheme.lower()


RETRYABLE_EXCEPTIONS = (
    http.client.CannotSendRequest,
    http.client.ResponseNotReady,
    ConnectionResetError,
    BrokenPipeError,
    TimeoutError,
    socket.timeout,
    xmlrpc.client.ProtocolError,
)


def _build_transport():
    if URL_SCHEME == "https":
        return TimeoutSafeTransport()
    return TimeoutTransport()


def _build_common_proxy():
    return xmlrpc.client.ServerProxy(
        COMMON_ENDPOINT,
        allow_none=True,
        use_datetime=True,
        transport=_build_transport(),
    )


def _build_object_proxy():
    return xmlrpc.client.ServerProxy(
        OBJECT_ENDPOINT,
        allow_none=True,
        use_datetime=True,
        transport=_build_transport(),
    )


def odoo_connect():
    """
    Authentifie l'utilisateur Odoo.

    Retourne :
    - uid
    - models : proxy XML-RPC objet, conservé pour compatibilité
    """
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

    # Compatibilité avec le reste du code existant
    return uid, _build_object_proxy()


def execute_kw(
    uid: int,
    model: str,
    method: str,
    args: Optional[list] = None,
    kwargs: Optional[dict] = None,
):
    """
    Exécute un appel Odoo avec une nouvelle connexion XML-RPC à chaque appel.
    C'est le point clé pour éviter les CannotSendRequest sous Streamlit.
    """
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
    """
    Le paramètre 'models' est conservé pour compatibilité,
    mais n'est plus utilisé.
    """
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
        return ids[0]

    return execute_kw(
        uid,
        TAG_MODEL,
        "create",
        args=[[{"name": tag_name}]],
    )


def find_team_ventes(models, uid):
    """
    Le paramètre 'models' est conservé pour compatibilité,
    mais n'est plus utilisé.
    """
    ids = execute_kw(
        uid,
        TEAM_MODEL,
        "search",
        args=[[("name", "ilike", "Ventes")]],
        kwargs={"limit": 1},
    )
    return ids[0] if ids else None


def get_active_sales_users(models, uid):
    """
    Le paramètre 'models' est conservé pour compatibilité,
    mais n'est plus utilisé.
    """
    return execute_kw(
        uid,
        USER_MODEL,
        "search_read",
        args=[[("active", "=", True)]],
        kwargs={"fields": ["id", "name", "login"], "order": "name asc"},
    )


def lead_exists(models, uid, email, phone, mobile=None):
    """
    Le paramètre 'models' est conservé pour compatibilité,
    mais n'est plus utilisé.
    """
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
    return ids[0] if ids else False