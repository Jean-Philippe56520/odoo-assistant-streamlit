import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from streamlit_js_eval import streamlit_js_eval

# Durable browser data.
# Keep the draft in localStorage so it survives page reloads and browser restarts.
DRAFT_KEY = "abm_odoo_lead_draft_v1"
DRAFT_TTL_HOURS = 24
LAST_SELLER_KEY = "abm_odoo_last_seller_name_v1"

# Temporary browser data.
# Keep technical resume/session markers in sessionStorage so a clean new browser
# session does not inherit stale "backgrounded" flags from an older visit.
APP_STATE_KEY = "abm_odoo_app_state_v1"
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
    "create_activity",
    "activity_type",
    "activity_summary",
    "activity_date_mode",
    "activity_custom_date",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _storage_js(storage_area: str) -> str:
    return "sessionStorage" if storage_area == "session" else "localStorage"


def _read_raw_storage(key_name: str, component_key: str, storage_area: str = "local"):
    storage = _storage_js(storage_area)
    expression = f"{storage}.getItem({_json(key_name)})"
    return streamlit_js_eval(
        js_expressions=expression,
        key=component_key,
        want_output=True,
    )


def read_json_storage(key_name: str, component_key: str, default=None, storage_area: str = "local"):
    raw = _read_raw_storage(key_name, component_key, storage_area=storage_area)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def write_json_storage(key_name: str, value: dict, component_key: str, storage_area: str = "local"):
    storage = _storage_js(storage_area)
    expression = f"{storage}.setItem({_json(key_name)}, {_json(_json(value))})"
    streamlit_js_eval(
        js_expressions=expression,
        key=component_key,
        want_output=False,
    )


def remove_storage(key_name: str, component_key: str, storage_area: str = "local"):
    storage = _storage_js(storage_area)
    expression = f"{storage}.removeItem({_json(key_name)})"
    streamlit_js_eval(
        js_expressions=expression,
        key=component_key,
        want_output=False,
    )


def reload_app(component_key: str = "reload_app"):
    payload = {"requested_at": now_iso(), "reason": "manual_streamlit_reload"}
    expression = (
        f"sessionStorage.setItem({_json(RELOAD_FLAG_KEY)}, {_json(_json(payload))});"
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
        storage_area="session",
    )
    remove_storage(RELOAD_FLAG_KEY, component_key=f"{component_key}_clear_reload", storage_area="session")


def _parse_iso_datetime(value: str | None):
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def is_draft_expired(draft: dict | None) -> bool:
    if not draft:
        return False
    saved_at = _parse_iso_datetime(str(draft.get("saved_at") or ""))
    if not saved_at:
        return False
    return datetime.now(timezone.utc) - saved_at > timedelta(hours=DRAFT_TTL_HOURS)


def get_browser_snapshot(current_session_id: str) -> dict:
    app_state = read_json_storage(
        APP_STATE_KEY,
        "read_browser_app_state",
        default={},
        storage_area="session",
    ) or {}
    draft = read_json_storage(
        DRAFT_KEY,
        "read_browser_draft",
        default={},
        storage_area="local",
    ) or {}
    reload_flag = read_json_storage(
        RELOAD_FLAG_KEY,
        "read_browser_reload_flag",
        default={},
        storage_area="session",
    ) or {}
    last_seller_name = _read_raw_storage(
        LAST_SELLER_KEY,
        "read_last_seller_name",
        storage_area="local",
    )
    last_seller_name = str(last_seller_name or "").strip()

    draft_expired = is_draft_expired(draft)
    if draft_expired:
        remove_storage(DRAFT_KEY, component_key="clear_expired_browser_draft", storage_area="local")
        draft = {}

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
        "draft_expired": draft_expired,
        "reload_requested": reload_requested,
        "reload_flag": reload_flag,
        "last_seller_name": last_seller_name,
    }


def has_meaningful_draft(data: dict | None) -> bool:
    if not data:
        return False
    for key in FORM_FIELD_KEYS + ("seller_name",):
        if str(data.get(key) or "").strip():
            return True
    return False


