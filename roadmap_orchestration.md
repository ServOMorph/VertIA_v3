# Roadmap orchestration — sessions IA locales

Objectif : VertIA devient le portail des IA locales de l'utilisateur ; ses 4 sessions (creation_3d, WorldModel, creation_llm, creation_videos) sont pilotées comme sub-agents, une seule IA en VRAM à la fois (RTX 4060 8 Go). Protocole : `_orchestration/protocole.md`.

## Phase 1 — Mécanique centralisée [EN COURS]
- Verrou VRAM `vram_lock.py` (file, priorités, pause des tâches longues, mesure nvidia-smi) et `pre_push_check.py` (poids, secrets, historique) : faits, 19 tests verts.
- Protocole unique et règle CLAUDE.md : faits.
- Ligne de renvoi vers `protocole.md` dans le CLAUDE.md de chaque session : écrite par chaque session sur instruction directe de l'utilisateur (jamais par VertIA), puis passage en mode orchestré par l'utilisateur.
- Audit d'historique git (`--audit`) des 4 dépôts publics avant tout push.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 2 — Planification [TODO]
- Calendrier GPU : creation_llm en tâche longue (pré-entraînement 369M), blocs entiers pour les clips de creation_videos (54 min, non interruptibles), benchmarks courts de creation_3d et WorldModel intercalés.
- Priorités selon ce qui rapproche VertIA d'un portail utilisable.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 3 — Intégration dans VertIA [TODO]
- Copie des composants stabilisés dans VertIA (choix utilisateur : copie), derrière l'interface Engine/Tool de la phase 3 de `roadmap_vertia_v1.md`.
