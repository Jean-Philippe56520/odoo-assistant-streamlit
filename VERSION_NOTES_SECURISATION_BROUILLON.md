# Version securisation brouillon

Cette version ajoute une couche de securite contre la perte de saisie lors de la creation ou mise a jour de pistes Odoo depuis Streamlit.

## Changements principaux

- Conservation d'un brouillon en session avant previsualisation et avant appel Odoo.
- Suppression du reset automatique lorsque la creation ou la mise a jour Odoo n'est pas confirmee.
- Reset du formulaire uniquement apres confirmation Odoo avec succes.
- Bouton de restauration du dernier brouillon non confirme.
- Spinner pendant la previsualisation et les appels Odoo.
- Journal de diagnostic local de session pour les tests terrain.
- Nettoyage du brouillon apres succes confirme.

## Limite connue

La sauvegarde du brouillon est basee sur la session Streamlit. Elle protege les erreurs d'appel, les warnings Odoo et les reruns internes. Si le navigateur mobile recharge totalement la page ou si Streamlit recrée une session neuve, un stockage navigateur ou serveur sera necessaire pour une protection encore plus forte.

## Test minimal conseille

1. Remplir une piste.
2. Cliquer sur Previsualiser.
3. Creer la piste.
4. Verifier le message vert avec ID Odoo.
5. Simuler une erreur Odoo et verifier que le formulaire n'est pas vide.
