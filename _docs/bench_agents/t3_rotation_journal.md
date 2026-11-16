# Objectif
Ajouter la rotation du journal `outbox/journal.jsonl` dans la classe `Livraison`, sûre en présence de plusieurs fils d'exécution. Critères : `python -m pytest -q tests/test_demandes.py tests/test_api_v1.py` reste vert, la rotation respecte la spécification ci-dessous.

## Fichiers autorisés
- `src/vertia/demandes/livraison.py`
- `tests/test_demandes.py` (ajout de tests seulement)

## Fichiers à lire
- `src/vertia/demandes/livraison.py`, `src/vertia/demandes/service.py` (usage de `Livraison`)
- `tests/test_demandes.py` (style des tests)

## Contexte autonome
- Constructeur : `Livraison(outbox, max_octets=5 * 1024 * 1024, conservation=3)`. Les appels existants `Livraison(outbox)` doivent fonctionner.
- `journal(...)` ajoute une ligne JSON dans `journal.jsonl`. Avant d'écrire une ligne, si le fichier existe, n'est pas vide et que sa taille plus celle de la ligne (en octets UTF-8, saut de ligne compris) dépasse `max_octets`, faire une rotation : supprimer `journal.<conservation>.jsonl` s'il existe, décaler `journal.<i>.jsonl` en `journal.<i+1>.jsonl` pour `i` de `conservation - 1` à 1, renommer `journal.jsonl` en `journal.1.jsonl`, puis écrire la ligne dans un nouveau `journal.jsonl`.
- Une ligne plus grande que `max_octets` est écrite seule dans un fichier neuf, sans boucle de rotation.
- Aucune ligne ne doit être perdue (tant que la conservation la garde), coupée ou mélangée à une autre, même avec plusieurs fils d'exécution écrivant en même temps, y compris via plusieurs instances de `Livraison` qui partagent le même dossier `outbox` dans le même processus. Chaque ligne reste écrite d'un seul bloc.
- Windows : le renommage échoue si un fichier est ouvert ; ne jamais garder le journal ouvert entre deux appels.
- Aucun fichier `journal.<n>.jsonl` avec `n > conservation` ne doit exister.

## Étapes
1. Verrou et rotation dans `Livraison.journal`.
2. Tests dans `tests/test_demandes.py` : rotation simple, ordre des fichiers, concurrence (plusieurs fils), plusieurs instances, ligne géante.

## Vérification
- `python -m py_compile src/vertia/demandes/livraison.py` -> OK
- `python -m pytest -q tests/test_demandes.py tests/test_api_v1.py` -> vert

## Ce qu'il ne faut pas faire
- Aucun changement hors périmètre, commit, push, génération ni redémarrage.
- Ne pas modifier le format des lignes de journal ni les autres méthodes de `Livraison`.

Terminer par le rapport STATUT / FICHIERS / VERIFS / OUVERT, 15 lignes maximum.
