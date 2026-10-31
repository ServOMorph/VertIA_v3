# Architecture VertIA_v3

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

## Mesure mémoire
- VRAM globale : `nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader,nounits`.
- VRAM par processus : `nvidia-smi --query-compute-apps` renvoie N/A en WDDM ; utiliser le compteur Windows `\GPU Process Memory(*)\Local Usage`.
- RAM : psutil.

## Gestion du contexte LLM (économie de tokens)
- Fenêtre glissante par paires, budget = num_ctx - marge réponse - système - message courant.
- Résumé incrémental des messages sortis de la fenêtre (un appel court, hors chemin critique, uniquement si le GPU est disponible pour Ollama).
- Schémas d'outils compacts, injectés seulement quand l'intention l'exige.
- Les fichiers ne sont jamais renvoyés au LLM : seulement une référence courte (id, type, prompt d'origine).
- Calibrage de l'estimation via `prompt_eval_count` renvoyé par Ollama.
