# Roadmap VertIA_v3 — V1

Objectif : studio d'IA 100 % locale pour novices. Un chat orchestrateur pilote la génération d'images (Qwen-Image 2.1 via ComfyUI), de musique (ACE-Step 1.5) puis de vidéo, avec file d'attente GPU exclusive, garde-fous mémoire et onglet Fichiers réutilisables.

Matériel de référence : RTX 4060 8 Go VRAM, 48 Go RAM, Windows 11. Une seule IA lourde en VRAM à la fois.
Architecture détaillée : [_docs/architecture.md](_docs/architecture.md).

Méthode : Claude chef de projet ; tâches bien délimitées déléguées à Codex / OpenCode via `_codex/` (brief → DryRun → run → revue du diff → commit par Claude). Sous-agents Claude pour l'exploration et les tâches nécessitant un contexte long. `file_agents.md` = qui fait quoi (jamais deux exécutants sur les mêmes fichiers).

---

## Phase 0 — Fondations [EN COURS]
- Squelette FastAPI (`src/vertia/`), `config.py` (Settings depuis `.env`), SQLite + migrations versionnées, bus d'événements SSE unique.
- `run.py` : uvicorn `--reload` + attente du port + ouverture du navigateur.
- Front vanilla en modules ES : layout à panneaux affichables/masquables (Chat, Fichiers, Mémoire & file, Outils), état persistant (localStorage), charte SérénIA Tech (polices locales Space Grotesk / Inter, tokens CSS).
- `MISE_EN_PROD.md` + commande `/mise_en_prod` + branchement dans `close.md` (bloc SPECIFICITES).
- Délégation : AGENTS.md, préambule `_codex`, `file_agents.md`.
- Tests : pytest (santé, config, migrations), contrat d'IDs UI.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 1 — Chat (port IA_V7 en async) [TODO]
- Client Ollama `httpx.AsyncClient` (stream, keep_alive, num_ctx cohérent, /api/ps, load/unload ciblé — jamais `taskkill` global).
- Dossiers (prompt système par dossier), conversations, messages, titre auto, éphémère corrigé (historique en mémoire).
- Gestion du contexte : fenêtre glissante + résumé incrémental des messages écartés, calibrage via `prompt_eval_count`, garde de dépassement.
- Streaming SSE, Stop fiable (annulation de la requête Ollama), rendu Markdown incrémental (marked + DOMPurify, pas de re-parse quadratique), blocs livrables copier/télécharger.
- File de messages : on peut envoyer pendant qu'une réponse est en cours (mise en file).
- Tests : FakeOllama, contexte, API, UI Playwright de base.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 2 — Ressources, file d'attente, garde-fous [TODO]
- Moniteur : VRAM (nvidia-smi + compteurs Windows par processus), RAM (psutil), modèles Ollama chargés.
- `GpuArbiter` : un seul moteur lourd actif (`none|ollama|comfy|ace|video`), libération automatique du précédent avant chaque job.
- File de jobs persistée (SQLite) : priorités, annulation, reprise après redémarrage, progression diffusée en SSE.
- Garde-fous configurables (seuils VRAM/RAM, refus explicite et compréhensible), arrêt après inactivité des moteurs.
- Onglet Mémoire & file : jauges, modèles chargés, boutons Décharger / Tout libérer, liste des jobs.
- Tests : arbitre et file avec moteurs simulés.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 3 — Registre d'outils, orchestrateur, image Qwen [TODO]
- Interface `Engine` (start/health/free/stop, besoin mémoire) + `Tool` (nom, description courte, schéma de paramètres, moteur) : ajouter une IA = ajouter un module.
- Orchestrateur : le LLM détecte l'intention et produit une **carte d'action** (prompt optimisé + paramètres) que l'utilisateur valide, modifie ou annule ; puis mise en file.
- Économie de tokens : schémas d'outils compacts injectés à la demande, routage léger, résumés, pas de ré-envoi des fichiers.
- `ComfyQwenEngine` : démarrage paresseux du ComfyUI existant (port 8189, correctifs, sans modifier le dossier), graphe API porté de `ui_simple/workflow.js` (t2i ; edit et inpaint prévus dans le schéma), progression websocket, `/free`.
- Tests : intention → carte d'action (benchmark à cas verrouillés), adaptateur simulé.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 4 — Fichiers générés [TODO]
- Stockage `outputs/<conversation>/` + table `fichiers` (type, source job, paramètres, prompt).
- Onglet Fichiers : galerie par conversation (images, audio, vidéo), aperçu, ouvrir, télécharger, ouvrir le dossier.
- Réutilisation : glisser ou bouton « Utiliser dans le chat » → pièce jointe référencée (image de référence pour édition/vidéo, audio pour cover).
- Tests API + UI.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 5 — Musique ACE-Step [TODO]
- `AceStepEngine` : serveur API du dossier existant (port 8001, offload CPU, backend pt, batch 1, 8 steps, mp3), arrêt du processus pour libérer la VRAM et après inactivité.
- Outil musique : paroles et caption générés par le LLM (reprise du pipeline CreaZik : JSON, validation des tags et syllabes, ajustement à la durée), carte d'action validable, instrumental ou chanté.
- Tests : validation paroles, adaptateur simulé.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 6 — Refacto et consolidation [TODO]
- Revue Codex en lecture seule de l'ensemble, correction de la dette, documentation développeur, couverture de tests.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 7 — Vidéo [TODO]
- Intégration du modèle retenu par la piste R (texte → vidéo et image Qwen → vidéo) comme nouveau moteur + outil.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 8 — Expérience novice et préparation distribution [TODO]
- Accueil guidé, messages d'erreur humains, aide contextuelle, état des moteurs lisible.
- Assistant de premier lancement : détection Ollama / ComfyUI / ACE-Step / modèles, chemins configurables.
- `MISE_EN_PROD.md` complet (installation chez l'utilisateur), plan d'installateur.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

---

## Piste R (parallèle) — Recherche et tests vidéo locale
- État de l'art des modèles vidéo open-weights compatibles 8 Go (Wan 2.2 TI2V 5B GGUF déjà présent dans ComfyUI-Qwen, LTX-Video déjà installé, WanGP, autres).
- Top 3 → fiches de test dans `tests_manuels.md` (l'utilisateur lance et juge) ; mesures temps / VRAM / qualité consignées dans `_docs/benchmark_video.md`.
- Choix du modèle validé par l'utilisateur avant la phase 7.
