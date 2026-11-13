# Contexte — vertia

## Objectif (immuable sauf décision explicite)
Studio d'IA 100 % locale pour novices : un chat orchestrateur pilote la génération d'images (Qwen/ComfyUI), de musique (ACE-Step) puis de vidéo, avec file d'attente et gestion optimisée de la VRAM (RTX 4060 8 Go).

## Stack / contraintes techniques (stable, rarement modifié)
Python 3.11+ / FastAPI / SQLite, front HTML/CSS/JS vanilla, Ollama, ComfyUI (API), ACE-Step (API), pytest + Playwright

## État actuel (réécrit intégralement à chaque /close)
Dernier commit produit : v0.1.0, phase 0 Fondations ; le code des phases 1 à 8 (Codex) est dans l'arbre de travail, non revu ni commité.
Orchestration (4 sessions IA locales) : mécanique commitée et poussée (jeton VRAM, contrôle pre-push, protocole v2, reprise auto) ; phase 2 de roadmap_orchestration.md en cours.
creation_llm détient le jeton GPU pour ~14 jours de pré-entraînement.

## Décisions structurantes (append only — 10 entrées max, 5 lignes max/entrée, archiver au-delà)
- 2026-10-31 : Initialisation du protocole vibecoding.
- 2026-11-01 : FastAPI + front vanilla, run.py en autoreload ; MISE_EN_PROD.md maintenu par /close et contrôlé par /mise_en_prod.
- 2026-11-01 : Délégation du code à Codex/OpenCode via `_codex/`, Claude seul commite ; dossiers de référence en lecture seule.
- 2026-11-01 : Un seul moteur lourd en VRAM à la fois (GpuArbiter), file de jobs persistée, carte d'action validée par l'utilisateur.
- 2026-11-13 : Orchestration des sessions creation_3d/WorldModel/creation_llm/creation_videos par `_orchestration/protocole.md` (jeton par script, escalades directes à l'utilisateur) ; jamais d'écriture dans les autres sessions.
- 2026-11-13 : Reprise auto des tâches GPU après redémarrage via `reprise_auto.py` + tâche Windows `VertIA_reprise_auto` ; pause Windows Update jusqu'au 2026-12-18.
