"""Affichage de la carte commerciale My Maps sans exposer son lien dans GitHub."""

import os
import re

import streamlit as st


MAP_SECRET_KEY = "ABM_MYMAPS_ID"
# Valeur provisoire pour la démonstration ; remplacer par le secret déployé ensuite.
DEMO_MAP_ID = "1K5FS9IMYVHoOQLTZYoUzZAomcSOS-WE"
MAP_TITLE = "Secteurs ABM V1 (pilote)"
MAP_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,128}$")


def get_map_id():
    """Lire un identifiant My Maps de la configuration privée de l'application."""
    try:
        configured_id = st.secrets.get(MAP_SECRET_KEY, "")
    except (FileNotFoundError, RuntimeError):
        configured_id = ""
    raw_id = configured_id or os.environ.get(MAP_SECRET_KEY, "") or DEMO_MAP_ID
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


def require_temporary_map_password():
    """Verrou temporaire pour la présentation du pôle business."""
    if st.session_state.get("abm_map_unlocked"):
        return

    st.subheader("Accès de présentation")
    st.info("Cette carte est réservée à la préparation de la présentation du pôle business.")
    with st.form("abm_map_password_form"):
        password = st.text_input("Mot de passe temporaire", type="password")
        submitted = st.form_submit_button("Accéder à la carte")
    if submitted:
        if password == "Test":
            st.session_state["abm_map_unlocked"] = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    st.stop()


@st.cache_data(ttl=900, show_spinner=False, max_entries=3)
def _cached_commercial_map(map_id):
    from odoo_streamlit.mymaps_data import load_map
    return load_map(map_id)


def render_commercial_map():
    require_temporary_map_password()
    st.title("Carte commerciale ABM")
    st.caption("Carte originale Google My Maps et recherche géographique.")

    map_id = get_map_id()
    if not map_id:
        st.warning("Carte non configurée. Contactez l'administrateur ABM.")
        return

    embed_url, viewer_url = build_map_urls(map_id)

    with st.form("abm_location_search", clear_on_submit=False):
        query = st.text_input(
            "Localiser un code postal, une commune ou une adresse",
            placeholder="Ex. : 35000, Vannes, 10 rue de la Paix Rennes",
            key="abm_map_search_query",
        )
        submitted = st.form_submit_button("Rechercher", type="primary")

    if submitted:
        if len(query.strip()) < 2:
            st.info("Saisissez un code postal, une commune ou une adresse.")
            st.session_state["abm_map_search_results"] = []
        else:
            from odoo_streamlit.map_geocoding import GeocodingError, search_location
            try:
                st.session_state["abm_map_search_results"] = search_location(query)
                if not st.session_state["abm_map_search_results"]:
                    st.info("Aucun lieu trouvé. Précisez la commune ou l'adresse.")
            except GeocodingError as exc:
                st.session_state["abm_map_search_results"] = []
                st.warning(str(exc))

    results = st.session_state.get("abm_map_search_results") or []
    if results:
        options = range(len(results))
        choice = st.selectbox(
            "Choisir le lieu",
            options=options,
            format_func=lambda i: results[i]["label"],
            key="abm_location_result",
        )
        point = results[choice]
        if st.button("Centrer la carte ici", key="abm_center_map", type="primary"):
            st.session_state["abm_map_selected_point"] = point

    mode = st.radio(
        "Affichage",
        ("Google My Maps (icônes originales)", "Calques interactifs ABM"),
        horizontal=True,
        key="abm_map_display_mode",
    )
    if mode.startswith("Google"):
        selected = st.session_state.get("abm_map_selected_point")
        url = embed_url
        if selected:
            # Paramètres de centrage utilisés par la visionneuse My Maps.
            from urllib.parse import urlencode
            url += "&" + urlencode({
                "ll": f'{selected["lat"]:.6f},{selected["lon"]:.6f}',
                "z": selected["zoom"],
            })
            st.caption(f'Lieu recherché : {selected["label"]}. Le recentrage dépend des paramètres acceptés par Google.')
        st.iframe(url, height=740, width="stretch")
        st.caption("Les symboles, styles et calques sont ceux de la carte Google originale. Certaines commandes Google sont masquées sur téléphone.")
    else:
        try:
            with st.spinner("Chargement des calques..."):
                map_data = _cached_commercial_map(map_id)
            from odoo_streamlit.mymaps_viewer import build_viewer_html
            import streamlit.components.v1 as components
            selected = st.session_state.get("abm_map_selected_point")
            components.html(build_viewer_html(map_data, selected), height=740, scrolling=False)
            st.caption("Vue adaptée au mobile : sélection des calques. Les symboles peuvent différer de Google My Maps.")
        except Exception:
            st.warning("Le lecteur de calques n'est pas disponible actuellement.")
            st.iframe(embed_url, height=740, width="stretch")

    st.link_button("Ouvrir la carte Google My Maps complète", viewer_url)
