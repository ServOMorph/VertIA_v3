# Signals — vertia   (MAJ 2026-11-01)

## Actions ouvertes
<!-- ≤ 20 entrées (ligne « Backlog » exclue) ; dette et findings non urgents -> _contexte/backlog.md -->
- [P1|ouvert] Phase 1 Chat : client Ollama httpx async, dossiers/conversations, contexte glissant + résumé, streaming SSE, Stop fiable, file de messages, tests FakeOllama
  - fait quand: phase 1 de la roadmap cochée [FAIT] avec tests pytest verts et chat fonctionnel dans l'UI.
  - réf: `roadmap_vertia_v1.md` (Phase 1), `_docs/architecture.md`, sources IA_V7 (lecture seule).
- [P2|attente utilisateur] Test vidéo n°1 Wan 2.2 TI2V-5B (tests A et B) à lancer par l'utilisateur ; aucune vidéo encore présente dans `ComfyUI-Qwen/output`
  - fait quand: temps, plantage et notes reportés dans le tableau Résultats de `_docs/benchmark_video.md`.
  - réf: `tests_manuels.md`, `_docs/benchmark_video.md`.
- [P2|décision requise] Feu vert pour télécharger les candidats vidéo 2 et 3 (~42 Go sur D:)
  - fait quand: réponse écrite de l'utilisateur (oui/non) consignée.
  - réf: `_docs/benchmark_video.md` (top 3).

## Contexte chaud
- Visionneuse vidéo (artefact privé, fichiers locaux déposés, export des lignes benchmark) : https://claude.ai/artifact/Y8DbJzb5FYfewr2dgLzmWK — non testée avec une vraie vidéo.
- `D:\ServOMorph\VibeObs\DEPLOYMENTS.md` : ligne VertIA_v3 ajoutée (seule écriture autorisée dans le kit).

## Dernière session (2026-11-01)
<!-- Écrasé intégralement par /close. Synthèse < 25 lignes. -->
# Session du 2026-11-01

## Décisions prises
- Stack FastAPI + vanilla, run.py autoreload, MISE_EN_PROD.md + /mise_en_prod, délégation Codex/OpenCode via `_codex/`.
- Top 3 vidéo : Wan 2.2 TI2V-5B (déjà sur disque), Wan 2.2 I2V A14B + lightx2v, LTX-2.3 ; Hunyuan 1.5, FramePack, MiniMax écartés (licences UE).

## Livrables produits ou modifiés
- Phase 0 Fondations : code, tests (8 passed), docs, commit e605f17 poussé.
- Visionneuse vidéo : artefact claude.ai (hors dépôt).
- DEPLOYMENTS.md du kit : ligne VertIA_v3.

## Hypothèses validées / invalidées
- VALIDE : interface à panneaux + SSE fonctionnels (contrôle Playwright).
- EN ATTENTE : faisabilité vidéo sur 8 Go (test n°1).

## Prochaine étape exacte
Démarrer la phase 1 (chat porté d'IA_V7 en async), en déléguant les parties délimitées via `_codex/`.

## Question bloquante pour la session suivante
Aucune.
