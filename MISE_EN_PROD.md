# Installation utilisateur — VertIA

État au 2026-11-02 : application intégrée et tests simulés exécutés. Installation sur une autre machine, générations, qualité et consommation réelles restent à valider dans `tests_manuels.md`. Aucun installateur n’est livré à ce stade.

## Préparer l’ordinateur

- Windows avec Python 3.11 ou supérieur, Git (nécessaire au contrôle du correctif ComfyUI), navigateur Edge et pilote NVIDIA adapté aux moteurs installés.
- Ollama installé, avec un modèle de chat déjà téléchargé. VertIA démarre son service automatiquement. Défaut : `gemma4:12b` ; choisir un autre modèle présent si nécessaire. VertIA ne télécharge pas de modèle.
- Image et vidéo facultatives : installation ComfyUI compatible avec les graphes du projet, son environnement `.venv`, ComfyUI-GGUF et le correctif Qwen appliqué par l’utilisateur. Un ComfyUI standard ne suffit pas nécessairement.
- Musique facultative : installation ACE-Step 1.5, environnement `.venv`, modèle turbo, VAE et encodeur de texte opérationnels. Le LLM interne ACE n’est pas utilisé.
- Prévoir de l’espace pour les environnements, poids, résultats et sauvegardes. Aucun volume minimum fiable n’a été mesuré. Les 8 Go de VRAM visés pour la vidéo restent à tester, sans garantie matérielle. Qwen déclare déjà 17 000 Mo de RAM pour son seul encodeur.

Les moteurs restent dans des dossiers séparés de VertIA. Vérifier leurs dépendances avec leur propre procédure ; ce dépôt ne contient ni leurs environnements ni leurs poids. Les noms ci-dessous sont imposés par les graphes actuels.

## Installer et lancer

Décompresser la version fournie dans un dossier accessible en écriture, de préférence sur D: si disponible, par exemple `D:\Applications\VertIA`. Dans PowerShell ouvert dans ce dossier :

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python run.py --no-reload
```

Ne pas recopier `.env.example` sur un `.env` déjà adapté. L’installation des dépendances nécessite un accès aux paquets ; les moteurs locaux avec leurs modèles déjà présents peuvent ensuite fonctionner sans téléchargement par VertIA. Node et `requirements-dev.txt` servent aux tests de développement.

Le navigateur s’ouvre sur `http://127.0.0.1:4310`. `--no-browser` laisse le navigateur fermé. Conserver la fenêtre PowerShell : `Ctrl+C` arrête VertIA. Le rechargement automatique, actif sans `--no-reload`, est destiné au développement et interrompt tâches et sessions éphémères lors des redémarrages.

## Premier accueil

1. « Accueil et réglages » apparaît automatiquement tant que « Accéder à la discussion » n’a pas été utilisé. Échap ferme aussi la fenêtre, sans mémoriser la fin de l’accueil.
2. Déplier « Chemins et modèle de chat ». Indiquer l’adresse HTTP locale Ollama, un modèle installé, les chemins absolus ComfyUI/ACE et leurs ports. Un dossier facultatif absent n’empêche pas le chat.
3. « Vérifier les moteurs » examine les valeurs affichées, même avant sauvegarde. Le diagnostic utilise seulement des lectures disque et trois requêtes GET locales, sans charger de modèle, lancer de moteur ni télécharger.
4. « Joignable » signifie une réponse HTTP reconnue. « Fichiers attendus présents » indique seulement l’existence des chemins : aucun contrôle des octets, versions, dépendances, correctifs ou besoins mémoire. Un moteur arrêté peut être bien installé.
5. Enregistrer, arrêter VertIA avec `Ctrl+C`, puis relancer la même commande. Les tâches gardent leur configuration précédente jusqu’au redémarrage. Fermer l’accueil avec « Accéder à la discussion ».
6. Attendre que le badge Ollama indique « disponible » : la liste des modèles se met à jour automatiquement. Le choix concerne les nouvelles discussions ; une discussion existante garde son modèle.

Le bouton « Accéder à la discussion » ferme immédiatement l’accueil. Si la préférence ne peut pas être enregistrée, un avertissement s’affiche dans Discussion, sans bloquer la saisie. Après une mise à jour, redémarrer VertIA puis faire `Ctrl+F5` dans le navigateur pour recharger l’interface.

