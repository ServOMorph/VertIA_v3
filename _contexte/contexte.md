# Contexte — vertia

## Objectif (immuable sauf décision explicite)
Studio d'IA 100 % locale pour novices : un chat orchestrateur pilote la génération d'images (Qwen/ComfyUI), de musique (ACE-Step) puis de vidéo, avec file d'attente et gestion optimisée de la VRAM (RTX 4060 8 Go).

## Stack / contraintes techniques (stable, rarement modifié)
Python 3.11+ / FastAPI / SQLite, front HTML/CSS/JS vanilla, Ollama, ComfyUI (API), ACE-Step (API), pytest + Playwright

## État actuel (réécrit intégralement à chaque /close)
Portail v0.3.0 : phases 1 à 4 de `roadmap_portail.md` faites (socle, CLI `vertia_gen.py`, accueil, image générer et retoucher, Atelier) ; phase 5 (musique, voix, CreaZik_V3) à lancer.
Le portail arbitre le GPU par le jeton `vertia` ; creation_llm (pré-entraînement) reprend seul, contrôle par `verif_reprise.py`.
Un modèle Ollama chargé en « Forever » par un client inconnu a bloqué la reprise ; origine à trouver.

## Décisions structurantes (append only — 10 entrées max, 5 lignes max/entrée, archiver au-delà)
- 2026-10-31 : Initialisation du protocole vibecoding.
- 2026-11-01 : FastAPI + front vanilla, run.py en autoreload ; MISE_EN_PROD.md maintenu par /close et contrôlé par /mise_en_prod.
- 2026-11-01 : Délégation du code à Codex/OpenCode via `_codex/`, Claude seul commite ; dossiers de référence en lecture seule.
- 2026-11-01 : Un seul moteur lourd en VRAM à la fois (GpuArbiter), file de jobs persistée, carte d'action validée par l'utilisateur.
- 2026-11-13 : Orchestration des sessions creation_3d/WorldModel/creation_llm/creation_videos par `_orchestration/protocole.md` (jeton par script, escalades directes à l'utilisateur) ; jamais d'écriture dans les autres sessions.
- 2026-11-13 : Reprise auto des tâches GPU après redémarrage via `reprise_auto.py` + tâche Windows `VertIA_reprise_auto` ; pause Windows Update jusqu'au 2026-12-18.
- 2026-11-16 : Toute demande GPU passe avant creation_llm (reprise seule) ; toute demande d'IA locale passe par `vertia_gen.py` (ligne dans CLAUDE.md, diffusion aux autres sessions après la phase 5).
- 2026-11-16 : Délégation par type de tâche selon `_docs/benchmark_agents.md` ; relance du benchmark à l'apparition d'un modèle ou après deux échecs.
- 2026-11-16 : Poids de modèles déplacés vers `models/` avec jonction ; LFM3 évalué, décision d'usage en attente.