def build_draft_from_session(seller_name: str | None = None) -> dict:
    data = {}
    for key in FORM_FIELD_KEYS:
        value = st.session_state.get(key)
        if key == "create_activity":
            data[key] = bool(value)
        elif key == "activity_custom_date" and isinstance(value, date):
            data[key] = value.isoformat()
        else:
            data[key] = str(value or "")
    if seller_name:
        data["seller_name"] = seller_name
    elif st.session_state.get("seller_name"):
        data["seller_name"] = st.session_state.get("seller_name")
    data["saved_at"] = now_iso()
    data["source"] = "streamlit_session"
    return data


def save_local_draft(data: dict, component_key: str = "save_local_draft"):
    if has_meaningful_draft(data):
        payload = dict(data)
        payload["saved_at"] = now_iso()
        payload.setdefault("source", "streamlit_session")
        write_json_storage(DRAFT_KEY, payload, component_key=component_key, storage_area="local")
    else:
        remove_storage(DRAFT_KEY, component_key=f"{component_key}_clear", storage_area="local")


def save_last_seller_name(seller_name: str | None, component_key: str = "save_last_seller_name"):
    """Persist the seller used by the last successful Odoo write.

    This is intentionally independent from the prospect draft. It is a user
    preference and must survive reloads, browser restarts and form resets until
    another successful Odoo write uses a different seller.
    """
    seller = str(seller_name or "").strip()
    if not seller:
        return

    # Use a tiny HTML component instead of a read/write Streamlit component.
    # We do not need a returned value; we only need the browser to commit the
    # localStorage write reliably during this render.
    html = f"""
    <script>
    (function () {{
      const key = {_json(LAST_SELLER_KEY)};
      const value = {_json(seller)};
      try {{
        if (window.parent && window.parent.localStorage) {{
          window.parent.localStorage.setItem(key, value);
        }} else {{
          localStorage.setItem(key, value);
        }}
      }} catch (error) {{
        try {{ localStorage.setItem(key, value); }} catch (_) {{}}
      }}
    }})();
    </script>
    """
    components.html(html, height=0, width=0)


def clear_last_seller_name(component_key: str = "clear_last_seller_name"):
    remove_storage(LAST_SELLER_KEY, component_key=component_key, storage_area="local")


def clear_local_draft(component_key: str = "clear_local_draft"):
    # Also write a short suppression marker so the browser-side DOM watcher does
    # not immediately recreate the just-deleted draft from an old DOM during a
    # Streamlit rerun after successful Odoo creation/update.
    expression = (
        f"localStorage.removeItem({_json(DRAFT_KEY)});"
        "localStorage.setItem('abm_odoo_draft_suppressed_until_v1', String(Date.now() + 5000));"
    )
    streamlit_js_eval(
        js_expressions=expression,
        key=component_key,
        want_output=False,
    )


def _coerce_draft_date(value):
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def restore_draft_to_session_state(draft: dict, seller_names: list[str] | None = None):
    form_data = {}
    for key in FORM_FIELD_KEYS:
        if key == "create_activity":
            value = bool(draft.get(key, False))
        elif key == "activity_custom_date":
            value = _coerce_draft_date(draft.get(key))
        else:
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
    st.session_state["suppress_draft_prompt"] = True


