# Correction UX - reprise visible de la dernière saisie

Cette version corrige l'affichage du bouton de reprise.

## Changements

- Le bloc de reprise n'est plus caché dans un expander fermé pour la dernière saisie envoyée.
- Un bouton visible apparaît au-dessus du formulaire quand une saisie récupérable existe.
- Ajout d'une reprise de secours en session pour la dernière saisie envoyée, même si la lecture localStorage n'est pas encore disponible.
- Le diagnostic technique reste masqué par défaut.

## Comportement attendu

- Après une création confirmée, l'utilisateur voit :
  - Dernière saisie envoyée disponible
  - Reprendre la dernière saisie
  - Masquer cette reprise

- Après un brouillon non envoyé retrouvé dans le navigateur, l'utilisateur voit :
  - Brouillon non envoyé retrouvé sur cet appareil
  - Restaurer le brouillon
  - Supprimer ce brouillon