Pour démarrer le chat : lancer VertIA. Le service Ollama existant est réutilisé ; s’il ne répond pas, VertIA cherche `ollama` dans le PATH puis dans `%LOCALAPPDATA%/Programs/Ollama/ollama.exe` et lance `ollama serve` en arrière-plan. Le badge en haut indique démarrage, disponibilité ou erreur, puis les modèles chargés (mesurés via `/api/ps`, environ toutes les trois secondes). Le modèle défini dans Accueil et réglages est préchargé une seule fois dès que le service est disponible, via la file GPU et ses garde-fous mémoire. Le badge indique l’attente, le chargement puis le nom du modèle chargé. Un modèle absent produit une erreur sans téléchargement. Après déchargement manuel, inactivité ou utilisation d’un autre moteur, le modèle sera rechargé à la prochaine demande. La liste des modèles s’actualise quand Ollama devient disponible ; sélectionner le modèle, cliquer « Nouvelle discussion », écrire et envoyer. L’adresse habituelle est `http://127.0.0.1:11434`. Références : https://docs.ollama.com/windows et https://docs.ollama.com/cli.

Le démarrage reste borné à 30 secondes et ne bloque pas l’interface. Si Ollama est introuvable, définir `VERTIA_OLLAMA_EXECUTABLE` avec le chemin absolu de son exécutable installé, puis relancer VertIA ; `VERTIA_OLLAMA_AUTOSTART=false` désactive le démarrage automatique. Les nouvelles instances utilisent l’adresse/port HTTP local configuré et héritent notamment de `OLLAMA_MODELS`. Une adresse distante ou un port répondant comme un autre service ne déclenche aucun lancement. À l’arrêt de VertIA, seul l’arbre du service qu’il a lancé est arrêté ; une instance déjà présente est conservée. Le diagnostic manuel de l’accueil reste en lecture seule ; le lancement automatique appartient au démarrage de VertIA.

Le panneau gauche regroupe les dossiers dépliables et les discussions. Le menu … permet de renommer, épingler/désépingler, déplacer et supprimer avec confirmation ; supprimer un dossier conserve ses discussions sans dossier. Glisser les éléments pour changer leur ordre, déposer une discussion sur un dossier pour l’y déplacer, ou sur « Sans dossier » pour l’en sortir. Les commandes Monter/Descendre et la sélection de destination offrent une alternative au clavier. Les éléments épinglés précèdent les autres et se réordonnent entre eux. L’ordre et l’épinglage persistent au redémarrage ; les discussions éphémères restent uniquement en mémoire.

L’assistant accepte Ollama en HTTP sur `localhost`, `127.0.0.1` ou `::1`, sans identifiants ni chemin d’API. ComfyUI et ACE sont joints sur `127.0.0.1`. Garder VertIA sur `127.0.0.1` : l’interface ne comporte pas d’authentification et n’est pas préparée pour une exposition réseau.

## Fichiers et ports attendus

| Service | Port par défaut | Contrôle sans génération |
|---|---|---|
| VertIA | 4310 | `/api/sante`, badge « en ligne » : connexion à VertIA seulement |
| Ollama | 11434 | `/api/tags`, présence du nom de modèle choisi |
| ComfyUI | 8189 | `/system_stats`, fichiers ci-dessous |
| ACE-Step | 8001 | `/health`, lanceur et marqueur de configuration turbo |

VertIA, ComfyUI et ACE doivent utiliser des ports différents. Une réponse d’un autre service n’est pas un diagnostic positif. Une réponse locale ne prouve pas que la génération fonctionne.

Chemins relatifs au dossier ComfyUI configuré :

| Fonction | Fichiers nécessaires |
|---|---|
| Installation | `.venv/Scripts/python.exe`, `main.py`, `custom_nodes/ComfyUI-GGUF/nodes.py` |
| Image Qwen | `models/unet/qwen-image-2.1-Q4_K_M.gguf`, `models/text_encoders/qwen3vl_8b_bf16.safetensors`, `models/vae/qwen_image_2.1_vae_bf16.safetensors` |
| Vidéo Wan | `models/unet/Wan2.2-TI2V-5B-Q4_K_M.gguf`, `models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors`, `models/vae/wan2.2_vae.safetensors` |

Les poids placés dans des répertoires alternatifs ComfyUI ne sont pas détectés par cette vérification de chemins fixes. Les nœuds TextEncodeQwenImage21, Wan22ImageToVideoLatent, CreateVideo et SaveVideo MP4 H.264 sont également nécessaires ; le diagnostic ne vérifie pas leurs contrats. Si le correctif manque, appliquer manuellement `correctifs/appliquer.bat` depuis l’installation compatible ; VertIA effectue seulement un contrôle Git en lecture seule avant son lancement.