def render_connection_watchdog():
    """Inject browser-side safeguards for mobile resume and local draft capture.

    Rules:
    - localStorage is only used for the durable draft;
    - sessionStorage is used for temporary resume/reload flags;
    - pagehide saves the draft but no longer marks the app as backgrounded;
    - opening the app normally must not trigger the resume overlay;
    - returning from background shows a neutral overlay and reloads after a
      short visible delay;
    - the first user interaction after background is intercepted as a safety net.
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
  const LAST_SELLER_KEY = "__LAST_SELLER_KEY__";
  const DRAFT_SUPPRESSED_UNTIL_KEY = "abm_odoo_draft_suppressed_until_v1";
  const MIN_OVERLAY_MS = 700;
  const STUCK_OVERLAY_MS = 5000;
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

  function localStore() {
    return getRootWindow().localStorage || window.localStorage;
  }

  function sessionStore() {
    return getRootWindow().sessionStorage || window.sessionStorage;
  }

  function localGet(key) {
    try { return localStore().getItem(key); } catch (error) { return null; }
  }

  function localSet(key, value) {
    try { localStore().setItem(key, value); } catch (error) {}
  }

  function localRemove(key) {
    try { localStore().removeItem(key); } catch (error) {}
  }

  function sessionGet(key) {
    try { return sessionStore().getItem(key); } catch (error) { return null; }
  }

  function sessionSet(key, value) {
    try { sessionStore().setItem(key, value); } catch (error) {}
  }

  function sessionRemove(key) {
    try { sessionStore().removeItem(key); } catch (error) {}
  }

  function draftSaveSuppressed() {
    const until = Number(localGet(DRAFT_SUPPRESSED_UNTIL_KEY) || "0");
    if (!until) { return false; }
    if (Date.now() > until) {
      localRemove(DRAFT_SUPPRESSED_UNTIL_KEY);
      return false;
    }
    return true;
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
          <div id="abm-resume-spinner" style="display:flex;align-items:center;gap:12px;margin:8px 0 16px 0;color:#475569">
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
            <button id="abm-resume-continue-button" style="width:100%;border:1px solid #cbd5e1;border-radius:12px;background:white;color:#334155;font-size:16px;font-weight:650;padding:12px 16px;cursor:pointer">
              Continuer
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
      const continueButton = doc.getElementById("abm-resume-continue-button");
      if (continueButton) {
        continueButton.addEventListener("click", function () {
          sessionRemove(BACKGROUNDED_KEY);
          sessionRemove(HIDDEN_AT_KEY);
          sessionRemove(INTERNAL_RELOAD_KEY);
          reloadScheduled = false;
          overlay.style.display = "none";
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
    const spinner = doc.getElementById("abm-resume-spinner");
    if (body) {
      body.textContent = message || "L'application se remet à jour pour sécuriser votre saisie.";
    }
    if (actions) {
      actions.style.display = showManualAction ? "flex" : "none";
    }
    if (spinner) {
      spinner.style.display = showManualAction ? "none" : "flex";
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
      ["free_comment", "textarea[aria-label=\"Commentaire libre\"]"],
      ["activity_summary", "input[aria-label=\"Résumé\"]"],
      ["activity_custom_date", "input[aria-label=\"Choisir une date\"]"]
    ];
  }

  function hasMeaningfulDraft(data) {
    const keys = ["partner_name", "contact_name", "phone", "mobile", "email_from", "street", "street2", "zip", "city", "current_equipment", "free_comment", "seller_name", "activity_summary"];
    return keys.some(function (key) { return String((data && data[key]) || "").trim().length > 0; });
  }

  function readExistingDraft() {
    const raw = localGet(DRAFT_KEY);
    if (!raw) { return {}; }
    try { return JSON.parse(raw) || {}; } catch (error) { return {}; }
  }

  function findCheckboxByLabel(labelText) {
    const doc = getRootDocument();
    const labels = Array.from(doc.querySelectorAll('label'));
    const target = String(labelText || '').trim().toLowerCase();
    for (const label of labels) {
      const text = String(label.textContent || '').trim().toLowerCase();
      if (!text.includes(target)) { continue; }
      const input = label.querySelector('input[type="checkbox"]') || (label.getAttribute('for') ? doc.getElementById(label.getAttribute('for')) : null);
      if (input && input.type === 'checkbox') { return input; }
      const container = label.closest('[data-testid="stCheckbox"], div');
      if (container) {
        const nested = container.querySelector('input[type="checkbox"]');
        if (nested) { return nested; }
      }
    }
    return null;
  }

  function findSelectedValueByLabel(labelText) {
    const doc = getRootDocument();
    const labels = Array.from(doc.querySelectorAll('label, [aria-label]'));
    const target = String(labelText || '').trim().toLowerCase();
    for (const label of labels) {
      const text = String(label.textContent || label.getAttribute('aria-label') || '').trim().toLowerCase();
      if (text !== target) { continue; }
      const container = label.closest('[data-testid="stSelectbox"], div');
      if (!container) { continue; }
      const selected = container.querySelector('[data-baseweb="select"] [title], [data-baseweb="select"] div[role="button"], [data-baseweb="select"]');
      const value = String((selected && (selected.getAttribute('title') || selected.textContent)) || '').trim();
      if (value && value.toLowerCase() !== target) { return value; }
    }
    return '';
  }

  function findSelectedRadioValueByGroupLabel(labelText) {
    const doc = getRootDocument();
    const radios = Array.from(doc.querySelectorAll('input[type="radio"]'));
    for (const radio of radios) {
      if (!radio.checked) { continue; }
      const label = radio.closest('label');
      const value = String((label && label.textContent) || radio.value || '').trim();
      if (value) { return value; }
    }
    return '';
  }

  function findSellerValueFromDom() {
    const doc = getRootDocument();
    const labels = Array.from(doc.querySelectorAll('label, [aria-label]'));
    for (const label of labels) {
      const text = String(label.textContent || label.getAttribute('aria-label') || '').trim().toLowerCase();
      if (text !== 'commercial') { continue; }
      const container = label.closest('[data-testid="stSelectbox"], div');
      if (!container) { continue; }
      const selected = container.querySelector('[data-baseweb="select"] [title], [data-baseweb="select"] div[role="button"], [data-baseweb="select"]');
      const value = String((selected && (selected.getAttribute('title') || selected.textContent)) || '').trim();
      if (value && value.toLowerCase() !== 'commercial') { return value; }
    }
    return '';
  }

  function saveLastSellerFromDom() {
    // Intentionally empty. The durable default commercial is updated only
    // after a successful Odoo creation/update, from Streamlit, not whenever
    // the selectbox changes. This prevents accidental overwrite by "A imputer"
    // on app startup or by a temporary selection.
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
    const seller = findSellerValueFromDom();
    if (seller) {
      draft.seller_name = seller;
    }
    const activityCheckbox = findCheckboxByLabel("Prévoir une activité de relance");
    if (activityCheckbox) {
      draft.create_activity = Boolean(activityCheckbox.checked);
    }
    const activityType = findSelectedValueByLabel("Type d'activité");
    if (activityType) { draft.activity_type = activityType; }
    const activityDateMode = findSelectedRadioValueByGroupLabel("Date de relance");
    if (activityDateMode) { draft.activity_date_mode = activityDateMode; }
    draft.saved_at = new Date().toISOString();
    draft.source = "browser_dom";
    return draft;
  }

  function saveDraftFromDom() {
    if (draftSaveSuppressed()) {
      return;
    }
    const draft = collectDraftFromDom();
    if (hasMeaningfulDraft(draft)) {
      localSet(DRAFT_KEY, JSON.stringify(draft));
    } else {
      localRemove(DRAFT_KEY);
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
    if (sessionGet(INTERNAL_RELOAD_KEY) === "1") {
      return;
    }
    sessionSet(BACKGROUNDED_KEY, "1");
    sessionSet(HIDDEN_AT_KEY, String(Date.now()));
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
    sessionSet(RELOAD_FLAG_KEY, payload);
    sessionRemove(BACKGROUNDED_KEY);
    sessionRemove(HIDDEN_AT_KEY);
    sessionSet(INTERNAL_RELOAD_KEY, "1");

    setTimeout(function () {
      const overlay = getRootDocument().getElementById(RESUME_OVERLAY_ID);
      if (overlay && reloadScheduled) {
        showResumeOverlay(
          "La préparation prend plus de temps que prévu. Votre brouillon reste conservé.",
          true
        );
      }
    }, STUCK_OVERLAY_MS);

    setTimeout(function () {
      try {
        getRootWindow().location.reload();
      } catch (error) {
        showResumeOverlay(
          "La préparation prend plus de temps que prévu. Votre brouillon reste conservé.",
          true
        );
      }
    }, typeof delayMs === "number" ? delayMs : MIN_OVERLAY_MS);
  }

  function needsResumeReload() {
    return sessionGet(BACKGROUNDED_KEY) === "1";
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
    const doc = getRootDocument();

    // Clean the internal reload marker shortly after the new page has had time
    // to settle. Do not remove it synchronously; pagehide/visibilitychange can
    // still fire during reload on some mobile browsers.
    setTimeout(function () { sessionRemove(INTERNAL_RELOAD_KEY); }, 1500);

    doc.addEventListener("input", scheduleDraftSave, true);
    doc.addEventListener("change", function () {
      scheduleDraftSave();
    }, true);

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

    // pagehide is not proof that the user reduced the app; it also occurs on
    // normal reload/navigation. Use it only as a last chance to save the draft.
    getRootWindow().addEventListener("pagehide", function () {
      saveDraftFromDom();
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
    """.replace("__RELOAD_FLAG_KEY__", RELOAD_FLAG_KEY).replace("__DRAFT_KEY__", DRAFT_KEY).replace("__LAST_SELLER_KEY__", LAST_SELLER_KEY)
    components.html(html, height=0, width=0)
