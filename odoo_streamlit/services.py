import streamlit as st

from odoo_import.lead_service import prepare_lead_preview
from odoo_import.odoo_client import find_team_ventes, get_active_sales_users, odoo_connect


@st.cache_resource
def get_odoo():
    uid, models = odoo_connect()
    return uid, models


@st.cache_data(ttl=300)
def get_sales_users():
    uid, models = get_odoo()
    return get_active_sales_users(models, uid)


@st.cache_data(ttl=300)
def get_team_id():
    uid, models = get_odoo()
    return find_team_ventes(models, uid)


def compute_preview(data, seller_name, seller_user_id, actor_user):
    uid, models = get_odoo()
    return prepare_lead_preview(
        uid=uid,
        models=models,
        raw_data=data,
        team_id=get_team_id(),
        seller_user_id=seller_user_id,
        seller_name=seller_name,
        actor_user=actor_user,
        audit_mode="prévisualisation",
    )
