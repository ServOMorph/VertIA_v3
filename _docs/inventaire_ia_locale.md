# Inventaire IA locale — D: et C: (2026-11-13)

Phase 1 de `roadmap_portail.md`. Lecture seule : rien n'a été modifié, déplacé ni lancé.
Source : scripts de mesure (tailles par `robocopy /L`, état git, venvs, poids > 100 Mo). Les rôles des projets sont déduits des noms de dossiers et de fichiers, pas de la lecture du code : toute colonne « module » est une hypothèse à confirmer.

## Espace disque
- D: 1 330 Go libres (1 464 Go utilisés). C: 133 Go libres (797 Go utilisés).
- Caches IA sur C: négligeables : `.cache` 8,6 Go (Whisper large-v3 et autres), `AppData\Local\Ollama` 1,8 Go, `.ollama` vide. Les modèles Ollama sont sur `D:\OllamaModels`.
- L'espace n'est pas une contrainte pour la migration : le seuil de 100 Go libres sur D: est très loin.

## Poids de modèles (la masse du chantier)
| Emplacement | Taille | Contenu relevé |
|---|---|---|
| `D:\AI` | 273,7 Go | WanGP 199,9 ; Musique 38,8 (heartlib, musicgen) ; MimicMotion 25,1 ; TripoSR 4,9 ; kimodo 4,8 ; UniRig 0,2 |
| `D:\HuggingFaceCache` | 228,5 Go | FLUX.1-dev 31,4 ; FLUX.1-schnell 31,4 ; Llama-3-8B 29,9 ; Mistral-7B 13,5 ; UniRig 10,8 ; datasets (wikipedia 8,6) ; oasis 7,6 ; LTX-Video 5,9 ; ResembleAI chatterbox 6,0 ; autres |
| `D:\ServOMorph\LTX-Video` | 81,6 Go | dont `.cache` 74,7 et `.venv` 5,7 |
| `D:\ServOMorph\creation_llm` | 74,0 Go | 33 fichiers > 100 Mo, checkpoints et jeux de données binaires |
| `D:\ServOMorph\ComfyUI-Qwen` | 54,8 Go | 11 poids (qwen3vl_8b 16,3 ; sdxl_lightning 6,5 ; umt5_xxl 6,3) |
| `D:\ServOMorph\ACE-Step-1.5` | 52,5 Go | checkpoints 10,7 ; `output` 34,6 (musiques générées) ; `.venv` 7,2 |
| `D:\OllamaModels` | 46,8 Go | 13 modèles : gemma3 (1b, 4b), gemma4 (12b, 12b-32k, e4b), llama3.2 3b, llava 7b, nomic-embed-text, qwen2.5 7b, qwen2.5-coder 7b, qwen2.5vl, qwen3.5, Flux_AI |
| `D:\ServOMorph\Flux` | 31,5 Go | `models_cache` FLUX.1-dev |
| `D:\ServOMorph\IA_Locales` | 30,0 Go | `Hunyuan3D2_WinPortable` 26,8 |
| `D:\ServOMorph\ComfyUI-SANA` | 29,9 Go | 7 poids dont un `*.invalide-20260912` |
| `D:\ServOMorph\TTS_Local` | 23,5 Go | chatterbox 5,1 ; hf_cache 11,7 ; `_uv_cache` 5,8 ; kokoro 0,9 |
| `D:\ServOMorph\WorldModel` | 20,6 Go | 3 poids (base_distill 6,0 ; open-clip 4,4) |
| `D:\ai-cache` | 12,2 Go | huggingface 7,5 ; uv 4,7 |
| `D:\Dev` | 11,5 Go | z_image_turbo Q5_0, Qwen3-4B Q4_K_M |
| `D:\tools` | 8,5 Go | stable-fast-3d 6,6 ; ghidra 0,8 ; mpfb_assets 0,5 |
| `D:\tmp` | 7,2 Go | non examiné |

Total des seuls dossiers ci-dessus : plus de 1 000 Go. Le déplacement vers `models/` porte donc sur un ordre de grandeur de plusieurs centaines de Go, pas sur quelques dizaines.

