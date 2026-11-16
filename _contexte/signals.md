# Signals — vertia   (MAJ 2026-11-16)

## Actions ouvertes
<!-- ≤ 20 entrées (ligne « Backlog » exclue) ; dette et findings non urgents -> _contexte/backlog.md -->
- [P1|ouvert] Phase 5 du portail (musique, voix, branchement CreaZik_V3) : à lancer après `/compact`, Opus en pilotage
  - fait quand: phase 5 passée `[EN COURS]` puis `[FAIT]` dans la roadmap.
  - réf: `roadmap_portail.md`.
- [P1|ouvert] Reprise auto de creation_llm après un vrai redémarrage Windows jamais éprouvée (la reprise après pause GPU l'est, contrôle auto par `verif_reprise.py`)
  - fait quand: un redémarrage réel a relancé `run_369m.py` (ligne dans `state/reprise.log`) ou l'entraînement est terminé.
  - réf: `_orchestration/reprise_auto.py`, `_orchestration/verif_reprise.py`.
- [P2|ouvert] Un modèle Ollama `gemma4:e4b` est chargé en « Forever » par un client inconnu et bloque creation_llm (code 4, VRAM 5,9 Go) ; suspects : Aide_Visio de SérénIATech (`keep_alive` -1) ou préchargement du portail hors `--headless`
  - fait quand: client identifié (log de requêtes ou proxy) et corrigé ; le préchargement du portail passe par le jeton GPU ou est coupé.
  - réf: `src/vertia/engines/ollama_preload.py`.
- [P2|ouvert] Pause Windows Update posée jusqu'au 2026-12-18 : à renouveler si l'entraînement dure plus longtemps
  - fait quand: pause renouvelée avant le 2026-12-18 ou entraînement terminé.
  - réf: registre `HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings`.
- [P2|attente utilisateur] Contrôles manuels de l'Atelier (retouche IA, interface web jamais testée dans un navigateur)
  - fait quand: items 9 à 11 validés puis retirés de `tests_manuels.md`.
  - réf: `tests_manuels.md`.
- [P2|attente utilisateur] Diffuser la ligne d'usage du portail (`vertia_gen.py`, option `--note`) aux autres sessions, une seule fois, quand musique et voix sont dans le portail ; message à jean-luc-dariol en attente (scan abandonné, images à la main, retouche IA disponible)
  - fait quand: message envoyé aux sessions concernées après phase 5.
  - réf: `.claude/CLAUDE.md` (section Spécificités projet, ligne « IA locale »).
- [P2|décision requise] LFM3 : écoute de la voix (`outputs/lfm3_voix/tts_fr.wav`) et décision d'usage face à gemma4:e4b
  - fait quand: décision consignée dans `_docs/lfm3.md` et note retirée.
  - réf: `_contexte/notes_a_faire.md`, `_docs/lfm3.md`.
- [P2|ouvert] Orchestration phase 2 : calendrier GPU et audit d'historique des dépôts creation_3d, creation_videos, WorldModel (peut être obsolète : consolidation dans VertIA)
  - fait quand: calendrier écrit dans `roadmap_orchestration.md` et audit `--audit` constaté, ou action retirée.
  - réf: `roadmap_orchestration.md`, `_orchestration/pre_push_check.py`.
- [P2|attente utilisateur] Réponses dans les sessions orchestrées : creation_3d (2 cas véhicule/cartoon) ; WorldModel (mesure Matrix-Game) (peut être obsolète)
  - fait quand: DECISION reçue de chaque session ou action retirée.
  - réf: `_orchestration/sessions.md`.
- [P2|attente utilisateur] Test vidéo n°1 Wan 2.2 TI2V-5B et feu vert pour les candidats vidéo 2 et 3 (~42 Go sur D:) (peut être obsolète)
  - fait quand: résultats reportés dans `_docs/benchmark_video.md` ou actions retirées.
  - réf: `_docs/benchmark_video.md`, `tests_manuels.md`.
- Backlog : 5 entrées (dette 2, amélioration 2, piste 1) — `_contexte/backlog.md`

## Contexte chaud
- Pause GPU utilisateur levée le 2026-11-16 ; creation_llm repris (pas 20120). Un `unhold` ne se fait que sur ordre de l'utilisateur.
- Jeton GPU : état courant par `python _orchestration/vram_lock.py status`.
- Kit v6.5 appliqué par VibeObs (HEAD b7230f6) ; l'utilisateur a classé les 7 actions ouvertes de l'époque « Plus tard » chez VibeObs.
- Règle « Journal de session » de Spécificités projet en doublon partiel avec le tronc commun du kit : à juger.
- Résidus non commités : dossiers `.codex-test-*` (accès refusé) et `.tmp_*`.

## Dernière session (2026-11-16)
# Session du 2026-11-16

## Décisions prises
- Benchmark des agents de délégation (18 agents, 3 tâches) : choix par type de tâche dans `_docs/benchmark_agents.md`.
- Toute demande GPU passe avant creation_llm, qui tourne quand rien d'autre n'en a besoin ; session `shorts` créée après moulin_du_sud.
- CLAUDE.md : ligne « IA locale » (usage de `vertia_gen.py`) écrite après les trois validations ; diffusion aux autres sessions plus tard.
- Contrôle de reprise de creation_llm automatisé (`verif_reprise.py`) ; relance sans solliciter sauf problème majeur.

## Livrables produits ou modifiés
- Phase 3 : verrou GPU du portail, CLI, accueil, déplacement des poids avec jonctions, LFM3 évalué : faits et commités.
- Phase 4 : module image (`image.generer`, `image.retoucher`), Atelier retouche IA, essai réel validé (hors masque identique) : faits et commités.
- `roadmap_portail.md`, README, MISE_EN_PROD, CHANGELOG v0.3.0, `_docs/benchmark_agents.md` : commités à la clôture.

## Hypothèses validées / invalidées
- VALIDE : image migrée pixel-identique à la référence ; retouche de bout en bout.
- EN ATTENTE : interface web de l'Atelier dans un navigateur ; origine du chargement Ollama « Forever ».

## Prochaine étape exacte
`/compact`, puis phase 5 du portail (musique, voix, CreaZik_V3).

## Question bloquante pour la session suivante
Aucune.
