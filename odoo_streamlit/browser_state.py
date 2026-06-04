import json
from datetime import datetime, timezone
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from streamlit_js_eval import streamlit_js_eval

APP_STATE_KEY = "abm_odoo_app_state_v1"
DRAFT_KEY = "abm_odoo_lead_draft_v1"
RELOAD_FLAG_KEY = "abm_odoo_reload_requested_v1"

FORM_FIELD_KEYS = (
    "partner_name",
    "contact_name",
    "phone",
    "mobile",
    "email_from",
    "street",
    "street2",
    "zip",
    "city",
    "current_equipment",
    "free_comment",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _read_raw_storage(key_name: str, component_key: str):
    expression = f"localStorage.getItem({_json(key_name)})"
    return streamlit_js_eval(
        js_expressions=expression,
        key=component_key,
        want_output=True,
    )


def read_json_storage(key_name: str, component_key: str, default=None):
    raw = _read_raw_storage(key_name, component_key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def write_json_storage(key_name: str, value: dict, component_key: str):
    expression = f"localStorage.setItem({_json(key_name)}, {_json(_json(value))})"
    streamlit_js_eval(
        js_expressions=expression,
        key=component_key,
        want_output=False,
    )


def remove_storage(key_name: str, component_key: str):
    expression = f"localStorage.removeItem({_json(key_name)})"
    streamlit_js_eval(
        js_expressions=expression,
        key=component_key,
        want_output=False,
    )


def reload_app(component_key: str = "reload_app"):
    payload = {"requested_at": now_iso()}
    expression = (
        f"localStorage.setItem({_json(RELOAD_FLAG_KEY)}, {_json(_json(payload))});"
        "window.location.reload();"
    )
    streamlit_js_eval(
        js_expressions=expression,
        key=component_key,
        want_output=False,
    )


def mark_current_session(current_session_id: str, component_key: str):
    write_json_storage(
        APP_STATE_KEY,
        {
            "streamlit_session_id": current_session_id,
            "last_seen": now_iso(),
        },
        component_key=component_key,
    )
    remove_storage(RELOAD_FLAG_KEY, component_key=f"{component_key}_clear_reload")


def get_browser_snapshot(current_session_id: str) -> dict:
    app_state = read_json_storage(APP_STATE_KEY, "read_browser_app_state", default={}) or {}
    draft = read_json_storage(DRAFT_KEY, "read_browser_draft", default={}) or {}
    reload_flag = read_json_storage(RELOAD_FLAG_KEY, "read_browser_reload_flag", default={}) or {}

    saved_session_id = app_state.get("streamlit_session_id")
    draft_exists = has_meaningful_draft(draft)
    reload_requested = bool(reload_flag.get("requested_at"))

    if not saved_session_id:
        status = "new_browser_state"
    elif saved_session_id == current_session_id:
        status = "ok"
    elif reload_requested:
        status = "ok_after_requested_reload"
    else:
        status = "session_reset"

    return {
        "status": status,
        "app_state": app_state,
        "draft": draft,
        "draft_exists": draft_exists,
        "reload_requested": reload_requested,
    }


def has_meaningful_draft(data: dict | None) -> bool:
    if not data:
        return False
    for key in FORM_FIELD_KEYS + ("seller_name",):
        if str(data.get(key) or "").strip():
            return True
    return False


def build_draft_from_session(seller_name: str | None = None) -> dict:
    data = {key: str(st.session_state.get(key, "") or "") for key in FORM_FIELD_KEYS}
    if seller_name:
        data["seller_name"] = seller_name
    elif st.session_state.get("seller_name"):
        data["seller_name"] = st.session_state.get("seller_name")
    data["saved_at"] = now_iso()
    return data


def save_local_draft(data: dict, component_key: str = "save_local_draft"):
    if has_meaningful_draft(data):
        payload = dict(data)
        payload["saved_at"] = now_iso()
        write_json_storage(DRAFT_KEY, payload, component_key=component_key)
    else:
        remove_storage(DRAFT_KEY, component_key=f"{component_key}_clear")


def clear_local_draft(component_key: str = "clear_local_draft"):
    remove_storage(DRAFT_KEY, component_key=component_key)


def restore_draft_to_session_state(draft: dict, seller_names: list[str] | None = None):
    form_data = {}
    for key in FORM_FIELD_KEYS:
        value = str(draft.get(key, "") or "")
        st.session_state[key] = value
        form_data[key] = value

    st.session_state["form_data"] = form_data

    seller_name = draft.get("seller_name")
    if seller_name and (not seller_names or seller_name in seller_names):
        st.session_state["seller_name"] = seller_name
        st.session_state["seller_selectbox"] = seller_name

    st.session_state["draft_restored"] = True
    st.session_state["draft_prompt_dismissed"] = True


def render_connection_watchdog():
    components.html(
        """
<script>
(function () {
  const OVERLAY_ID = "abm-connection-overlay";
  const HEALTH_URL = window.location.origin + "/_stcore/health";

  function ensureOverlay() {
    let overlay = window.parent.document.getElementById(OVERLAY_ID);
    if (!overlay) {
      overlay = window.parent.document.createElement("div");
      overlay.id = OVERLAY_ID;
      overlay.style.cssText = [
        "display:none",
        "position:fixed",
        "z-index:2147483647",
        "left:0",
        "right:0",
        "bottom:0",
        "padding:14px 16px",
        "background:#7f1d1d",
        "color:white",
        "font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
        "font-size:15px",
        "box-shadow:0 -2px 12px rgba(0,0,0,0.25)"
      ].join(";");
      overlay.innerHTML = '<strong>Connexion interrompue.</strong><br>L\'application ne répond pas correctement. Vérifiez le réseau ou rechargez avant de continuer.';
      window.parent.document.body.appendChild(overlay);
    }
    return overlay;
  }

  function showOverlay() {
    ensureOverlay().style.display = "block";
  }

  function hideOverlay() {
    ensureOverlay().style.display = "none";
  }

  async function checkHealth() {
    const controller = new AbortController();
    const timer = setTimeout(function () { controller.abort(); }, 4000);
    try {
      const response = await fetch(HEALTH_URL, {
        method: "GET",
        cache: "no-store",
        signal: controller.signal
      });
      clearTimeout(timer);
      if (response.ok) {
        hideOverlay();
      } else {
        showOverlay();
      }
    } catch (error) {
      clearTimeout(timer);
      showOverlay();
    }
  }

  window.parent.document.addEventListener("visibilitychange", function () {
    if (!window.parent.document.hidden) {
      checkHealth();
    }
  });

  window.parent.addEventListener("online", checkHealth);
  window.parent.addEventListener("offline", showOverlay);
  checkHealth();
  setInterval(checkHealth, 30000);
})();
</script>
        """,
        height=0,
        width=0,
    )
