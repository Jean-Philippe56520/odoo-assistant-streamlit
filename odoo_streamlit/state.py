import streamlit as st

from odoo_streamlit.constants import DEFAULT_DUPLICATE_ACTION, FORM_FIELD_KEYS


def empty_form_data():
    return {key: "" for key in FORM_FIELD_KEYS}


def init_state():
    defaults = {
        "form_data": empty_form_data(),
        "preview_data": None,
        "preview_vals": None,
        "existing_id": None,
        "existing_data": None,
        "seller_name": None,
        "seller_user_id": None,
        "result_banner": None,
        "pending_form_reset": False,
        "pending_preview_reset": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def apply_pending_resets():
    if st.session_state.get("pending_form_reset"):
        _reset_form_and_preview_state()
        _reset_form_widgets()
        st.session_state["pending_form_reset"] = False
        st.session_state["pending_preview_reset"] = False
    elif st.session_state.get("pending_preview_reset"):
        _reset_preview_state()
        st.session_state["pending_preview_reset"] = False


def request_preview_reset():
    st.session_state["pending_preview_reset"] = True


def request_full_reset(clear_banner=False):
    if clear_banner:
        st.session_state["result_banner"] = None
    st.session_state["pending_form_reset"] = True


def _reset_form_and_preview_state():
    st.session_state["form_data"] = empty_form_data()
    _reset_preview_state()


def _reset_preview_state():
    st.session_state["preview_data"] = None
    st.session_state["preview_vals"] = None
    st.session_state["existing_id"] = None
    st.session_state["existing_data"] = None
    st.session_state["seller_name"] = None
    st.session_state["seller_user_id"] = None
    st.session_state["confirm_existing"] = False
    st.session_state["duplicate_action_radio"] = DEFAULT_DUPLICATE_ACTION


def _reset_form_widgets():
    for key in FORM_FIELD_KEYS:
        st.session_state[key] = ""

    st.session_state["confirm_existing"] = False
    st.session_state["duplicate_action_radio"] = DEFAULT_DUPLICATE_ACTION

    if "seller_selectbox" in st.session_state:
        del st.session_state["seller_selectbox"]