ACE doit contenir `.venv/Scripts/python.exe`, `acestep/api_server.py` et une installation complète de ses modèles. L’assistant détecte uniquement le marqueur `checkpoints/acestep-v15-turbo/config.json` pour le checkpoint ; il ne vérifie pas ses poids ni les dépendances VAE/encodeur.

## Configuration et stockage

L’assistant enregistre `.vertia-local.json` à la racine de VertIA, par remplacement atomique. Ce fichier ignoré par Git contient uniquement les six réglages affichés. Au démarrage, il prend priorité sur les mêmes valeurs de `.env` et de l’environnement. Pour revenir à `.env`, arrêter VertIA puis renommer ce fichier. Une configuration locale illisible bloque le démarrage avec une indication de correction/renommage.

Les autres réglages restent dans `.env` :

| Variables | Usage |
|---|---|
| `VERTIA_HOST`, `VERTIA_PORT` | Écoute VertIA, défaut local 4310 |
| `VERTIA_DATA_DIR`, `VERTIA_DATABASE`, `VERTIA_OUTPUTS_DIR` | Base/préférences et fichiers générés ; chemins relatifs à la racine VertIA |
| `VERTIA_NUM_CTX` | Taille de contexte du chat, défaut 16384 |
| `VERTIA_VRAM_LIMIT_PERCENT`, `VERTIA_RAM_LIMIT_PERCENT` | Seuils avant travail GPU, défauts 92 et 90 ; aucune garantie contre un dépassement pendant le calcul |
| `VERTIA_RESIDENT_VRAM_RESERVE_MB` | Réserve VRAM pour réutiliser le même modèle/contexte déjà chargé : 512 Mio par défaut, minimum 128 ; au moins 3 % de chaque GPU restent libres |
| `VERTIA_ENGINE_IDLE_SECONDS` | Libération après inactivité, défaut 300 ; 0 la désactive |
| `OLLAMA_URL`, `VERTIA_DEFAULT_MODEL` | Chat initial, remplacé par l’assistant s’il a enregistré sa configuration |
| `VERTIA_OLLAMA_AUTOSTART`, `VERTIA_OLLAMA_EXECUTABLE` | Démarrage du service activé par défaut ; chemin absolu facultatif de l’exécutable installé |
| `VERTIA_COMFY_DIR`, `VERTIA_COMFY_PORT`, `VERTIA_ACESTEP_DIR`, `VERTIA_ACESTEP_PORT` | Dossiers/ports initiaux, remplacés par l’assistant s’il a enregistré sa configuration |

Éviter aussi les ports Ollama/ComfyUI/ACE identiques. Une variable déjà définie dans l’environnement prime sur `.env`, avant application du fichier de l’assistant. Ne pas ajouter de secrets dans ces réglages.

La base SQLite est `data/vertia.db` par défaut. Les nouveaux médias persistants sont copiés dans `outputs/<conversation>/`. Les moteurs conservent aussi leurs propres résultats. Le mode éphémère garde échanges et copies VertIA en mémoire jusqu’à l’arrêt ; il n’efface pas les sorties des moteurs externes. Télécharger ce qui doit être conservé avant l’arrêt.

## Portail, Atelier et ligne de commande (v0.3.0)

- **Chemins** : `config/chemins.toml` (ignoré par Git, modèle `config/chemins.example.toml`) donne les dossiers des moteurs (`[moteurs] comfyui, acestep`) et des données (`[dossiers] models, outputs, outbox, inbox, data`) ; sans fichier, les défauts sont `engines/`, `models/`, `outputs/`, `outbox/`, `inbox/` sous la racine. Priorité : défauts, `chemins.toml`, `.env`, `.vertia-local.json`.
- **Poids ComfyUI** : les dossiers `unet`, `text_encoders`, `vae` et `checkpoints` de ComfyUI-Qwen ont été déplacés vers `models/comfy/` avec une jonction Windows à l'ancien emplacement (`outils/deplacer_poids.py`, journal `models/_deplacements.jsonl`). Retour arrière : `python outils/deplacer_poids.py retour <id> --appliquer`.
- **Commande pour les autres sessions** : `python vertia_gen.py <capacité> --session <nom> --prompt "..."` démarre seule le portail (`run.py --headless`, sans navigateur, sans préchargement Ollama), attend la livraison dans `outbox/` et affiche le chemin du fichier. `python vertia_gen.py capacites` liste les capacités ; codes de sortie dans `_docs/architecture_portail.md` (section 5).
- **Verrou GPU** : le portail prend le jeton `vertia` de `_orchestration/vram_lock.py` avant tout moteur GPU et le rend après inactivité ; l'entraînement de creation_llm se met en pause puis reprend seul.
- **Atelier** : `python run_atelier.py` (port 4320, `--sans-navigateur` possible), projets dans `outputs/atelier/`. Dépendances ajoutées à `requirements.txt` : `pillow`, `psutil`. La retouche IA dépose les images dans `inbox/` et lance `vertia_gen.py image.retoucher`.
- **Nouvelles variables** :

