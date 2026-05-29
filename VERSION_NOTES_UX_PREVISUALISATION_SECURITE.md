# Mise à jour UX prévisualisation et sécurité de saisie

Cette version ajuste la couche de sécurité brouillon et l'expérience utilisateur mobile.

## Changements

- Suppression de l'affichage du bloc replié `Brouillon de sécurité disponible` dans l'interface principale.
- Les reprises passent désormais par les blocs visibles :
  - `Brouillon non envoyé retrouvé sur cet appareil`
  - `Dernière saisie envoyée retrouvée sur cet appareil`
  - `Dernière saisie envoyée disponible`
- Le masquage ou la suppression d'une reprise supprime aussi la copie locale concernée pour éviter que le bloc réapparaisse immédiatement.
- La sauvegarde de sécurité est faite dès le clic sur `Prévisualiser`, avant validation et avant appel Odoo.
- Si une erreur bloquante empêche la prévisualisation, la page remonte automatiquement en haut pour montrer le message d'erreur.
- Les warnings simples ne déclenchent pas de remontée automatique.
- Une exception technique pendant `compute_preview` ne casse plus l'app : la saisie est conservée, un message bloquant est affiché et la page remonte en haut.

## Fichiers modifiés

- `odoo_streamlit/app.py`
- `odoo_streamlit/views.py`
- `odoo_streamlit/state.py`
- `odoo_streamlit/constants.py`

## Vérification

Compilation Python validée avec :

```bash
python -m compileall -q odoo_streamlit odoo_import
```
