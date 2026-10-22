"""Carte commerciale accessible aux utilisateurs ABM connectés."""

import sys
from pathlib import Path

import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parents[2]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from odoo_streamlit.auth import require_simple_auth
from odoo_streamlit.map_view import render_commercial_map

st.set_page_config(page_title="Carte commerciale ABM", layout="wide")
require_simple_auth()
st.page_link("app.py", label="Retour à la saisie des pistes")
render_commercial_map()
