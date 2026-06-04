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
        "reload_flag": reload_flag,
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
    html = r"""
<script>
(function () {
  const CONNECTION_OVERLAY_ID = "abm-connection-overlay";
  const RESUME_OVERLAY_ID = "abm-resume-overlay";
  const HEALTH_URL = window.location.origin + "/_stcore/health";
  const BACKGROUNDED_KEY = "abm_odoo_app_was_backgrounded_v1";
  const HIDDEN_AT_KEY = "abm_odoo_hidden_at_v1";
  const INTERNAL_RELOAD_KEY = "abm_odoo_internal_reload_v1";
  const RELOAD_FLAG_KEY = "__RELOAD_FLAG_KEY__";
  let resumeCheckInProgress = false;

  function storage() {
    return window.parent.localStorage;
  }

  function ensureConnectionOverlay() {
    let overlay = window.parent.document.getElementById(CONNECTION_OVERLAY_ID);
    if (!overlay) {
      overlay = window.parent.document.createElement("div");
      overlay.id = CONNECTION_OVERLAY_ID;
      overlay.style.cssText = [
        "display:none",
        "position:fixed",
        "z-index:2147483646",
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

  function ensureResumeOverlay() {
    let overlay = window.parent.document.getElementById(RESUME_OVERLAY_ID);
    if (!overlay) {
      overlay = window.parent.document.createElement("div");
      overlay.id = RESUME_OVERLAY_ID;
      overlay.style.cssText = [
        "display:none",
        "position:fixed",
        "z-index:2147483647",
        "inset:0",
        "background:rgba(2,6,23,0.92)",
        "color:white",
        "font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
        "padding:22px",
        "box-sizing:border-box",
        "align-items:center",
        "justify-content:center"
      ].join(";");
      overlay.innerHTML = `
        <div style="max-width:540px;width:100%;background:#111827;border:1px solid #374151;border-radius:18px;padding:22px;box-shadow:0 18px 50px rgba(0,0,0,.45)">
          <div id="abm-resume-title" style="font-size:22px;font-weight:750;margin-bottom:10px">Vérification de l'application</div>
          <div id="abm-resume-message" style="font-size:16px;line-height:1.45;color:#d1d5db;margin-bottom:16px">
            L'application revient au premier plan. Vérification en cours avant de continuer.
          </div>
          <div id="abm-resume-spinner" style="width:32px;height:32px;border:4px solid #374151;border-top-color:#ffffff;border-radius:50%;animation:abmSpin 1s linear infinite;margin:8px auto 16px auto"></div>
          <div id="abm-resume-actions" style="display:none;gap:10px;flex-direction:column">
            <button id="abm-resume-retry-button" style="width:100%;border:0;border-radius:12px;background:#2563eb;color:white;font-size:17px;font-weight:700;padding:13px 16px;cursor:pointer">
              Réessayer
            </button>
            <button id="abm-resume-reload-button" style="width:100%;border:0;border-radius:12px;background:#ef4444;color:white;font-size:17px;font-weight:700;padding:13px 16px;cursor:pointer">
              Recharger l'application
            </button>
          </div>
          <div style="font-size:13px;line-height:1.35;color:#9ca3af;margin-top:12px">
            Si une saisie était commencée, le brouillon local sera conservé et pourra être repris après rechargement.
          </div>
        </div>`;
      const style = window.parent.document.createElement("style");
      style.textContent = "@keyframes abmSpin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}";
      window.parent.document.head.appendChild(style);
      window.parent.document.body.appendChild(overlay);

      const retryButton = window.parent.document.getElementById("abm-resume-retry-button");
      if (retryButton) {
        retryButton.addEventListener("click", function () {
          verifyThenReload("manual_retry");
        });
      }

      const reloadButton = window.parent.document.getElementById("abm-resume-reload-button");
      if (reloadButton) {
        reloadButton.addEventListener("click", function () {
          requestReload("manual_resume_button");
        });
      }
    }
    return overlay;
  }

  function showConnectionOverlay() {
    ensureConnectionOverlay().style.display = "block";
  }

  function hideConnectionOverlay() {
    ensureConnectionOverlay().style.display = "none";
  }

  function showResumeOverlay(message, isError) {
    const overlay = ensureResumeOverlay();
    const title = window.parent.document.getElementById("abm-resume-title");
    const body = window.parent.document.getElementById("abm-resume-message");
    const spinner = window.parent.document.getElementById("abm-resume-spinner");
    const actions = window.parent.document.getElementById("abm-resume-actions");
    if (title) { title.textContent = isError ? "Connexion interrompue" : "Vérification de l'application"; }
    if (body) { body.textContent = message; }
    if (spinner) { spinner.style.display = isError ? "none" : "block"; }
    if (actions) { actions.style.display = isError ? "flex" : "none"; }
    overlay.style.display = "flex";
  }

  function markBackgrounded() {
    if (storage().getItem(INTERNAL_RELOAD_KEY) === "1") {
      return;
    }
    storage().setItem(BACKGROUNDED_KEY, "1");
    storage().setItem(HIDDEN_AT_KEY, String(Date.now()));
  }

  function requestReload(reason) {
    const payload = JSON.stringify({
      requested_at: new Date().toISOString(),
      reason: reason || "background_resume"
    });
    storage().setItem(RELOAD_FLAG_KEY, payload);
    storage().removeItem(BACKGROUNDED_KEY);
    storage().setItem(INTERNAL_RELOAD_KEY, "1");
    window.parent.location.reload();
  }

  async function fetchHealth(timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(function () { controller.abort(); }, timeoutMs || 3500);
    try {
      const response = await fetch(HEALTH_URL, {
        method: "GET",
        cache: "no-store",
        signal: controller.signal
      });
      clearTimeout(timer);
      return response.ok;
    } catch (error) {
      clearTimeout(timer);
      return false;
    }
  }

  async function verifyThenReload(reason) {
    if (resumeCheckInProgress) {
      return;
    }
    resumeCheckInProgress = true;
    showResumeOverlay(
      "L'application revient au premier plan. Vérification en cours avant rechargement sécurisé.",
      false
    );
    const ok = await fetchHealth(3500);
    if (ok) {
      requestReload(reason || "background_resume");
      return;
    }
    resumeCheckInProgress = false;
    showResumeOverlay(
      "L'application ne répond pas correctement. Vérifiez votre réseau, puis réessayez ou rechargez l'application.",
      true
    );
  }

  async function checkHealth() {
    const ok = await fetchHealth(4000);
    if (ok) {
      hideConnectionOverlay();
    } else {
      showConnectionOverlay();
    }
  }

  function needsResumeReload() {
    return storage().getItem(BACKGROUNDED_KEY) === "1";
  }

  function handleReturnToForeground() {
    if (window.parent.document.hidden) {
      return;
    }
    if (needsResumeReload()) {
      verifyThenReload("background_resume");
      return;
    }
    checkHealth();
  }

  function interceptFirstInteraction(event) {
    if (!needsResumeReload()) {
      return;
    }
    const overlay = window.parent.document.getElementById(RESUME_OVERLAY_ID);
    if (overlay && overlay.contains(event.target)) {
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    verifyThenReload("first_interaction_after_background");
  }

  try {
    storage().removeItem(INTERNAL_RELOAD_KEY);
    if (!window.parent.document.hidden && storage().getItem(BACKGROUNDED_KEY) === "1") {
      verifyThenReload("initial_visible_with_background_flag");
    }
  } catch (error) {
    // localStorage can be unavailable in rare restrictive browser contexts.
  }

  window.parent.document.addEventListener("visibilitychange", function () {
    if (window.parent.document.hidden) {
      markBackgrounded();
    } else {
      handleReturnToForeground();
    }
  });

  window.parent.addEventListener("pagehide", function () {
    markBackgrounded();
  });

  window.parent.addEventListener("pageshow", function () {
    handleReturnToForeground();
  });

  window.parent.addEventListener("focus", function () {
    handleReturnToForeground();
  });

  window.parent.document.addEventListener("pointerdown", interceptFirstInteraction, true);
  window.parent.document.addEventListener("touchstart", interceptFirstInteraction, true);
  window.parent.document.addEventListener("keydown", interceptFirstInteraction, true);
  window.parent.document.addEventListener("focusin", interceptFirstInteraction, true);

  window.parent.addEventListener("online", checkHealth);
  window.parent.addEventListener("offline", showConnectionOverlay);

  checkHealth();
  setInterval(checkHealth, 30000);
})();
</script>
    """.replace("__RELOAD_FLAG_KEY__", RELOAD_FLAG_KEY)
    components.html(html, height=0, width=0)
