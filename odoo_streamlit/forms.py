import streamlit as st

from odoo_import.lead_service import validate_lead_data


def validate_form(raw_data):
    result = validate_lead_data(raw_data)
    return result.errors, result.cleaned_data


def render_lead_form(seller_names):
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
            value=st.session_state["form_data"]["partner_name"],
            key="partner_name",
        )
        contact_name = st.text_input(
            "Nom du contact",
            value=st.session_state["form_data"]["contact_name"],
            key="contact_name",
        )
        phone_raw = st.text_input(
            "Téléphone",
            value=st.session_state["form_data"]["phone"],
            key="phone",
        )
        mobile_raw = st.text_input(
            "Mobile",
            value=st.session_state["form_data"]["mobile"],
            key="mobile",
        )
        email_raw = st.text_input(
            "Email",
            value=st.session_state["form_data"]["email_from"],
            key="email_from",
        )

        st.subheader("Adresse")
        street = st.text_input(
            "Adresse",
            value=st.session_state["form_data"]["street"],
            key="street",
        )
        street2 = st.text_input(
            "Complément d'adresse",
            value=st.session_state["form_data"]["street2"],
            key="street2",
        )
        zip_code = st.text_input(
            "Code postal",
            value=st.session_state["form_data"]["zip"],
            key="zip",
        )
        city = st.text_input(
            "Ville",
            value=st.session_state["form_data"]["city"],
            key="city",
        )

        st.subheader("Notes")
        current_equipment = st.text_area(
            "Équipement actuel",
            value=st.session_state["form_data"]["current_equipment"],
            key="current_equipment",
        )
        free_comment = st.text_area(
            "Commentaire libre",
            value=st.session_state["form_data"]["free_comment"],
            key="free_comment",
        )

        submitted = st.form_submit_button("Prévisualiser")

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
    }
    return submitted, seller_name, raw_data


def _get_seller_index(seller_names):
    seller_name = st.session_state.get("seller_name")
    if seller_name in seller_names:
        return seller_names.index(seller_name)
    return 0
