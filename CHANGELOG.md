# Changelog

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
