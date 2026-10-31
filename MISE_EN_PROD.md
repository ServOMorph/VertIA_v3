# Mise en production — VertIA

Directives d'installation et de lancement sur la machine d'un utilisateur. Maintenu à chaque `/close` ; vérifié par la commande `/mise_en_prod`.

## Prérequis
- Windows 10 ou 11, GPU NVIDIA conseillé (8 Go de VRAM minimum pour l'image et la vidéo).
- Python 3.11 ou supérieur dans le `PATH`.
- Ollama installé, avec au moins le modèle de chat (`ollama pull gemma4:12b`).
- Optionnel selon les outils : ComfyUI avec Qwen-Image 2.1 (image), ACE-Step 1.5 (musique).

## Moteurs externes
| Moteur | Rôle | Emplacement (variable) | Port |
|---|---|---|---|
| Ollama | chat / orchestration | service local | 11434 |
| ComfyUI-Qwen | images | `VERTIA_COMFY_DIR` | 8189 |
| ACE-Step 1.5 | musique | `VERTIA_ACESTEP_DIR` | 8001 |

VertIA démarre ces moteurs à la demande depuis leur dossier ; il ne les installe ni ne les modifie.

## Variables d'environnement
Copier `.env.example` en `.env` puis adapter :
- `VERTIA_HOST`, `VERTIA_PORT` : adresse de l'interface.
- `VERTIA_DATA_DIR`, `VERTIA_DATABASE`, `VERTIA_OUTPUTS_DIR` : données et fichiers générés.
- `OLLAMA_URL`, `VERTIA_DEFAULT_MODEL`, `VERTIA_NUM_CTX` : chat.
- `VERTIA_COMFY_DIR`, `VERTIA_COMFY_PORT`, `VERTIA_ACESTEP_DIR`, `VERTIA_ACESTEP_PORT` : moteurs.
- `VERTIA_VRAM_LIMIT_PERCENT`, `VERTIA_RAM_LIMIT_PERCENT` : garde-fous mémoire.

## Installation
```powershell
git clone https://github.com/ServOMorph/VertIA_v3.git
cd VertIA_v3
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

## Lancement
```powershell
.venv\Scripts\python run.py
```
Options : `--no-browser`, `--no-reload` (recommandé hors développement).

## Vérification
- `GET http://127.0.0.1:4310/api/sante` renvoie `{"statut": "ok"}`.
- L'interface s'ouvre et le badge affiche « en ligne ».

## Retour arrière
- Revenir à une version : `git checkout <tag>` puis relancer.
- La base `data/vertia.db` migre vers l'avant uniquement : la sauvegarder avant une mise à jour.

## Journal
- 2026-10-31 v0.1.0 : fondations (FastAPI, run.py, préférences UI, SSE).
