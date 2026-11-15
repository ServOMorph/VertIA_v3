# Architecture VertIA_v3

Architecture cible du portail (consolidation, validée le 2026-11-15) : `_docs/architecture_portail.md`. Elle prime sur l'arborescence ci-dessous à partir de la phase 3 de `roadmap_portail.md`.

## Principes
- Une IA = un module branchable (`Engine` + un ou plusieurs `Tool`). Le cœur ne connaît aucune IA en dur.
- GPU exclusif : un seul moteur lourd chargé à la fois, arbitré par `GpuArbiter` ; tout travail GPU passe par la file de jobs.
- Le chat orchestre : il propose une carte d'action (prompt optimisé + paramètres), l'utilisateur valide, le job part en file.
- Les dossiers des moteurs externes (ComfyUI-Qwen, ACE-Step-1.5, Ollama) sont utilisés en place, jamais modifiés ni copiés. Leurs chemins sont configurables (`.env`).
- Code maintenable : couches nettes, injection des clients externes (tests sans GPU), fonctions courtes, pas de variables globales côté front.

## Stack
- Backend : Python 3.11+, FastAPI, uvicorn, httpx (async), sqlite3 (WAL), psutil.
- Front : HTML/CSS/JS vanilla en modules ES, sans bundler. Vendor local : marked, DOMPurify. Polices locales (Space Grotesk, Inter).
- Tests : pytest (+ pytest-asyncio), Playwright (Edge).

## Arborescence cible
```
run.py                     uvicorn --reload + ouverture navigateur
src/vertia/
  config.py                Settings (dataclass figée, .env)
  app.py                   create_app(settings, overrides) : assemblage et injection
  core/
    db.py                  connexion, migrations versionnées
    events.py              bus d'événements -> SSE /api/events
  chat/                    port IA_V7 (repository, context, service, commands)
  engines/
    base.py                Engine (start, health, free, stop, besoin mémoire)
    ollama.py  comfy_qwen.py  acestep.py  (video_*.py)
  tools/
    base.py                Tool (nom, description, schéma, moteur, run)
    registry.py            découverte et schémas compacts pour le LLM
    image.py  music.py  (video.py)
  jobs/
    queue.py               file persistée, priorités, annulation, reprise
    arbiter.py             GpuArbiter
  resources/
    monitor.py             VRAM / RAM / modèles chargés, garde-fous
  files/                   fichiers générés, réutilisation dans le chat
  web/                     routeurs FastAPI (un par domaine)
  static/  templates/
data/                      base SQLite (non versionné)
outputs/<conversation>/    fichiers générés (non versionné)
```

## Moteurs externes (faits relevés le 2026-10-31)

### Ollama
- `OllamaService` supervise uniquement le service HTTP, dans une tâche du lifespan FastAPI indépendante des jobs GPU. Réutilisation si `/api/tags` répond comme attendu ; sinon, sur refus de connexion local, lancement caché de l’exécutable installé avec `serve`, `OLLAMA_HOST` local et environnement hérité. Aucun téléchargement ni mise à mort globale. Fermeture de l’arbre détenu uniquement à l’arrêt de VertIA, même si le nettoyage d’un autre moteur échoue.
- `OllamaPreload` attend que le service soit disponible, vérifie que le modèle par défaut est installé, puis soumet une seule tâche `prechargement_ollama` à la file GPU (priorité 100, non rejouable). Préparation ciblée et chargement avec le même `num_ctx` et `keep_alive=-1` que le chat ; garde mémoire et exclusivité de l’arbitre conservées. Une annulation attend la fin de l’appel de chargement avant de décharger le modèle et libérer le verrou GPU. Le statut de préchargement est conservé dans l’instantané/SSE du service. Un déchargement manuel, une inactivité ou un autre moteur ne provoquent pas de nouveau préchargement automatique.
- État HTTP/modèles contrôlé par GET bornés (connexion cinq secondes, lecture deux secondes), attente du service lancé limitée à 30 secondes, rafraîchissement toutes les trois secondes via `ollama.etat` et instantané `/api/ollama/etat` avec révision. Le délai de connexion permet de recevoir le refus TCP Windows, mesuré à environ 2,04 secondes le 2026-11-07 ; une limite de deux secondes empêchait le lancement automatique en produisant ConnectTimeout avant ConnectError. Modèles chargés inconnus distingués d’une liste vide ; badge séparé de la connexion VertIA, liste des modèles installés actualisée automatiquement à la disponibilité. Options `.env` : `VERTIA_OLLAMA_AUTOSTART` (vrai par défaut), `VERTIA_OLLAMA_EXECUTABLE` (chemin absolu facultatif). Le diagnostic de l’accueil reste passif.
- `http://127.0.0.1:11434`, modèles dans `D:\OllamaModels` : gemma4:12b, gemma4:12b-32k, gemma4:e4b, qwen3.5, qwen2.5:7b, llama3.2:3b, gemma3:1b/4b, qwen2.5vl, llava:7b, nomic-embed-text.
- Chat : `POST /api/chat` stream NDJSON. Charger/décharger : `POST /api/generate` `prompt:""`, `keep_alive` -1 / 0, même `num_ctx` que le chat. État : `/api/ps`, `/api/tags`.
- Ne jamais tuer `ollama.exe` globalement.

