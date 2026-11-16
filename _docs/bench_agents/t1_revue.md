# Objectif
Revue de code en lecture seule : trois fichiers contiennent des défauts de comportement (erreurs de logique ou écarts avec la spécification). Trouver les défauts réels, sans signaler de faux positifs. Ne modifier AUCUN fichier.

## Fichiers autorisés
- Aucun : revue en lecture seule.

## Fichiers à lire
- `src/vertia/demandes/livraison.py`, `src/vertia/demandes/repository.py`, `src/vertia/api/v1.py`
- `_docs/architecture_portail.md` (sections 5 et 6 : référence de la spécification)

## Contexte autonome
- Ces fichiers implémentent la boucle demande / essai / retour du portail : journal `outbox/journal.jsonl` en ajout seul, livraison des fichiers produits dans `outbox/<session>/<id>/`, table `demandes`, API `/api/v1`.
- Un défaut = un comportement qui contredit la spécification ou l'intention évidente du code (pas un choix de style).
- Au plus 6 défauts. Pour chacun : fichier, ligne, description en moins de 25 mots.

## Étapes
1. Lire les trois fichiers et la spécification.
2. Lister les défauts.

## Vérification
- Aucune commande à lancer. Ne rien modifier.

## Ce qu'il ne faut pas faire
- Aucune modification de fichier, aucun commit.
- Ne pas signaler de simple préférence de style.

Rapport final : OUVERT contient la liste des défauts sous la forme `fichier:ligne description`, séparés par ` ; `. STATUT: OK, FICHIERS: aucun.
Terminer par le rapport STATUT / FICHIERS / VERIFS / OUVERT, 15 lignes maximum.
