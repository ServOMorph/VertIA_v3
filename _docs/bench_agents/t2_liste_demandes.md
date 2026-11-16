# Objectif
Ajouter la route `GET /api/v1/demandes` qui liste les demandes. Critères : `python -m pytest -q tests/test_api_v1.py tests/test_demandes.py` reste vert, la route respecte la spécification ci-dessous.

## Fichiers autorisés
- `src/vertia/api/v1.py`, `src/vertia/demandes/service.py`, `src/vertia/demandes/repository.py`
- `tests/test_api_v1.py` (ajout de tests seulement)

## Fichiers à lire
- `src/vertia/api/v1.py`, `src/vertia/demandes/service.py`, `src/vertia/demandes/repository.py`, `src/vertia/core/db.py` (tables)
- `tests/test_api_v1.py` (style des tests)

## Contexte autonome
- La route existante `GET /api/v1/demandes/{demande_id}` renvoie une demande. Il manque la liste.
- `GET /api/v1/demandes?session=<nom>&etat=<état>&limite=<n>` renvoie un tableau JSON.
- Chaque élément contient exactement les clés : `id`, `session`, `capacite`, `etat`, `created`.
- Tri : création la plus récente d'abord ; à égalité de date (la précision est la seconde), l'insertion la plus récente d'abord (colonne `rowid` de SQLite).
- `session` (facultatif) filtre sur la session ; `etat` (facultatif) filtre sur l'état et doit être l'un de `attente, actif, livre, valide, a_refaire, echec, plafond, annule`, sinon réponse 422.
- `limite` : entier de 1 à 200, défaut 50 ; hors bornes ou non entier : 422.
- Les paramètres de requête inconnus sont ignorés. La route est protégée comme les autres (localhost).

## Étapes
1. Méthode de liste dans le dépôt de données (requête SQL paramétrée, jamais de concaténation).
2. Méthode de service et route.
3. Tests dans `tests/test_api_v1.py`.

## Vérification
- `python -m py_compile` sur les fichiers modifiés -> OK
- `python -m pytest -q tests/test_api_v1.py tests/test_demandes.py` -> vert

## Ce qu'il ne faut pas faire
- Aucun changement hors périmètre, commit, push, génération ni redémarrage.
- Ne pas modifier le comportement des routes existantes.

Terminer par le rapport STATUT / FICHIERS / VERIFS / OUVERT, 15 lignes maximum.
