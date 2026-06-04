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
    payload = {"requested_at": now_iso(), "reason": "manual_streamlit_reload"}
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
    """Inject browser-side safeguards for mobile resume and local draft capture.

    The critical parts run in the browser, not in Streamlit Python:
    - when the page goes background, the browser marks it locally;
    - when it returns, an immediate neutral overlay is displayed;
    - after a short visible delay, the parent page reloads;
    - draft data typed in the DOM is captured directly on input/change/pagehide.
    """
    html = r"""
<script>
(function () {
  const RESUME_OVERLAY_ID = "abm-resume-overlay";
  const BACKGROUNDED_KEY = "abm_odoo_app_was_backgrounded_v1";
  const HIDDEN_AT_KEY = "abm_odoo_hidden_at_v1";
  const INTERNAL_RELOAD_KEY = "abm_odoo_internal_reload_v1";
  const RELOAD_FLAG_KEY = "__RELOAD_FLAG_KEY__";
  const DRAFT_KEY = "__DRAFT_KEY__";
  const MIN_OVERLAY_MS = 700;
  let reloadScheduled = false;
  let draftSaveTimer = null;

  function getRootWindow() {
    try {
      if (window.parent && window.parent.document) {
        return window.parent;
      }
    } catch (error) {}
    return window;
  }

  function getRootDocument() {
    return getRootWindow().document || document;
  }

  function storage() {
    return getRootWindow().localStorage || window.localStorage;
  }

  function safeStorageGet(key) {
    try { return storage().getItem(key); } catch (error) { return null; }
  }

  function safeStorageSet(key, value) {
    try { storage().setItem(key, value); } catch (error) {}
  }

  function safeStorageRemove(key) {
    try { storage().removeItem(key); } catch (error) {}
  }

  function ensureResumeOverlay() {
    const doc = getRootDocument();
    let overlay = doc.getElementById(RESUME_OVERLAY_ID);
    if (!overlay) {
      overlay = doc.createElement("div");
      overlay.id = RESUME_OVERLAY_ID;
      overlay.setAttribute("aria-live", "polite");
      overlay.style.cssText = [
        "display:none",
        "position:fixed",
        "z-index:2147483647",
        "inset:0",
        "background:rgba(248,250,252,0.98)",
        "color:#0f172a",
        "font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
        "padding:22px",
        "box-sizing:border-box",
        "align-items:center",
        "justify-content:center",
        "text-align:left"
      ].join(";");
      overlay.innerHTML = `
        <div style="max-width:520px;width:100%;background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;padding:22px;box-shadow:0 18px 50px rgba(15,23,42,.16)">
          <div style="font-size:22px;font-weight:750;margin-bottom:10px;color:#0f172a">Préparation de l'application</div>
          <div id="abm-resume-message" style="font-size:16px;line-height:1.45;color:#334155;margin-bottom:16px">
            L'application se remet à jour pour sécuriser votre saisie.
          </div>
          <div style="display:flex;align-items:center;gap:12px;margin:8px 0 16px 0;color:#475569">
            <div style="width:26px;height:26px;border:3px solid #cbd5e1;border-top-color:#2563eb;border-radius:50%;animation:abmSpin 1s linear infinite"></div>
            <div style="font-size:14px">Rechargement en cours...</div>
          </div>
          <div style="font-size:13px;line-height:1.35;color:#64748b">
            Si une saisie était commencée, le brouillon local sera conservé et pourra être repris après rechargement.
          </div>
          <div id="abm-resume-actions" style="display:none;margin-top:16px;gap:10px;flex-direction:column">
            <button id="abm-resume-reload-button" style="width:100%;border:0;border-radius:12px;background:#2563eb;color:white;font-size:17px;font-weight:700;padding:13px 16px;cursor:pointer">
              Recharger l'application
            </button>
          </div>
        </div>`;
      const style = doc.createElement("style");
      style.textContent = "@keyframes abmSpin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}";
      doc.head.appendChild(style);
      doc.body.appendChild(overlay);

      const reloadButton = doc.getElementById("abm-resume-reload-button");
      if (reloadButton) {
        reloadButton.addEventListener("click", function () {
          requestReload("manual_resume_button", 0);
        });
      }
    }
    return overlay;
  }

  function showResumeOverlay(message, showManualAction) {
    const doc = getRootDocument();
    const overlay = ensureResumeOverlay();
    const body = doc.getElementById("abm-resume-message");
    const actions = doc.getElementById("abm-resume-actions");
    if (body) {
      body.textContent = message || "L'application se remet à jour pour sécuriser votre saisie.";
    }
    if (actions) {
      actions.style.display = showManualAction ? "flex" : "none";
    }
    overlay.style.display = "flex";
  }

  function formFieldDescriptors() {
    return [
      ["partner_name", "input[aria-label=\"Nom de l'entreprise *\"]"],
      ["contact_name", "input[aria-label=\"Nom du contact\"]"],
      ["phone", "input[aria-label=\"Téléphone\"]"],
      ["mobile", "input[aria-label=\"Mobile\"]"],
      ["email_from", "input[aria-label=\"Email\"]"],
      ["street", "input[aria-label=\"Adresse\"]"],
      ["street2", "input[aria-label=\"Complément d'adresse\"]"],
      ["zip", "input[aria-label=\"Code postal\"]"],
      ["city", "input[aria-label=\"Ville\"]"],
      ["current_equipment", "textarea[aria-label=\"Équipement actuel\"]"],
      ["free_comment", "textarea[aria-label=\"Commentaire libre\"]"]
    ];
  }

  function hasMeaningfulDraft(data) {
    const keys = ["partner_name", "contact_name", "phone", "mobile", "email_from", "street", "street2", "zip", "city", "current_equipment", "free_comment", "seller_name"];
    return keys.some(function (key) { return String((data && data[key]) || "").trim().length > 0; });
  }

  function readExistingDraft() {
    const raw = safeStorageGet(DRAFT_KEY);
    if (!raw) { return {}; }
    try { return JSON.parse(raw) || {}; } catch (error) { return {}; }
  }

  function collectDraftFromDom() {
    const doc = getRootDocument();
    const draft = Object.assign({}, readExistingDraft());
    formFieldDescriptors().forEach(function (pair) {
      const key = pair[0];
      const selector = pair[1];
      const element = doc.querySelector(selector);
      if (element && typeof element.value !== "undefined") {
        draft[key] = String(element.value || "");
      }
    });
    draft.saved_at = new Date().toISOString();
    draft.source = "browser_dom";
    return draft;
  }

  function saveDraftFromDom() {
    const draft = collectDraftFromDom();
    if (hasMeaningfulDraft(draft)) {
      safeStorageSet(DRAFT_KEY, JSON.stringify(draft));
    } else {
      safeStorageRemove(DRAFT_KEY);
    }
  }

  function scheduleDraftSave() {
    if (draftSaveTimer) {
      clearTimeout(draftSaveTimer);
    }
    draftSaveTimer = setTimeout(saveDraftFromDom, 120);
  }

  function markBackgrounded() {
    saveDraftFromDom();
    if (safeStorageGet(INTERNAL_RELOAD_KEY) === "1") {
      return;
    }
    safeStorageSet(BACKGROUNDED_KEY, "1");
    safeStorageSet(HIDDEN_AT_KEY, String(Date.now()));
  }

  function requestReload(reason, delayMs) {
    if (reloadScheduled) {
      return;
    }
    reloadScheduled = true;
    saveDraftFromDom();
    showResumeOverlay("L'application se remet à jour pour sécuriser votre saisie.", false);
    const payload = JSON.stringify({
      requested_at: new Date().toISOString(),
      reason: reason || "background_resume"
    });
    safeStorageSet(RELOAD_FLAG_KEY, payload);
    safeStorageRemove(BACKGROUNDED_KEY);
    safeStorageSet(INTERNAL_RELOAD_KEY, "1");
    setTimeout(function () {
      getRootWindow().location.reload();
    }, typeof delayMs === "number" ? delayMs : MIN_OVERLAY_MS);
  }

  function needsResumeReload() {
    return safeStorageGet(BACKGROUNDED_KEY) === "1";
  }

  function handleReturnToForeground() {
    const doc = getRootDocument();
    if (doc.hidden) {
      return;
    }
    if (needsResumeReload()) {
      requestReload("background_resume", MIN_OVERLAY_MS);
    }
  }

  function interceptFirstInteraction(event) {
    if (!needsResumeReload()) {
      return;
    }
    const doc = getRootDocument();
    const overlay = doc.getElementById(RESUME_OVERLAY_ID);
    if (overlay && overlay.contains(event.target)) {
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    requestReload("first_interaction_after_background", MIN_OVERLAY_MS);
  }

  try {
    safeStorageRemove(INTERNAL_RELOAD_KEY);

    const doc = getRootDocument();
    doc.addEventListener("input", scheduleDraftSave, true);
    doc.addEventListener("change", scheduleDraftSave, true);

    if (!doc.hidden && needsResumeReload()) {
      requestReload("initial_visible_with_background_flag", MIN_OVERLAY_MS);
    }

    doc.addEventListener("visibilitychange", function () {
      if (doc.hidden) {
        markBackgrounded();
      } else {
        handleReturnToForeground();
      }
    });

    getRootWindow().addEventListener("pagehide", function () {
      markBackgrounded();
    });

    getRootWindow().addEventListener("pageshow", function () {
      handleReturnToForeground();
    });

    getRootWindow().addEventListener("focus", function () {
      handleReturnToForeground();
    });

    doc.addEventListener("pointerdown", interceptFirstInteraction, true);
    doc.addEventListener("touchstart", interceptFirstInteraction, true);
    doc.addEventListener("keydown", interceptFirstInteraction, true);
    doc.addEventListener("focusin", interceptFirstInteraction, true);

    getRootWindow().addEventListener("offline", function () {
      if (needsResumeReload()) {
        showResumeOverlay(
          "La reprise prendra un instant dès que la connexion sera disponible. Votre brouillon reste conservé.",
          true
        );
      }
    });

    getRootWindow().addEventListener("online", function () {
      if (needsResumeReload()) {
        requestReload("online_after_background", MIN_OVERLAY_MS);
      }
    });
  } catch (error) {
    // Browser storage or parent document access can be restricted in rare contexts.
  }
})();
</script>
    """.replace("__RELOAD_FLAG_KEY__", RELOAD_FLAG_KEY).replace("__DRAFT_KEY__", DRAFT_KEY)
    components.html(html, height=0, width=0)