| Variables | Usage |
|---|---|
| `VERTIA_VERROU_GPU` | Verrou GPU du portail, actif par défaut ; `0` le coupe |
| `VERTIA_VERROU_GPU_ATTENTE_S` | Attente maximale du jeton en secondes, défaut 600 |
| `VERTIA_PRELOAD_OLLAMA` | Préchargement du modèle de chat au démarrage, actif par défaut ; coupé en mode `--headless` |
| `VERTIA_RESERVER_GPU_UI` | Garde le jeton GPU tant qu'un client de l'interface est connecté et le rend 30 s après la fermeture, actif par défaut ; `0` le coupe |
| `ATELIER_PORT`, `ATELIER_INBOX`, `ATELIER_VERTIA_GEN` | Port de l'Atelier (4320), dossier de dépôt des images à retoucher, script de génération (tests) |

- **Journaux** : `data/logs/comfy_qwen.log` (sortie de ComfyUI lancé par le portail, remplacée à chaque démarrage) et `data/logs/<moteur>_<nom>.log` des travailleurs ; les échecs de demande sont tracés par le journal du serveur (`vertia.demandes`).
- **Vérification** : `python vertia_gen.py capacites` (le portail démarre seul), puis une génération `image` courte ; relever que `vram_lock.py status` montre le jeton `vertia` pendant le travail et que creation_llm repart ensuite.

## Contrôle après installation

Le seuil de 92 % reste appliqué au chargement d’un modèle. Pour un modèle Ollama déjà chargé avec exactement le contexte demandé (confirmé par `/api/ps`, un seul modèle GPU présent), le chat utilise une réserve libre de 512 Mio minimum et 3 % de la VRAM, plutôt que de refuser son occupation existante. Le contrôle RAM est conservé. Si cette réserve manque ou si les métadonnées ne permettent pas de vérifier la réutilisation, la requête est refusée avec une explication. Les allocations supplémentaires pendant le calcul restent dépendantes du modèle.

- Tester un message simple, la réponse progressive et Stop. Puis demander une image, relire et valider sa carte. Tester musique/vidéo seulement si ces outils sont installés.
- Une génération de fichier attend la validation de sa carte. Une seule tâche GPU s’exécute à la fois ; Mémoire affiche attente, progression, annulation et erreurs.
- ComfyUI est partagé entre image et vidéo. VertIA le lance à la demande avec `--lowvram --reserve-vram 1`. Une instance externe garde ses options ; utiliser une instance dédiée, sans tâches concurrentes.
- ACE doit être lancé par VertIA ; arrêter une instance démarrée séparément avant de créer une musique. Ollama est réutilisé ou démarré automatiquement ; seul le processus lancé par VertIA peut être arrêté par lui, jamais d’arrêt global.
- Tester lecture/téléchargement, fermeture/redémarrage et persistance. Le badge et le diagnostic ne remplacent pas les contrôles réels de `tests_manuels.md`.

## Dépannage

