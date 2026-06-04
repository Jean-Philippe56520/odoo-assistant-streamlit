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

## Gestion mobile des sessions et brouillons

L'application sauvegarde automatiquement un brouillon local dans le navigateur de l'appareil (`localStorage`). Ce brouillon survit au rechargement de la page et à une réinitialisation de session Streamlit.

Le brouillon est supprimé uniquement dans les cas suivants :

- création ou mise à jour confirmée dans Odoo ;
- action explicite de l'utilisateur : `Effacer le brouillon` ou `Effacer et recommencer`.

La session Streamlit possède aussi un identifiant technique local. Si le navigateur revient avec un ancien identifiant et que Streamlit en génère un nouveau, l'application affiche un message `Session réinitialisée` et conseille de recharger ou de reprendre le brouillon.

Un watchdog navigateur vérifie périodiquement l'endpoint Streamlit `/_stcore/health`. Si l'application ne répond pas, un bandeau `Connexion interrompue` est affiché côté navigateur.