## Doublons de poids
Méthode : fichiers > 500 Mo de même taille à des chemins différents. La taille identique n'est pas une preuve : un contrôle par empreinte reste à faire avant toute suppression.
- **Très probable** : FLUX.1-dev présent dans `D:\ServOMorph\Flux\models_cache` et `D:\HuggingFaceCache\hub` avec le même identifiant de snapshot (3de623fc...). Environ 31 Go récupérables.
- **Probable** : blobs `svdq-int4-sana-1600m` en double dans `ComfyUI-SANA` (`models_cache`, `sana_models_cache`, et `models\...-propre`) : environ 2,5 Go.
- **À vérifier** : text_encoder_2 de FLUX.1-dev et FLUX.1-schnell (mêmes tailles, probablement le même encodeur T5) : environ 9,5 Go ; les shards de transformer ont des tailles proches mais sont probablement différents.
- **Fichier incomplet** : `D:\AI\Musique\musicgen-small\.cache\...\*.incomplete` (2,4 Go).
- **Faux positifs probables** : les `ckpt.pt` de `creation_llm` de même taille sont des checkpoints d'expériences différentes, pas des copies. À ne pas toucher (entraînement en cours).

## État git des dépôts (risque de perte avant archivage)
Travail non poussé (modifications non commitées / commits non poussés) :
- CreaZik_V3 : 29 / 1 ; IA_Life : 48 / 2 ; LocalArenaAI : 41 / 1 ; BD_IA_V2 : 8 / 1 ; robert-ia : 5 / 2 ; Stop_Motion_IA : 4 / 1 ; Addict_IA : 1 / 1 ; IA-TSA : 0 / 1 ; IA_V7 : 0 / 1.
- ComfyUI-Qwen : 9 modifs, ComfyUI-SANA : 8 modifs (dépôts clonés de Comfy-Org/ComfyUI, modifications locales à identifier).

Sans dépôt distant ou sans git :
- `Flux` : git local, 19 modifications, aucun remote.
- `crea_zik` : aucun git. `Comparatif-Image`, `IA_Locales`, `IA_V6`, `TTS_Local`, `D:\AI` : aucun git.

Les modifications de creation_3d, creation_llm, creation_videos et WorldModel (4 à 6 chacune) correspondent à des sessions actives : à relire au moment de leur migration.

## Environnements virtuels (à recréer, jamais à déplacer)
`.venv` dans : ACE-Step-1.5, ComfyUI-Qwen, ComfyUI-SANA, creation_llm, IA_Life, LTX-Video, whisper, WorldModel ; `venv` dans Fine_Tuning, `backend\venv` dans robert-ia ; plusieurs venvs dans `crea_zik\benchmarks`, `TTS_Local` (chatterbox, kokoro), `D:\AI` (kimodo, MimicMotion, heartlib, TripoSR, WanGP) et `D:\tools\stable-fast-3d`. Versions de Python non relevées.

## Proposition de classement (hypothèses à confirmer)
Colonnes : module cible du portail, devenir proposé. « moteur » = installation tierce sous `engines/` ; « code » = ton code repris sous `modules/` ; « archive » = zip ou dépôt distant puis suppression en phase 12.

| Module | Éléments | Proposition |
|---|---|---|
| Image | ComfyUI-Qwen, ComfyUI-SANA, Flux, Comparatif-Image, `D:\Dev` (z_image, Qwen3-4B) | moteurs (ComfyUI) + poids vers `models/` ; Flux : code éventuel + dédoublonnage ; Comparatif-Image : archive |
| Musique | ACE-Step-1.5, CreaZik_V3, crea_zik, `D:\AI\Musique` (heartlib, musicgen), TTS_Local | ACE-Step : moteur ; CreaZik_V3 : code (phase 5) ; crea_zik et heartlib : à qualifier (anciennes versions ?) ; TTS_Local : hors modules listés, décision requise |
| Vidéo | creation_videos, LTX-Video, WanGP, MimicMotion, Stop_Motion_IA | creation_videos : code ; WanGP et LTX : moteurs ; MimicMotion : à qualifier (animation ?) |
| Chat | IA_V7, IA_V6, IA_Life, IA-TSA, Addict_IA, robert-ia, JarviX, LocalArenaAI | à qualifier un par un : portage déjà prévu pour IA_V7 ; les autres semblent des applications distinctes |
| 3D | creation_3d, TripoSR, stable-fast-3d, Hunyuan3D2 (IA_Locales), UniRig | creation_3d : code ; les autres : moteurs |
| Animation 3D | kimodo, UniRig | à qualifier avec creation_3d |
| WorldModel | WorldModel, poids oasis, diamond, Matrix-Game | code + poids |
| LLM | creation_llm, Fine_Tuning, Llama-3-8B, Mistral-7B, `D:\OllamaModels`, datasets | creation_llm en dernier ; Fine_Tuning (dernière activité 2025-12) à qualifier ; Ollama : un seul dossier de modèles |
| Hors périmètre probable | Caveman (dépôt tiers JuliusBrussee), whisper (outil de transcription), Labo, Recherches_IA, BD_IA_V2, Jeux_Codes_par_IA_Locales_Ollama | à ne pas migrer sauf avis contraire ; whisper et TTS posent la question d'un module « voix » |

