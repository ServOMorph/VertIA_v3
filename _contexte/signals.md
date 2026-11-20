# Signals — vertia   (MAJ 2026-11-20)

## Actions ouvertes
<!-- ≤ 20 entrées (ligne « Backlog » exclue) ; dette et findings non urgents -> _contexte/backlog.md -->
Toutes les actions et le backlog sont suivis dans `roadmap_portail.md` (phase 7-bis et section « Actions ouvertes hors phase »), depuis le 2026-11-20.
- [à transférer vers visioaide] `gemma4:e4b` reste chargé « Forever » par le backend VisioAide (`AIDE_VISIO_OLLAMA_KEEP_ALIVE` défaut -1, `config.py:91`) ; à corriger dans cette session, aucune écriture faite chez elle (règle : jamais d'écriture dans les autres sessions). fait quand: la session VisioAide a changé le défaut ou l'utilisateur a tranché. réf: `roadmap_portail.md` phase 7-bis.

## Contexte chaud
- Pause GPU utilisateur : non. Un `unhold` ne se fait que sur ordre de l'utilisateur. Jeton GPU : `python _orchestration/vram_lock.py status`.
- Portail : aucune instance ne tourne (l'ancienne instance headless du 2026-11-19 a été arrêtée avec l'accord de l'utilisateur, la suivante aussi) ; il redémarre seul au prochain `vertia_gen.py` ou par `python run.py`.
- Codex : drapeau `delegation_bloquee.flag` levé par l'utilisateur le 2026-11-20 (VibeObs), Codex de nouveau utilisable (gpt-6.2-sol, un appel à la fois, vérifier `model:` dans `log.txt`). Wrapper `run_codex.ps1` remplacé par la version du kit (verdict explicite).
- Retouche dialoguée : parcours réel de `image.analyser` constaté (phare, 1 min 14 s : dialogue 46 s, repérage 27 s) ; les zones d'ajout sont larges (qwen répond par une région), à réduire à la main avant application. Le test dans l'Atelier reste à faire.
- Résidus non commités : dossiers `.codex-test-*` (accès refusé), `veille/`, `benchmarks/veille/`, `scripts/benchmark_*_veille.py`, `.tmp_*`.

## Dernière session (2026-11-20)
# Session du 2026-11-20

## Décisions prises
- `roadmap_portail.md` devient la source unique des actions ; `roadmap_vertia_v1.md` et `roadmap_orchestration.md` archivées dans `_docs/archives/` ; creation_3d et WorldModel abandonnés (phases 8 à 10).
- Retouche dialoguée dans l'Atelier : gemma4:12b pour le dialogue puis qwen2.5vl pour repérer les zones ; gemma4 sans réflexion (`think=False`, 157 s -> 46 s).
- Codex bloqué par le drapeau d'urgence de l'utilisateur : non contourné, OpenCode utilisé, VibeObs alerté ; drapeau levé ensuite par l'utilisateur.
- Arrêt de l'ancien portail headless accordé par l'utilisateur pour l'essai réel.

## Livrables produits ou modifiés
- Phase 7-bis : réservation du GPU tant que l'UI est ouverte (`src/vertia/gpu/reservation.py`, `VERTIA_RESERVER_GPU_UI`), jeton de Qwen déclaré (`jeton_gb`), design du chat IA_V7 (`chat.css`) : commités (1df9546, 098dbf9), à valider à l'écran.
- `image.analyser` (lot 2, 6a68c13, correctif 56d0e81) et outil « Retouche dialoguée » de l'Atelier (lot 3, d112ba9) : livrés, essai réel de la capacité réussi, outil non essayé à l'écran.
- `_docs/conception_retouche_dialoguee.md`, `tests_manuels.md` (3 sections), `_codex/run_codex.ps1` (version du kit) : à jour. Suite complète : 1070 tests verts.

## Hypothèses validées / invalidées
- VALIDE : qwen2.5vl repère un objet visible (IoU 0,94 phare, 0,67 porte) avec un cadre d'environ 1 Mpx multiple de 28 ; `image.analyser` livre 4 propositions avec zones sur le phare.
- INVALIDE : gemma4 comme repéreur de zones (repère instable) ; sortie JSON toujours pure (une réponse a échoué, lecture rendue tolérante).
- EN ATTENTE : gate benchmark de la retouche dialoguée (6 images, IoU >= 0,5 sur 70 % des zones) ; tests manuels de la phase 7-bis.

## Prochaine étape exacte
Dérouler les tests manuels de `tests_manuels.md` (design du chat, GPU réservé, retouche dialoguée dans l'Atelier, retouche IA et logo), puis `/compact` et clôture de la phase 7-bis.

## Question bloquante pour la session suivante
Versionner ou écarter `veille/`, `benchmarks/veille/` et `scripts/benchmark_*_veille.py` ?
