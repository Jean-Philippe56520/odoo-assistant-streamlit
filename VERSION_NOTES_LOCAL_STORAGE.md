# Version Niveau 2 - Brouillon navigateur localStorage

Cette version ajoute une sauvegarde navigateur en complément du brouillon de session Streamlit.

## Changements principaux

- Ajout d'une dépendance : `streamlit-local-storage==0.0.25`.
- Nouveau module `odoo_streamlit/local_draft.py`.
- Sauvegarde automatique de la saisie dans le navigateur :
  - au clic sur `Prévisualiser` ;
  - avant création ou mise à jour Odoo.
- Restauration d'un brouillon local après rechargement de la page ou perte de session Streamlit.
- Distinction entre :
  - `Brouillon non envoyé retrouvé` ;
  - `Dernière saisie envoyée retrouvée` avec ID Odoo si disponible.
- Expiration automatique du brouillon local après 7 jours.
- Diagnostic technique masqué par défaut.

## Activation du diagnostic technique

Ajouter dans les secrets Streamlit si nécessaire :

```toml
SHOW_DEBUG = true
```

Sans cette clé, le bloc diagnostic n'est pas affiché aux commerciaux.

## Limites

- Le brouillon local est lié au navigateur et à l'appareil utilisé.
- Si l'utilisateur change de téléphone ou vide le cache navigateur, le brouillon local n'est pas récupérable.
- Cette version ne remplace pas une sauvegarde serveur centralisée.