## Contrôles complémentaires (2026-11-14)

### Doublon FLUX.1-dev : confirmé
Les caches Hugging Face de cette machine ont leurs dossiers `blobs` vides ; les fichiers sont directement dans `snapshots`. La comparaison par nom de blob est donc impossible. Comparaison octet par octet (`cmp`) du shard 3/3 du transformer (3,87 Go) entre `Flux\models_cache` et `HuggingFaceCache\hub` : identiques. Les autres fichiers de ce modèle portent le même identifiant de snapshot (3de623fc...) et les mêmes tailles : même contenu très probable, non comparé fichier par fichier. Gain : environ 31 Go. Le recoupement entre FLUX.1-dev et FLUX.1-schnell (text_encoder_2) n'a pas pu être tranché : à comparer par `cmp` avant tout dédoublonnage.

### CreaZik_V3 : ce que recouvre « le système d'apprentissage »
Lu : `README.md`, `DOCUMENTATION/APPRENTISSAGE.md`, en-tête de `OUTILS/apprentissage/calculer_preferences.py`. Ce n'est pas un entraînement de modèle, c'est un calcul de préférences à partir des votes de la radio (`webradio/votes.json`, 872 morceaux votés au 2026-10-11 selon la doc) et de règles par modèle (`regles_modeles.json`), relus par script avant chaque génération. Ils ne changent qu'avec l'accord de l'utilisateur.
Conséquence pour la phase 5 : la génération musicale pourrait vivre dans VertIA, mais les votes viennent de la webradio, qui reste dans CreaZik_V3. Le contrat d'API devra préciser où vit le calcul de préférences (côté CreaZik qui envoie des paramètres déjà résolus, ou côté VertIA qui reçoit les votes). Décision à prendre en phase 2. Le dépôt compte 864 fichiers suivis et aucun chemin `D:\` en dur dans le code lu par la recherche.

### Chemins `D:\` en dur dans le code
Recherche texte (fichiers hors json, jsonl, log ; hors `.venv`, `.git`, caches, modèles, sorties) de `D:\ServOMorph`, `D:\AI`, `D:\HuggingFaceCache`, `D:\OllamaModels`, `D:\Ollama` :

| Projet | Fichiers concernés |
|---|---|
| creation_videos | 25 |
| IA_Life, TTS_Local | 8 chacun |
| Flux, IA_V7 | 7 chacun |
| creation_3d, WorldModel | 6 chacun |
| creation_llm, LTX-Video | 4 chacun |
| ComfyUI-Qwen, ComfyUI-SANA, Stop_Motion_IA | 1 chacun |
| ACE-Step-1.5, CreaZik_V3, crea_zik, Fine_Tuning, whisper | 0 |

Hors recherche : fichiers de configuration JSON, chemins en notation autre (`/d/...`), variables d'environnement hors dépôt. Dans VertIA : `reprise.json` fixe `D:\ServOMorph\creation_llm` et le `.venv` de ce projet ; la tâche Windows `VertIA_reprise_auto` appelle `D:\ServOMorph\VertIA_v3\_orchestration\reprise_auto.py`. Ces deux points sont à mettre à jour à la migration de creation_llm (phase 11).

## Ce que cet inventaire ne couvre pas encore
- Contenu et rôle réels des projets autres que CreaZik_V3 : non lus.
- Empreintes des autres doublons (SANA, FLUX schnell), versions de Python des venvs, dernier usage réel de chaque projet.
- Hors périmètre de mesure : autres dossiers de `D:\ServOMorph` non listés (archives, BACKUPS, _sauvegardes, Capafy_AI, etc.), `D:\tmp` en détail, autres disques.

## Décisions attendues
1. Confirmer ou corriger la colonne « module / proposition » projet par projet, notamment les « à qualifier ».
2. ~~TTS_Local, whisper~~ : module voix retenu le 2026-11-14 (phase 5).
3. ~~`ACE-Step-1.5\output`~~ : réglé le 2026-11-14. CreaZik_V3 copie ses WAV hors de ce dossier (`ace_worker.py`) et ne le relit jamais ; il supprime lui-même ses WAV après conversion en MP3. Sur instruction de l'utilisateur (« supprime si CreaZik ne les utilise pas »), les 1 121 WAV (37,17 Go) ont été supprimés, liste conservée dans le scratchpad de session, dossier `creazik` vide conservé.
4. Les dépôts avec travail non poussé : pousser, archiver ou abandonner, avant toute suppression en phase 12.
