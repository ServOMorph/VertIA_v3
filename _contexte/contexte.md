# Contexte — vertia

## Objectif (immuable sauf décision explicite)
Studio d'IA 100 % locale pour novices : un chat orchestrateur pilote la génération d'images (Qwen/ComfyUI), de musique (ACE-Step) puis de vidéo, avec file d'attente et gestion optimisée de la VRAM (RTX 4060 8 Go).

## Stack / contraintes techniques (stable, rarement modifié)
Python 3.11+ / FastAPI / SQLite, front HTML/CSS/JS vanilla, Ollama, ComfyUI (API), ACE-Step (API), pytest + Playwright

## État actuel (réécrit intégralement à chaque /close)
v0.1.0 : phase 0 Fondations terminée (FastAPI, run.py autoreload, SQLite à migrations, SSE, préférences UI, panneaux masquables, charte SérénIA Tech ; 8 tests verts).
Phase 1 (chat porté d'IA_V7 en async) à démarrer.
Piste vidéo : top 3 établi, test n°1 Wan 2.2 TI2V-5B en attente de l'utilisateur.

## Décisions structurantes (append only — 10 entrées max, 5 lignes max/entrée, archiver au-delà)
- 2026-10-31 : Initialisation du protocole vibecoding.
- 2026-11-01 : FastAPI + front vanilla, run.py en autoreload ; MISE_EN_PROD.md maintenu par /close et contrôlé par /mise_en_prod.
- 2026-11-01 : Délégation du code à Codex/OpenCode via `_codex/`, Claude seul commite ; dossiers de référence en lecture seule.
- 2026-11-01 : Un seul moteur lourd en VRAM à la fois (GpuArbiter), file de jobs persistée, carte d'action validée par l'utilisateur.
