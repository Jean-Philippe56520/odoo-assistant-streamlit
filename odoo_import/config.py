from pathlib import Path
import os

from dotenv import load_dotenv

# ============================================================
# CHARGEMENT ENVIRONNEMENT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ============================================================
# CHEMINS
# ============================================================

FILES_DIR = BASE_DIR / "fichiers"
ALLOWED_EXT = (".csv", ".xlsx", ".xls")

# ============================================================
# ODOO CONFIG
# ============================================================

try:
    import streamlit as st
except Exception:
    st = None


def _read_secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    if st is not None:
        try:
            return str(st.secrets.get(name, "")).strip()
        except Exception:
            return ""
    return ""


ODOO_URL = _read_secret("ODOO_URL")
ODOO_DB = _read_secret("ODOO_DB")
ODOO_USER = _read_secret("ODOO_USER")
ODOO_API_KEY = _read_secret("ODOO_API_KEY")

LEAD_MODEL = "crm.lead"
TAG_MODEL = "crm.tag"
TEAM_MODEL = "crm.team"
USER_MODEL = "res.users"

# ============================================================
# MODE IMPORT
# ============================================================

FORCE_CREATE = os.getenv("FORCE_CREATE", "true").strip().lower() in ("1", "true", "yes", "y", "on")

# ============================================================
# VALIDATION DIFFÉRÉE
# ============================================================

def get_missing_odoo_settings() -> list[str]:
    """
    Retourne la liste des paramètres Odoo manquants.

    Important :
    - ne lève pas d'exception à l'import du module
    - permet à Streamlit de démarrer proprement
    - la validation se fait ensuite au moment de la connexion réelle à Odoo
    """
    missing = []

    if not ODOO_URL:
        missing.append("ODOO_URL")
    if not ODOO_DB:
        missing.append("ODOO_DB")
    if not ODOO_USER:
        missing.append("ODOO_USER")
    if not ODOO_API_KEY:
        missing.append("ODOO_API_KEY")

    return missing
