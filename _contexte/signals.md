# Signals — vertia   (MAJ 2026-11-19)

## Actions ouvertes
<!-- ≤ 20 entrées (ligne « Backlog » exclue) ; dette et findings non urgents -> _contexte/backlog.md -->
- [P1|ouvert] Reprise auto de creation_llm après un vrai redémarrage Windows jamais éprouvée (la reprise après pause GPU l'est, contrôle auto par `verif_reprise.py`)
  - fait quand: un redémarrage réel a relancé `run_369m.py` (ligne dans `state/reprise.log`) ou l'entraînement est terminé.
  - réf: `_orchestration/reprise_auto.py`, `_orchestration/verif_reprise.py`.
- [P2|ouvert] Un modèle Ollama `gemma4:e4b` est chargé en « Forever » par un client inconnu et bloque creation_llm (code 4, VRAM 5,9 Go) ; suspects : Aide_Visio de SérénIATech (`keep_alive` -1) ou préchargement du portail hors `--headless`
  - fait quand: client identifié (log de requêtes ou proxy) et corrigé ; le préchargement du portail passe par le jeton GPU ou est coupé.
  - réf: `src/vertia/engines/ollama_preload.py`.
- [P2|ouvert] Pause Windows Update posée jusqu'au 2026-12-18 : à renouveler si l'entraînement dure plus longtemps
  - fait quand: pause renouvelée avant le 2026-12-18 ou entraînement terminé.
  - réf: registre `HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings`.
- [P1|ouvert] Phase 7-bis (demandes du 2026-11-19) : libération de la VRAM au lancement de l'UI, design du chat repris d'IA_V7 (examen en lecture seule du dossier IA_V7), outil de retouche d'image dialoguée ; retouche IA : cause trouvée et corrigée, reste le test manuel dans l'Atelier
  - fait quand: les quatre points de la phase 7-bis de la roadmap sont faits et la phase passée `[FAIT]`.
  - réf: `roadmap_portail.md` (phase 7-bis), `tests_manuels.md`.
- [P1|attente utilisateur] `/compact` avant la phase 8 (checkpoint de la phase 7 jamais confirmé par écrit)
  - fait quand: l'utilisateur a confirmé par écrit le `/compact`.
  - réf: `roadmap_portail.md`.
- [P2|attente utilisateur] FLUX 3 Klein : accepter la licence FLUX sur Hugging Face et fournir un jeton, puis téléchargement d'environ 11 Go et essai dans `engines/comfy-flux3` (ComfyUI 0.46.0, installé, jamais lancé) ; vérifier que cette version prend en charge FLUX 3
  - fait quand: essai réalisé et résultat ajouté à `benchmarks/veille/rapport_resultats.md`, ou piste écartée.
  - réf: `engines/comfy-flux3`, `benchmarks/veille/rapport_resultats.md`.
- [P2|décision requise] Supprimer ou garder granite4.2:8b (Ollama) et les fichiers de `models/veille/` (garder le VAE de 0,25 Go recommandé)
  - fait quand: décision de l'utilisateur appliquée.
  - réf: `models/veille/`, `benchmarks/veille/rapport_resultats.md`.
- [P2|ouvert] Fichiers non versionnés à décider (versionner ou écarter) : `veille/`, `benchmarks/veille/`, `scripts/benchmark_*_veille.py` ; consentement d'écriture d'AGENTS.md par VibeObs (commit 920371e, poussé le 2026-11-19) non confirmé par écrit
  - fait quand: fichiers versionnés ou écartés ; consentement confirmé.
  - réf: `veille/`, `AGENTS.md`.
- [P2|ouvert] Fermer la session creation_videos (migration validée) ; renard (poly_fox) pour creation_3d sur demande séparée
  - fait quand: session fermée ; demande renard reçue ou écartée.
  - réf: `_orchestration/sessions.md`.
- [P2|ouvert] Licence Qwen Research License de Qwen-Image 2.1 à lire par l'utilisateur avant tout usage commercial
  - fait quand: licence lue par l'utilisateur, décision consignée.
  - réf: `benchmarks/veille/rapport_resultats.md`.
- [P2|attente utilisateur] Contrôles manuels de l'Atelier (retouche IA, interface web jamais testée dans un navigateur)
  - fait quand: items 9 à 11 validés puis retirés de `tests_manuels.md`.
  - réf: `tests_manuels.md`.
- [P2|attente utilisateur] Diffuser la ligne d'usage du portail (`vertia_gen.py`, option `--note`) aux autres sessions, une seule fois, maintenant que image, musique, voix, vidéo et chat sont dans le portail ; message à jean-luc-dariol en attente (scan abandonné, images à la main, retouche IA disponible) ; trois validations pour toucher CLAUDE.md des autres sessions
  - fait quand: message envoyé aux sessions concernées.
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
- Backlog : 6 entrées (dette 3, amélioration 2, piste 1) — `_contexte/backlog.md`

## Contexte chaud
- Pause GPU utilisateur : non ; creation_llm repris (REPRISE_OK pas 40590 à 21:16 le 2026-11-19). Un `unhold` ne se fait que sur ordre de l'utilisateur.
- Jeton GPU : état courant par `python _orchestration/vram_lock.py status`.
- Portail relancé le 2026-11-19 en headless (code avec correctifs, sortie dans `data/logs/portail.err`) ; l'Atelier de l'utilisateur a été fermé par ce redémarrage. L'UI avec rechargement automatique (`run.py`) prend désormais le jeton GPU sans erreur (repli en thread).
- Résidus non commités : dossiers `.codex-test-*` (accès refusé), `.tmp_*`.

## Dernière session (2026-11-19)
# Session du 2026-11-19 (journal du 2026-11-16 au 2026-11-19 intégré)

## Décisions prises
- Phases 5 (voix, musique, branchement CreaZik), 6 (vidéo WanGP, Atelier dans le portail) et 7 (chat, module chat.generer, ports IA_V7) livrées ; la phase 7 reste à confirmer par `/compact`.
- Veille et benchmarks (chat, image, vidéo) faits sous jeton ; FLUX 3 Klein sauté (licence à accepter par l'utilisateur), MOSS-Image bloqué (ComfyUI 0.38.0).
- Demandes du 2026-11-19 rangées en phase 7-bis : VRAM libérée au lancement de l'UI, design du chat d'IA_V7, retouche dialoguée, correction de la retouche IA.
- Copie séparée de ComfyUI (engines/comfy-flux3, v0.46.0) autorisée pour FLUX ; logo VertIA remplacé par l'arbre-circuit de l'utilisateur.

## Livrables produits ou modifiés
- Modules voix, musique, vidéo, chat, Atelier intégré : faits et commités (voir CHANGELOG v0.4.0).
- Correctifs retouche IA : verrou GPU en repli thread sous boucle Selector (cause du NotImplementedError dans l'UI à rechargement), erreur jamais vide, journal de ComfyUI dans `data/logs/comfy_qwen.log`, trace des échecs de demande ; 930 tests verts.
- `veille/`, `benchmarks/veille/` : créés, non versionnés.

## Hypothèses validées / invalidées
- VALIDE : retouche IA par masque livrée par le portail (10 min, session de test) une fois l'ancienne instance arrêtée.
- INVALIDE : cause mémoire seule de l'échec de retouche -> l'échec dans l'UI venait du sous-processus asyncio sous Windows ; l'erreur mémoire de l'encodeur (16,7 Go) reste possible sous pression de RAM.
- EN ATTENTE : test manuel de la retouche dans l'Atelier, design du chat, FLUX 3 Klein.

## Prochaine étape exacte
`/compact`, puis phase 7-bis (libération de la VRAM à l'ouverture de l'UI, design du chat d'IA_V7).

## Question bloquante pour la session suivante
Supprimer ou garder granite4.2:8b et `models/veille/` ?
