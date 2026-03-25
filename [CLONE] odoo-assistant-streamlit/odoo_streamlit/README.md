# Odoo Streamlit V2

## Contenu
- `odoo_streamlit/app.py` : interface Streamlit V2
- `.streamlit/secrets.toml.example` : modèle de secrets
- `requirements_v2.txt` : dépendances minimales

## Installation
Depuis la racine de ton projet existant :

```bash
pip install -r requirements.txt
streamlit run odoo_streamlit/app.py
```

## Pré-requis
Le projet existant doit déjà contenir :
- `odoo_import/config.py`
- `odoo_import/commercial_wizard.py`
- `odoo_import/odoo_client.py`

## Secrets Streamlit
Crée ou complète `.streamlit/secrets.toml` à la racine du projet avec :
```toml
ODOO_URL = "https://..."
ODOO_DB = "..."
ODOO_USER = "..."
ODOO_API_KEY = "..."
```
