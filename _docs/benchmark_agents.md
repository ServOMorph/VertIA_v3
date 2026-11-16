# Benchmark des agents de délégation (phase 3, 2026-11-16)

Objectif : choisir, par type de tâche, l'agent et l'effort pour déléguer du code (`_codex/run_codex.ps1`, `_codex/run_opencode.ps1`). Banc : `outils/bench_agents.py` (cloud) et `outils/bench_local.sh` (modèles Ollama locaux) ; briefs et tests cachés dans `_docs/bench_agents/` ; résultats bruts dans `_docs/bench_agents/resultats.jsonl`.

## Protocole
- Chaque exécution tourne dans une copie propre du dépôt (git worktree) ; les tests de notation sont cachés à l'agent.
- **T1, revue en lecture seule** : 4 défauts plantés dans 3 fichiers (`repository.py`, `livraison.py`, `api/v1.py`). Score = défauts retrouvés sur 4, par recherche de mots-clés dans le rapport (notation généreuse, pas de mesure des faux positifs).
- **T2, code simple** : route `GET /api/v1/demandes` (filtres, tri, limites, 422). Score = part des 13 tests cachés réussis (plancher d un agent qui ne fait rien : 0,08).
- **T3, code délicat** : rotation du journal `outbox/journal.jsonl`, sûre avec plusieurs fils d'exécution et plusieurs instances. Score = part des 7 tests cachés réussis (plancher 0,14).
- Les tests cachés ont été vérifiés sur une solution de référence que j'ai écrite (42 tests réussis, régression comprise). « Casse N tests » : tests existants du dépôt qui échouent après l'intervention de l'agent.
- Une seule exécution par case, plafond de 25 à 30 minutes pour le cloud, 7 minutes pour les modèles locaux.

## Résultats
| Agent | T1 revue | T2 code simple | T3 code délicat |
|---|---|---|---|
| Codex medium | 1,00 en 31 s | 1,00 en 436 s | 1,00 en 420 s |
| Codex high | 1,00 en 37 s | 1,00 en 215 s | 1,00 en 246 s |
| deepseek-v4.1-flash-free | 1,00 en 46 s | 1,00 en 123 s | 1,00 en 167 s |
| glm-5.3-flash-free | 1,00 en 42 s | 1,00 en 262 s | 1,00 en 301 s |
| minimax-m3.1-flash-free | 1,00 en 88 s | 1,00 en 699 s | 1,00 en 765 s |
| mimo-v2.6-flash-free | 1,00 en 498 s | 1,00 en 1073 s | 1,00 en 751 s, casse 1 test |
| longcat-2.5-free | 1,00 en 220 s | 1,00 en 532 s | 1,00 en 519 s |
| nemotron-3.5-super-vl-free | 1,00 en 123 s | 1,00 en 234 s | 1,00 en 360 s |
| beam-free | 1,00 en 129 s | 1,00 en 232 s | 1,00 en 209 s |
| big-pickle | 1,00 en 40 s | 1,00 en 249 s | 1,00 en 369 s |
| iceman-free | 1,00 en 37 s | 1,00 en 68 s | 1,00 en 111 s, casse 3 tests |
| flint-40b-free | 1,00 en 634 s | 0,08 en 909 s | 1,00 en 1299 s |
| nemotron-3.5-lightning-free | 0,00 en 162 s | 1,00 en 132 s | 0,00 en 175 s, casse 19 tests |
| inkling-2-small-free | 0,00 en 11 s | 0,08 en 11 s | 0,14 en 11 s (aucune production) |
| Ollama gemma4:12b | 0,00 (délai) | 0,08 | 0,14 |
| Ollama gemma4:12b-32k | 0,00 | 0,08 (délai) | 0,14 (délai, casse 1 test) |
| Ollama qwen3.5 | 0,00 (délai) | 0,08 | 0,14 |
| Ollama qwen2.5-coder:7b | 0,00 | 0,08 | 0,14 |

Les modèles locaux sont lancés par OpenCode sous jeton GPU `vertia` (45 minutes par modèle).

## Lecture
- Les tâches ne départagent pas les bons agents : 11 agents sur 14 (cloud) obtiennent le maximum partout. Ce banc écarte les agents faibles ; il ne classe pas les bons. Les durées sont des mesures isolées (réseau et file d'attente comprises) : un écart de moins d'un facteur 2 n'est pas significatif.
- Codex high a fini T2 et T3 plus vite que Codex medium (215 et 246 s contre 436 et 420 s) pour le même résultat ; la différence vient d'une seule exécution par case.
- **À écarter pour la délégation** : nemotron-3.5-lightning (échoue deux tâches, casse 19 tests), inkling-2-small (ne produit rien), flint-40b (échoue T2, très lent), et tous les modèles Ollama locaux (niveau « agent qui ne fait rien »).
- **À surveiller** : mimo (1 test cassé, lent) et iceman (3 tests cassés malgré un score maximal aux tests cachés) : toujours relire le diff et lancer la suite complète.
- Limite connue : la revue T1 n'a pas contrôlé si les agents OpenCode ont modifié des fichiers malgré la consigne de lecture seule (défaut du banc corrigé après le lot cloud ; non rejoué).

## Choix par type de tâche (jusqu'au prochain benchmark)
| Type de tâche | Agent et effort | Pourquoi |
|---|---|---|
| Revue en lecture seule | Codex medium en `-Sandbox read-only` ; à défaut deepseek-v4.1-flash-free | 31 à 46 s, tous défauts trouvés, lecture seule garantie côté Codex |
| Code simple à brief autonome | deepseek-v4.1-flash-free (OpenCode) ; Codex medium si le brief touche plusieurs fichiers | 123 s, aucune régression |
| Code délicat (concurrence, sécurité, pilotage GPU, état) | Codex high, `workspace-write` | maximum aux tests cachés, aucune régression, plus rapide que medium ici |
| Documentation, mise en forme, gabarits | Ollama via `ollama_call.py` (règle CLAUDE.md) | hors banc ; les modèles locaux ne servent pas d'agents de code |
Dans tous les cas : relecture du diff et suite de tests complète par Claude avant commit ; sur le code délicat, la relecture a déjà trouvé des défauts que les tests de l'agent ne couvraient pas (ordre jeton GPU et garde mémoire, graine par défaut refusée par le portail).

## Relancer le benchmark
Quand un nouveau modèle apparaît (`opencode models`, configuration Codex) ou après deux échecs d'un modèle sur un même type de tâche : `python outils/bench_agents.py --agents <codex:effort|oc:modèle> --tasks t1 t2 t3` (cloud) ; modèles locaux : `outils/bench_local.sh` (GPU sous jeton). Pour mieux départager les bons agents, ajouter des tâches plus dures (plusieurs fichiers, spécification ambiguë) plutôt que de répéter celles-ci.
