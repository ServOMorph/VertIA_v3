# Signals — vertia   (MAJ 2026-11-13)

## Actions ouvertes
<!-- ≤ 20 entrées (ligne « Backlog » exclue) ; dette et findings non urgents -> _contexte/backlog.md -->
- [P1|ouvert] Revue du diff et commit des phases 1 à 8 livrées par Codex (non commitées, roadmap_vertia_v1.md encore à l'état Phase 1 EN COURS / 2 à 8 TODO)
  - fait quand: diff relu, suite pytest verte (conftest échoue sur `websockets` absent), commit fait, statuts de roadmap_vertia_v1.md mis à jour.
  - réf: `file_agents.md`, `_docs/revue_phase6.md`, `roadmap_vertia_v1.md`.
- [P1|attente utilisateur] Réponses dans les sessions orchestrées : creation_3d (2 cas véhicule/cartoon, SF3D 0/4 sur uv_unwrapper) ; WorldModel (mesure Matrix-Game bloc entier ou adaptateur pas à pas)
  - fait quand: DECISION reçue de chaque session (VertIA ne relaie pas).
  - réf: `_orchestration/sessions.md`, `_orchestration/protocole.md`.
- [P1|ouvert] Pré-entraînement creation_llm (jeton long, ~14 jours depuis 2026-11-13 12:58) : reprise auto après redémarrage installée mais jamais éprouvée par un vrai redémarrage
  - fait quand: un redémarrage réel a relancé `run_369m.py` (ligne dans `state/reprise.log`) ou l'entraînement est terminé.
  - réf: `_orchestration/reprise_auto.py`, `_orchestration/reprise.json`, tâche Windows `VertIA_reprise_auto`.
- [P2|ouvert] Phase 2 orchestration : calendrier GPU et priorités entre sessions ; audit d'historique des dépôts creation_3d, creation_videos, WorldModel à confirmer
  - fait quand: calendrier écrit dans `roadmap_orchestration.md` et audit `--audit` constaté pour les 3 dépôts.
  - réf: `roadmap_orchestration.md`, `_orchestration/pre_push_check.py`.
- [P2|ouvert] Pause Windows Update posée jusqu'au 2026-12-18 : à renouveler si l'entraînement dure plus longtemps
  - fait quand: pause renouvelée avant le 2026-12-18 ou entraînement terminé.
  - réf: registre `HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings`.
- [P2|attente utilisateur] Test vidéo n°1 Wan 2.2 TI2V-5B (peut être obsolète : file_agents.md indique le modèle validé par l'utilisateur)
  - fait quand: résultats reportés dans `_docs/benchmark_video.md` ou action retirée.
  - réf: `tests_manuels.md`, `_docs/benchmark_video.md`.
- [P2|décision requise] Feu vert pour télécharger les candidats vidéo 2 et 3 (~42 Go sur D:) (peut être obsolète, même motif)
  - fait quand: réponse écrite de l'utilisateur (oui/non) consignée ou action retirée.
  - réf: `_docs/benchmark_video.md` (top 3).

## Contexte chaud
- `D:\ServOMorph\VibeObs\DEPLOYMENTS.md` : ligne VertIA_v3 ajoutée (seule écriture autorisée dans le kit).
- Jeton GPU : creation_llm détient un jeton long interruptible ; état courant par `python _orchestration/vram_lock.py status`.
- Mode `/telephone` installé (copie du kit VibeObs, demande validée par VibeObs puis par l'utilisateur le 2026-11-13).
- Résidus Codex non commités (README, MISE_EN_PROD, tests_manuels, src/, tests/...) volontairement exclus du commit d'orchestration.

## Dernière session (2026-11-13)
# Session du 2026-11-13

## Décisions prises
- Orchestration par VertIA : jeton VRAM par script, protocole v2 source unique, escalades posées par chaque session à l'utilisateur, jamais écrit dans les autres sessions.
- creation_llm : embeddings liés (~336M), plafond 7,5 Go maintenu ; rodage OK, pré-entraînement lancé.
- Reprise automatique après redémarrage : script + tâche planifiée Windows (accord utilisateur). Pause Windows Update appliquée.
- `/telephone` installé après validation VibeObs et accord utilisateur.

## Livrables produits ou modifiés
- `_orchestration/` (vram_lock, pre_push_check, protocole v2, sessions, reprise_auto, reprise.json), `tests/test_orchestration.py`, `tests/test_reprise.py` (31 verts) : commités et poussés (51a3195, c348958).
- `roadmap_orchestration.md`, `.claude/CLAUDE.md`, `.gitignore`, `.claude/commands/telephone.md` : commités au /close.

## Hypothèses validées / invalidées
- VALIDE : nuit improductive causée par un redémarrage Windows Update (journal des événements).
- EN ATTENTE : reprise auto après un vrai redémarrage ; décisions creation_3d et WorldModel.

## Prochaine étape exacte
Revoir et commiter les phases Codex (action P1), puis établir le calendrier GPU (phase 2 orchestration).

## Question bloquante pour la session suivante
Aucune.
