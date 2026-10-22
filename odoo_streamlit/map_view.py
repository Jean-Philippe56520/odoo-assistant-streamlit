"""Affichage de la carte commerciale My Maps sans exposer son lien dans GitHub."""

import os
import re

import streamlit as st


MAP_SECRET_KEY = "ABM_MYMAPS_ID"
MAP_TITLE = "Secteurs ABM V1 (pilote)"
MAP_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,128}$")


def get_map_id():
    """Lire un identifiant My Maps de la configuration privée de l'application."""
    try:
        configured_id = st.secrets.get(MAP_SECRET_KEY, "")
    except (FileNotFoundError, RuntimeError):
        configured_id = ""
    raw_id = configured_id or os.environ.get(MAP_SECRET_KEY, "")
    map_id = str(raw_id).strip()
    return map_id if MAP_ID_PATTERN.fullmatch(map_id) else None


def build_map_urls(map_id):
    """Construire seulement des URL Google My Maps à partir d'un ID valide."""
    if not MAP_ID_PATTERN.fullmatch(map_id):
        raise ValueError("Identifiant Google My Maps invalide.")
    return (
        f"https://www.google.com/maps/d/embed?mid={map_id}",
        f"https://www.google.com/maps/d/viewer?mid={map_id}",
    )


def render_commercial_map():
    st.title("Carte commerciale ABM")
    st.caption(MAP_TITLE)

    map_id = get_map_id()
    if not map_id:
        st.warning("Carte non configurée. Contactez l'administrateur ABM.")
        return

    embed_url, viewer_url = build_map_urls(map_id)
    st.iframe(embed_url, height=760, width="stretch")
    st.caption("Si la carte ne s'affiche pas ici, ouvrez-la directement dans Google My Maps.")
    st.link_button("Ouvrir dans Google My Maps", viewer_url)
