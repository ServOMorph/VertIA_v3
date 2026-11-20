# Changelog

## v0.5.0 - 2026-11-20

### Ajouté
- GPU réservé tant que l'interface est ouverte (`ReservationUi`, variable `VERTIA_RESERVER_GPU_UI`), besoin en jeton de Qwen déclaré (`MemoryNeeds.jeton_gb`).
- Capacité `image.analyser` (dialogue gemma4:12b, repérage de zones qwen2.5vl) et outil « Retouche dialoguée » de l'Atelier (routes `/api/analyse`).
- Design du chat repris d'IA_V7 (`chat.css`).
- `_docs/conception_retouche_dialoguee.md`.

### Modifié
- Roadmaps : `roadmap_portail.md` seule source des actions, `roadmap_vertia_v1.md` et `roadmap_orchestration.md` archivées ; creation_3d et WorldModel abandonnés. `run_codex.ps1` remplacé par la version du kit.

### Corrigé
- Lecture du JSON du dialogue tolérante au texte environnant ; gemma4 sans réflexion (157 s -> 46 s par tour).

## v0.4.0 - 2026-11-19

### Ajouté
- Modules du portail : voix (Chatterbox, Kokoro, Whisper), musique (ACE-Step, branchement de la génération de CreaZik_V3), vidéo (WanGP), chat (`chat.generer`, commandes /help /write /rgpd, capture, export typé, changement de modèle) ; Atelier servi sous `/atelier/`.
- Veille et benchmarks (`veille/`, `benchmarks/veille/`, `scripts/benchmark_*_veille.py`) ; phase 7-bis de la roadmap.
- Logo VertIA : arbre-circuit.

### Corrigé
- Verrou GPU : repli en thread quand la boucle asyncio ne permet pas les sous-processus (serveur à rechargement sous Windows), cause de l'échec de la retouche IA dans l'UI.
- Erreurs de demande jamais vides, trace complète journalisée, sortie de ComfyUI dans `data/logs/comfy_qwen.log`.

## v0.3.0 - 2026-11-16

### Ajouté
- Portail : registre de modules (`modules/`), chemins par `config/chemins.toml`, API `/api/v1`, commande `vertia_gen.py` avec boucle demande / essai / retour et livraison dans `outbox/`, écran d'accueil par activité, verrou GPU pris par le portail (creation_llm en pause puis reprise vérifiée).
- Modules : image (`image.generer`, `image.retoucher` par masque depuis `inbox/`), Atelier (éditeur d'image local avec outil Retouche IA, port 4320).
- Outils : `outils/deplacer_poids.py` (déplacement de poids avec jonction, simulation, retour arrière), banc des agents (`outils/bench_agents.py`), comparaison LFM3 (`outils/comparer_lfm3.py`).
- Documentation : `_docs/architecture_portail.md`, `_docs/migration_module.md`, `_docs/benchmark_agents.md`, `_docs/lfm3.md`.

### Modifié
- Poids ComfyUI-Qwen déplacés vers `models/comfy/` (54 Go, jonctions). Kit de protocole v6.5. `run_codex.ps1` : `-Model` et `-Effort`.
- Orchestration : session `shorts`, vérification automatique de la reprise de creation_llm (`verif_reprise.py`).

## v0.2.0 - 2026-11-13

### Ajouté
- Orchestration des sessions IA locales : jeton VRAM par script, contrôle anti-secrets avant push, protocole v2, reprise automatique après redémarrage (tâche Windows), 31 tests.
- Commande /telephone (kit VibeObs).

## v0.1.0 — 2026-10-31
- Création du dépôt, protocole vibecoding (zone vertia), kit de délégation Codex/OpenCode.
- Roadmap V1, architecture, recherche vidéo locale.
- Fondations : FastAPI, run.py (autoreload + navigateur), SQLite à migrations, bus SSE, préférences UI, interface à panneaux masquables, charte SérénIA Tech.
