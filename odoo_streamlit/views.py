import streamlit as st

from odoo_import.lead_service import PROSPECTION_TAG, build_title
from odoo_streamlit.constants import APP_CAPTION, APP_TITLE


def render_page_header():
    st.title(APP_TITLE)
    st.caption(APP_CAPTION)


def render_banner():
    banner = st.session_state.get("result_banner")
    if not banner:
        return

    if banner["status"] == "success":
        st.success(banner["message"], icon="✅")
    elif banner["status"] == "warning":
        st.warning(banner["message"], icon="⚠️")
    else:
        st.error(banner["message"], icon="❌")


def show_existing(existing):
    st.markdown("### Lead détecté")
    if not existing:
        st.warning("Impossible de lire le détail du lead détecté.")
        return

    seller = "-"
    user_id = existing.get("user_id")
    if isinstance(user_id, list) and len(user_id) >= 2:
        seller = user_id[1]

    st.write(f"**Titre :** {existing.get('name') or '-'}")
    st.write(f"**Société :** {existing.get('partner_name') or '-'}")
    st.write(f"**Contact :** {existing.get('contact_name') or '-'}")
    st.write(f"**Email :** {existing.get('email_from') or '-'}")
    st.write(f"**Téléphone :** {existing.get('phone') or '-'}")
    st.write(f"**Mobile :** {existing.get('mobile') or '-'}")
    st.write(f"**Vendeur actuel :** {seller}")


def show_preview(preview_vals, raw_data, seller_name):
    st.subheader("Prévisualisation")
    st.write(f"**Compte connecté :** {st.session_state.get('auth_user') or '-'}")
    st.write(f"**Commercial :** {seller_name}")
    st.write(f"**Titre :** {build_title(raw_data)}")
    st.write(f"**Entreprise :** {raw_data.get('partner_name') or '-'}")
    st.write(f"**Contact :** {raw_data.get('contact_name') or '-'}")
    st.write(f"**Téléphone :** {raw_data.get('phone') or '-'}")
    st.write(f"**Mobile :** {raw_data.get('mobile') or '-'}")
    st.write(f"**Email :** {raw_data.get('email_from') or '-'}")
    st.write(f"**Adresse :** {raw_data.get('street') or '-'}")
    st.write(f"**Complément :** {raw_data.get('street2') or '-'}")
    st.write(f"**Code postal :** {raw_data.get('zip') or '-'}")
    st.write(f"**Ville :** {raw_data.get('city') or '-'}")
    st.write(f"**Équipement actuel :** {raw_data.get('current_equipment') or '-'}")
    st.write(f"**Commentaire libre :** {raw_data.get('free_comment') or '-'}")
    if preview_vals.get("description"):
        with st.expander("Notes générées pour Odoo", expanded=False):
            st.text(preview_vals["description"])
    st.write(f"**Étiquette :** {PROSPECTION_TAG}")