| Symptôme | Action |
|---|---|
| Le navigateur ne s’ouvre pas | Ouvrir l’URL indiquée dans PowerShell ; lire l’erreur de lancement éventuelle |
| Port VertIA occupé | Le lanceur refuse désormais le démarrage avant d’ouvrir le navigateur. Arrêter l’ancienne instance ou changer `VERTIA_PORT`, puis relancer ; identifier le processus avant de l’arrêter |
| Not Found sur réglages, modèles ou état Ollama | Une ancienne instance peut servir l’interface actuelle avec une API obsolète. Arrêter cette instance, relancer le `run.py` actuel puis Ctrl+F5 ; le rechargement du navigateur seul ne remplace pas le serveur |
| Ollama ne répond pas / modèle absent | Lire le badge Ollama, vérifier l’adresse/port ou `VERTIA_OLLAMA_EXECUTABLE`, puis relancer VertIA. Installer un modèle dans Ollama ou choisir un modèle présent si nécessaire |
| Installation/fichier manquant | Corriger le dossier absolu et consulter le détail ; installer les éléments avec la procédure du moteur |
| Nœud/correctif ComfyUI absent | Vérifier l’installation compatible et ses correctifs ; le diagnostic disque ne les valide pas |
| ACE externe / file ComfyUI occupée | Attendre ou arrêter manuellement l’instance externe concernée |
| Mémoire insuffisante | Fermer les autres applications GPU, consulter Mémoire, réduire la demande ou choisir un modèle de chat plus petit déjà installé |
| Échec après un délai | Lire l’erreur du job et vérifier le moteur ; démarrage jusqu’à dix minutes, génération musique quinze, vidéo trente |
| Enregistrement impossible | Vérifier droits et espace disque ; les réglages précédents restent conservés |
| Réglages sans effet | Arrêter puis relancer le processus VertIA ; recharger la page ne suffit pas |
| Échec de copie du résultat | Télécharger le média de secours avant nettoyage externe ; vérifier l’accès aux sorties VertIA |

## Sauvegarde, mise à jour et retrait

Arrêter VertIA avant sauvegarde. Conserver ensemble la base et ses éventuels fichiers SQLite associés, les sorties, `.env` et `.vertia-local.json` ; tenir compte des chemins personnalisés. Sauvegarder séparément les modèles/configurations externes.

Avant mise à jour, garder une copie du code et des données. Installer le nouveau code et ses dépendances, conserver la configuration, relancer puis vérifier. Les migrations SQLite vont vers l’avant : pour revenir à une ancienne version, restaurer **aussi** sa sauvegarde de base et de sorties, pas seulement le code. Aucune migration descendante automatique.

Pour retirer VertIA, arrêter son processus et retirer son dossier après sauvegarde. Ollama/ComfyUI/ACE et leurs sorties sont distincts et restent sous la responsabilité de l’utilisateur.

## Plan d’installateur — à réaliser avant diffusion

1. Figer les versions Python/dépendances réellement testées. Produire une archive reproductible avec manifeste, empreintes et licences ; exclure environnements, données, sorties, secrets et chemins locaux du développeur.
2. Valider les licences des composants et poids avant redistribution. Décider si les moteurs seront installés séparément ou fournis en paquets compatibles ; aucun droit de redistribution n’est supposé ici.
3. Proposer un dossier accessible en écriture, préférer D: s’il existe, installer le runtime isolé, créer un raccourci `run.py --no-reload`. Limiter les droits administrateur aux prérequis justifiés.
4. Guider vers l’installation des moteurs et l’obtention consentie des modèles ; afficher tailles, provenance, licences et stockage avant téléchargement. Préserver les installations externes existantes.
5. Ajouter journal de lancement lisible, sélection d’un port disponible, mise à jour avec sauvegarde/restauration, retrait conservant par défaut données et modèles.
6. Tester sur une machine Windows distincte : chemins avec espaces/accents, D: absent, droits limités, ports occupés, installation partielle, usage sans réseau après installation, arrêt forcé, disque plein, mise à jour et retour arrière.

Ce plan ne constitue pas un installateur exécuté. Les validations matérielles et de redistribution doivent précéder une annonce de compatibilité ou une diffusion des moteurs.

## Journal
- 2026-11-20 v0.5.0 : variable `VERTIA_RESERVER_GPU_UI` (GPU gardé pendant l'ouverture de l'UI), capacité `image.analyser` (gemma4:12b et qwen2.5vl via Ollama, aucun nouveau poids hors ces deux modèles à avoir dans Ollama), routes `/api/analyse` de l'Atelier.
- 2026-11-19 v0.4.0 : modules voix, musique, vidéo, chat et Atelier dans le portail ; verrou GPU compatible avec le serveur à rechargement ; sortie de ComfyUI conservée dans `data/logs/comfy_qwen.log`.
- 2026-11-16 v0.3.0 : portail (config/chemins.toml, vertia_gen.py, API v1, verrou GPU, modules image et Atelier), poids ComfyUI-Qwen déplacés vers `models/comfy/` avec jonctions, dépendances `pillow` et `psutil`, nouvelles variables d'environnement.
