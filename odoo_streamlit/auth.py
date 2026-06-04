import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import streamlit as st
import extra_streamlit_components as stx


COOKIE_MANAGER = stx.CookieManager(key="abm_cookie_manager")

AUTH_SESSION_KEYS = (
    "authenticated",
    "auth_user",
    "cookie_bootstrap_done",
    "auth_cookie_cache",
)


@dataclass(frozen=True)
class AuthConfig:
    username: str
    password: str
    cookie_name: str
    cookie_key: str
    cookie_expiry_days: int

    @property
    def expected_cookie_value(self) -> str:
        return f"{self.username}:{self.cookie_key}"


def load_auth_config() -> AuthConfig:
    auth = st.secrets["auth_simple"]
    return AuthConfig(
        username=auth["username"],
        password=auth["password"],
        cookie_name=auth["cookie_name"],
        cookie_key=auth["cookie_key"],
        cookie_expiry_days=int(auth.get("cookie_expiry_days", 30)),
    )


def init_auth_state():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if "auth_user" not in st.session_state:
        st.session_state["auth_user"] = ""
    if "cookie_bootstrap_done" not in st.session_state:
        st.session_state["cookie_bootstrap_done"] = False


def get_cookie_value(cookie_name: str) -> str:
    """Return a cookie value while calling CookieManager only once per Streamlit run.

    extra-streamlit-components renders a custom component for get_all().
    Calling it multiple times in the same run with the same internal key can trigger
    StreamlitDuplicateElementKey. Caching the result in session_state avoids that.
    """
    if "auth_cookie_cache" not in st.session_state:
        st.session_state["auth_cookie_cache"] = COOKIE_MANAGER.get_all() or {}
    return st.session_state["auth_cookie_cache"].get(cookie_name, "")


def set_auth_cookie(config: AuthConfig):
    COOKIE_MANAGER.set(
        config.cookie_name,
        config.expected_cookie_value,
        expires_at=datetime.now() + timedelta(days=config.cookie_expiry_days),
    )
    st.session_state["auth_cookie_cache"] = {config.cookie_name: config.expected_cookie_value}
    time.sleep(0.5)


def clear_auth_cookie(config: AuthConfig):
    COOKIE_MANAGER.set(
        config.cookie_name,
        "",
        expires_at=datetime.now() - timedelta(days=1),
    )
    st.session_state["auth_cookie_cache"] = {}
    time.sleep(0.5)


def authenticate_session(username: str):
    st.session_state["authenticated"] = True
    st.session_state["auth_user"] = username


def clear_session_keys(keys):
    for key in keys:
        if key in st.session_state:
            del st.session_state[key]


def reset_auth_state():
    clear_session_keys(AUTH_SESSION_KEYS)


def restore_auth_from_cookie(config: AuthConfig) -> bool:
    existing_cookie = get_cookie_value(config.cookie_name)
    if existing_cookie and existing_cookie == config.expected_cookie_value:
        authenticate_session(config.username)
        return True
    return False


def bootstrap_auth(config: AuthConfig):
    if st.session_state["cookie_bootstrap_done"]:
        return

    time.sleep(0.5)
    restored = restore_auth_from_cookie(config)
    st.session_state["cookie_bootstrap_done"] = True

    if not restored and not st.session_state.get("authenticated"):
        st.rerun()


def render_login_form(config: AuthConfig):
    st.title("Accès privé ABM")
    st.caption("Connexion requise pour accéder à l'application.")

    input_user = st.text_input("Identifiant", key="login_username")
    input_pass = st.text_input("Mot de passe", type="password", key="login_password")
    remember_me = st.checkbox("Rester connecté 30 jours", value=True, key="login_remember_me")

    if st.button("Se connecter", type="primary", key="login_submit"):
        if input_user == config.username and input_pass == config.password:
            authenticate_session(input_user)

            if remember_me:
                set_auth_cookie(config)

            st.rerun()
        else:
            st.error("Identifiants incorrects.")

    st.stop()


def require_simple_auth():
    config = load_auth_config()
    init_auth_state()
    bootstrap_auth(config)

    # Do not call restore_auth_from_cookie() a second time in the same run.
    # CookieManager.get_all() is a Streamlit component and duplicate calls can
    # raise StreamlitDuplicateElementKey. bootstrap_auth() already restored the
    # session if a valid cookie exists.
    if st.session_state.get("authenticated"):
        return

    render_login_form(config)


def render_logout(app_state_keys):
    config = load_auth_config()

    with st.sidebar:
        st.markdown("### Session")
        st.write(f"Connecté : {st.session_state.get('auth_user', '-')}")

        if st.button("Se déconnecter", use_container_width=True, key="logout_button"):
            clear_auth_cookie(config)
            reset_auth_state()
            clear_session_keys(app_state_keys)
            st.rerun()