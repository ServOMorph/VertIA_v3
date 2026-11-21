# Contexte — vertia

## Objectif (immuable sauf décision explicite)
Studio d'IA 100 % locale pour novices : un chat orchestrateur pilote la génération d'images (Qwen/ComfyUI), de musique (ACE-Step) puis de vidéo, avec file d'attente et gestion optimisée de la VRAM (RTX 4060 8 Go).

## Stack / contraintes techniques (stable, rarement modifié)
Python 3.11+ / FastAPI / SQLite, front HTML/CSS/JS vanilla, Ollama, ComfyUI (API), ACE-Step (API), pytest + Playwright

## État actuel (réécrit intégralement à chaque /close)
Portail v0.6.0 : phases 1 à 7 de `roadmap_portail.md` faites ; phase 7-bis codée, gate benchmark de la retouche dialoguée atteint (21/24 zones, JSON 6/6, références à valider), reste les tests manuels à l'écran ; phase 7-ter (LFM3 utilitaire texte + vision) à faire ensuite, puis phase 11 ; phases 8 à 10 abandonnées.
Le portail arbitre le GPU par le jeton `vertia` ; creation_llm (pré-entraînement) reprend seul, contrôle par `verif_reprise.py`. Suite complète : 1070 tests verts (2026-11-20).
FLUX 3 Klein en attente de la licence de l'utilisateur ; veille et benchmarks versionnés dans `veille/` et `benchmarks/`.

## Décisions structurantes (append only — 10 entrées max, 5 lignes max/entrée, archiver au-delà)
- 2026-11-01 : Un seul moteur lourd en VRAM à la fois (GpuArbiter), file de jobs persistée, carte d'action validée par l'utilisateur.
- 2026-11-13 : Orchestration des sessions creation_3d/WorldModel/creation_llm/creation_videos par `_orchestration/protocole.md` (jeton par script, escalades directes à l'utilisateur) ; jamais d'écriture dans les autres sessions.
- 2026-11-13 : Reprise auto des tâches GPU après redémarrage via `reprise_auto.py` + tâche Windows `VertIA_reprise_auto` ; pause Windows Update jusqu'au 2026-12-18.
- 2026-11-16 : Toute demande GPU passe avant creation_llm (reprise seule) ; toute demande d'IA locale passe par `vertia_gen.py` (ligne dans CLAUDE.md, diffusion aux autres sessions après la phase 5).
- 2026-11-16 : Délégation par type de tâche selon `_docs/benchmark_agents.md` ; relance du benchmark à l'apparition d'un modèle ou après deux échecs.
- 2026-11-16 : Poids de modèles déplacés vers `models/` avec jonction ; LFM3 évalué, décision d'usage en attente.
- 2026-11-18 : chat dans le cœur du portail plus module `chat.generer` sur le moteur ollama partagé ; ports IA_V7 retenus (/help, /write, /rgpd, capture, export typé, changement de modèle, renommage) ; mode Code, /controle_pc, taskkill écartés.
- 2026-11-19 : demandes rangées en phase 7-bis (VRAM à l'ouverture de l'UI, design IA_V7, retouche dialoguée) ; copie séparée de ComfyUI pour FLUX 3 ; logo VertIA remplacé.
- 2026-11-20 : roadmap_portail.md seule source des actions, creation_3d et WorldModel abandonnés ; retouche dialoguée = gemma4:12b (dialogue, sans réflexion) puis qwen2.5vl (zones), dans l'Atelier ; interrupteur Codex = drapeau de l'utilisateur, jamais contourné.
- 2026-11-21 : LFM3 adopté comme utilitaire texte + vision (phase 7-ter), gemma4:12b reste le modèle de discussion ; granite4.2:8b supprimé ; gate de la retouche dialoguée = `scripts/benchmark_retouche_gate.py` (6 images, références tracées par Claude, à valider).
