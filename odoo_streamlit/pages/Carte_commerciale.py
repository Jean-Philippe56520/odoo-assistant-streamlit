import streamlit as st
from odoo_streamlit.auth import require_simple_auth
from odoo_streamlit.map_view import render_commercial_map

st.set_page_config(page_title='Carte commerciale ABM', layout='wide')
require_simple_auth()
render_commercial_map()