### ComfyUI-Qwen (`D:\ServOMorph\ComfyUI-Qwen`)
- Lancement : appliquer `correctifs\appliquer.bat` puis `.venv\Scripts\python.exe main.py --port 8189` (modèle : `run_ui_simple.py`), attendre `GET /system_stats` (jusqu'à 600 s).
- Modèles : `unet\qwen-image-2.1-Q4_K_M.gguf` (UnetLoaderGGUF), `text_encoders\qwen3vl_8b_bf16.safetensors` (CLIPLoader type qwen_image, ~17 Go en RAM), `vae\qwen_image_2.1_vae_bf16.safetensors`. Aussi présents : Wan2.2-TI2V-5B-Q4_K_M + umt5 + wan2.2_vae, Z-Image Turbo.
- Graphe API de référence : `ui_simple\workflow.js` `construireGraphe(p)` (t2i, edit via images de référence dans `TextEncodeQwenImage21`, inpaint). KSampler cfg 1, euler/simple, 15 (rapide) / 25-30 (qualité) steps, dimensions multiples de 32.
- API : `POST /prompt`, `GET /history/{id}`, `GET /view`, `POST /upload/image`, `WS /ws?clientId=`, `POST /interrupt`, `POST /queue {"clear":true}`, `POST /free {"unload_models":true,"free_memory":true}`.
- Perf : ~95 s / image 1024² à 25 steps à chaud ; 255-345 s premier prompt.

### ACE-Step 1.5 (`D:\ServOMorph\ACE-Step-1.5`)
- Lancement : `.venv\Scripts\python.exe acestep\api_server.py --host 127.0.0.1 --port 8001` (ne jamais utiliser `start_api_server.bat`, prompt interactif). Env : `ACESTEP_CONFIG_PATH=acestep-v15-turbo`, `ACESTEP_OFFLOAD_TO_CPU=true`, `ACESTEP_LM_BACKEND=pt`, `ACESTEP_INIT_LLM=false`.
- API : `POST /release_task` (prompt, lyrics, vocal_language, audio_duration, bpm, inference_steps=8, batch_size=1, audio_format=mp3), `POST /query_result`, `GET /v1/audio?path=`, `GET /health`.
- Pas d'endpoint de déchargement : libérer la VRAM = arrêter le processus (arbre).
- Perf : init à froid ~90 s ; morceau 50-125 s généré en 8-22 s.
- Paroles : reprendre le pipeline CreaZik (`webradio\user_songs.py`, `TEXTES\tools\generate_lyrics.py`, `check_lyrics.py`) : JSON {titre, caption anglais 5-8 termes, bpm, paroles à tags [verse]/[chorus]}.

### Vidéo (piste R)
- Déjà sur disque : Wan2.2-TI2V-5B GGUF (ComfyUI-Qwen), LTX-Video 2B 0.9.8 distilled (`D:\ServOMorph\LTX-Video\ComfyUI`), WanGP (`D:\AI\WanGP`).
- Voir `_docs/benchmark_video.md`.
- Choix utilisateur du 2026-11-02 : Wan 2.2 TI2V-5B GGUF Q4_K_M. `WanVideoEngine` construit le graphe et délègue transport/cycle de vie au même `ComfyQwenEngine` que l’image. `VideoTool.engine = comfy` : un seul propriétaire de processus, un seul prompt actif, une seule identité d’arbitrage. Aucun second serveur ni client HTTP à fermer.
- ComfyUI lancé par VertIA utilise désormais `--lowvram --reserve-vram 1` pour les deux outils. Une instance déjà active conserve ses propres options. Graphe vidéo : CLIP Wan/umt5, Wan22ImageToVideoLatent (image initiale optionnelle), ModelSamplingSD3 shift 8, uni_pc/simple CFG 5, VAE tuilé, CreateVideo 24 fps, SaveVideo MP4 H.264. Les besoins réels Wan restent inconnus ; la marge minimale commune de 17 Go RAM héritée de Qwen est conservatrice, pas une estimation Wan.
- Carte vidéo : 256..960 par axe (multiples de 32), surface maximale 960×544, 17..73 images (4n+1), 1..30 étapes, une référence image au plus. Défaut 640×384, 49 images, 20 étapes ; environ deux secondes muettes. Contrats nœuds lus dans les sources ComfyUI locales et [template officiel](https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/video_wan2_2_5B_ti2v.json) ; aucun test GPU effectué.

## Mesure mémoire
- Réutilisation résidente : les tâches Chat/résumé/préchargement transmettent le nom du modèle à la file en mémoire, sans persistance ni prompt. Sous le verrou GPU et après libération des autres moteurs, l’adaptateur Ollama vérifie dans le nouvel échantillon qu’un seul modèle GPU est chargé, qu’il correspond au modèle demandé et que son `context_length` est exactement le `num_ctx` actif. Alors le seuil de chargement (92 % par défaut) est remplacé par une réserve libre d’au moins 512 Mio et 3 % de chaque GPU. Réserve configurable par `VERTIA_RESIDENT_VRAM_RESERVE_MB` (minimum 128). Le seuil RAM reste inchangé ; modèle différent, métadonnées absentes ou contexte différent conservent le seuil VRAM normal. Aucune garantie sur les allocations supplémentaires pendant l’inférence.
- VRAM globale : `nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader,nounits`.
- VRAM par processus : `nvidia-smi --query-compute-apps` renvoie N/A en WDDM ; utiliser le compteur Windows `\GPU Process Memory(*)\Local Usage`. La classe CIM fournit l’identifiant d’instance dans `Name` ; le parseur conserve aussi la compatibilité avec `InstanceName`.
- RAM : psutil.

## Gestion du contexte LLM (économie de tokens)
- Fenêtre glissante par paires, budget = num_ctx - marge réponse - système - message courant.
- Résumé incrémental des messages sortis de la fenêtre (un appel court, hors chemin critique, uniquement si le GPU est disponible pour Ollama).
- Schémas d'outils compacts, injectés seulement quand l'intention l'exige.
- Les fichiers ne sont jamais renvoyés au LLM : seulement une référence courte (id, type, prompt d'origine).
- Calibrage de l'estimation via `prompt_eval_count` renvoyé par Ollama.

## Premier lancement et configuration
- Présentation inspirée de Codex : sections latérales Épinglés/Projets, affichage progressif des discussions, bulle utilisateur et réponses assistant sans carte. Les styles de chat sont dans `static/css/chat.css`, chargés après `app.css`. La copie de chaque message utilise son texte source, y compris le Markdown assistant et le flux incrémental courant, avec retour de succès/échec accessible.
- Navigation : dossiers et discussions dans un panneau gauche, épinglage et ordre persistés dans leurs tables SQLite (migration additive). Une discussion peut changer de dossier hors tâche active ; supprimer un dossier conserve ses discussions. Les métadonnées des discussions éphémères restent en mémoire. Les dossiers se déplient et le glisser-déposer possède une alternative par menu (déplacement, monter/descendre).
- Le bouton d’accès ferme immédiatement l’accueil, même si la mémorisation de la préférence échoue ou reste sans réponse. Les lectures de configuration et la mémorisation ont un délai de cinq secondes ; une erreur de mémorisation est signalée dans Discussion. HTML, JS et CSS demandent une revalidation du cache navigateur.
- `setup.py` valide les réglages et réalise un diagnostic en lecture seule : GET locaux limités à deux secondes, présence des fichiers attendus. Aucun appel de cycle de vie moteur ni job GPU. Les marqueurs disque ne valident ni poids ni contrats de nœuds.
- `.vertia-local.json` contient les six réglages de l’assistant, enregistrés par remplacement atomique. `Settings.from_env()` les applique après `.env`/environnement et avant les overrides injectés pour les tests. Paramètres figés pendant l’instance ; redémarrage explicite requis, sans remplacement à chaud des moteurs ou outils.
- L’accueil et le diagnostic sont disponibles par `/api/installation`. La fin de l’accueil est une préférence SQLite. Les dossiers restent externes et ne sont pas modifiés par l’assistant. Les ports moteurs sont distincts et l’adresse Ollama saisie doit être locale.
