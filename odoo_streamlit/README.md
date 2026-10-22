# Odoo Streamlit V2

## Contenu
- `odoo_streamlit/app.py` : interface Streamlit V2
- `odoo_streamlit/campaigns.py` : configuration des campagnes temporaires / salons
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

## Mode temporaire Salon BCT Angers 2026

L'application propose temporairement un mode dédié aux contacts rencontrés au **Salon BCT Angers 2026**.

### Fonctionnement

- le mode normal reste la prospection classique avec l'étiquette Odoo `Prospection` ;
- le mode Salon doit être activé explicitement via le bouton `Activer le mode Salon BCT` ;
- l'interface indique clairement que ce mode est réservé aux commerciaux qui saisissent des contacts du salon ;
- une fois activé, le bandeau `MODE SALON BCT ACTIF` reste visible ;
- le mode reste actif après chaque création afin de permettre plusieurs saisies successives sur le stand ;
- le bouton `Revenir à la prospection normale` permet de quitter immédiatement le mode Salon ;
- après le **12 octobre 2026**, le mode est automatiquement masqué.

### Étiquette Odoo

Une piste créée en mode Salon reçoit l'étiquette dédiée :

`Salon de la Boucherie Angers 2026`

Pour une nouvelle piste, cette étiquette est utilisée à la place de `Prospection`.

Lorsqu'un doublon est détecté et que la piste Odoo existante est mise à jour, l'étiquette Salon est ajoutée sans supprimer les autres étiquettes déjà présentes.

La résolution de l'étiquette utilise le mécanisme existant `find_or_create_tag` : l'application recherche d'abord une étiquette portant exactement ce nom avant d'en créer une.

### Réutilisation pour les prochains salons

La logique de campagne est isolée dans `odoo_streamlit/campaigns.py`.

Pour un prochain événement, il suffit principalement d'adapter :
- le nom de la campagne ;
- le texte du bouton ;
- l'étiquette Odoo ;
- les dates de visibilité.

Le formulaire de prospection et la logique générale de création des pistes Odoo restent communs.

## Gestion mobile des sessions et brouillons

L'application sauvegarde automatiquement un brouillon local dans le navigateur de l'appareil (`localStorage`). Ce brouillon survit au rechargement de la page et à une réinitialisation de session Streamlit.

Le brouillon est supprimé uniquement dans les cas suivants :

- création ou mise à jour confirmée dans Odoo ;
- action explicite de l'utilisateur : `Effacer le brouillon` ou `Effacer et recommencer`.

La session Streamlit possède aussi un identifiant technique local. Si le navigateur revient avec un ancien identifiant et que Streamlit en génère un nouveau, l'application affiche un message `Session réinitialisée` et conseille de recharger ou de reprendre le brouillon.

Un watchdog navigateur vérifie périodiquement l'endpoint Streamlit `/_stcore/health`. Si l'application ne répond pas, un bandeau `Connexion interrompue` est affiché côté navigateur.

## Carte commerciale ABM (présentation provisoire)

- Depuis le menu latéral Streamlit, ouvrir **Carte commerciale**.
- La page demande d'abord l'authentification ABM habituelle, puis un code d'accès de présentation temporaire, conservé pour la session Streamlit.
- Le contenu utilise l'intégration Google My Maps. Les calques se manipulent dans l'interface Google intégrée, si celle-ci les affiche. Un lien **Ouvrir dans Google My Maps** permet d'accéder à l'interface complète.
- La carte pilote **Secteurs ABM V1 (pilote)** est utilisée à titre provisoire, sans intervention dans Odoo.
- Un identifiant différent peut être configuré dans le secret Streamlit `ABM_MYMAPS_ID`. Le code de présentation et l'identifiant pilote doivent être retirés du dépôt après la présentation ; il ne s'agit pas d'une protection des données Google My Maps, qui restent accessibles à toute personne possédant le lien de partage.
- Le formulaire de prospection demeure sur la page principale. Le changement de page est une opération Streamlit : **enregistrer ou terminer une saisie en cours** avant d'ouvrir la carte pour éviter toute perte des champs de formulaire non persistés.
