# VertIA

Studio d'intelligence artificielle **100 % locale**, pensé pour les personnes qui débutent. On discute avec un assistant qui prépare les demandes (images, musiques, vidéos), on valide, et tout tourne sur son propre ordinateur.

## État actuel (v0.6.0)
- Phase 7-bis codée, gate benchmark de la retouche dialoguée atteint (`benchmarks/retouche_gate/`), en attente de validation à l'écran : GPU réservé tant que l'interface est ouverte, design du chat repris d'IA_V7, capacité `image.analyser` (dialogue gemma4:12b puis repérage de zones qwen2.5vl) et outil « Retouche dialoguée » de l'Atelier (zones éditables, application zone par zone en calques).
- Portail (consolidation des projets d'IA locale, `roadmap_portail.md`, phases 1 à 7 faites) : modules découverts dans `modules/`, écran d'accueil par activité, API versionnée `/api/v1`, commande `vertia_gen.py <capacité>` pour les autres sessions (le portail démarre seul et prend le jeton GPU `vertia`), boucle demande / essai / retour avec livraison dans `outbox/`. Capacités : image (génération, retouche par masque), voix, musique, vidéo et chat ; l'Atelier est servi sous `/atelier/` ; `python vertia_gen.py capacites` donne la liste à jour.
- Atelier (`modules/atelier/`, `python run_atelier.py`, port 4320) : éditeur d'image local type Canva et Photoshop (calques, remplissage de scans, palette, pinceau, texte, formes, export PNG, projets) avec outil Retouche IA par masque ; interface à valider dans un navigateur (`tests_manuels.md`).
- Orchestration GPU entre sessions (`_orchestration/`) : jeton VRAM, reprise automatique et vérifiée de l'entraînement de creation_llm.
- Fondations v0.1.0 ci-dessous.
- Fondations : serveur FastAPI, interface à panneaux affichables/masquables (Discussion, Fichiers, Mémoire, Outils) avec préférences mémorisées, canal d'événements temps réel.
- Chat : client Ollama async, dossiers et instructions, conversations et titres automatiques issus du premier message, mode éphémère en mémoire, streaming Markdown, livrables à copier/télécharger, file de messages et Stop.
- Contexte : fenêtre par paires, garde de dépassement et calibrage par `prompt_eval_count`. Les résumés des échanges écartés sont calculés lorsque la file est vide ; une nouvelle demande les interrompt. Un résumé peut donc être différé jusqu'à une période d'inactivité.
- Ressources : RAM via psutil, VRAM via nvidia-smi, VRAM par PID via les compteurs Windows, modèles Ollama chargés. Le panneau Mémoire présente les jauges, déchargements ciblés et tâches GPU avec priorités, progression et annulation.
- Les réponses, résumés et générations d’images, de musique et de vidéo passent par la file SQLite et un arbitre GPU partagé. Les adaptateurs utilisent les installations ComfyUI et ACE-Step existantes. Les tests utilisent des moteurs simulés ; les validations réelles restent à effectuer.
- Images : routage léger, proposition JSON par le LLM, carte à modifier/valider/annuler, progression et aperçu du résultat. Aucun job image n’est créé avant validation. Édition avec une à trois images générées jointes ; la retouche par masque passe par l'Atelier (`image.retoucher`).
- Musique : préparation des paroles/caption par le Chat, carte modifiable, instrumental ou chant français/anglais, génération ACE-Step en MP3, lecteur et galerie. La qualité musicale et les performances attendent une validation réelle.
- Vidéo : Wan 2.2 TI2V-5B GGUF, texte ou image jointe vers MP4 muet court, carte modifiable et galerie ; performances et qualité à mesurer sur la machine.
- Fichiers : copie locale des nouveaux résultats, catalogue par conversation, aperçu image/audio/vidéo, ouverture, téléchargement, dossier Windows et pièces jointes par bouton ou glisser-déposer. Les lecteurs sont testés avec des données simulées.
- Accueil : guide de première utilisation, diagnostic local sans lancement, chemins et modèle configurables pour le prochain démarrage, récupération de la liste Ollama après indisponibilité.
- Ollama : service démarré automatiquement avec VertIA (instance existante réutilisée), préchargement du modèle par défaut via la file GPU dès que le service est disponible, badge de chargement puis des modèles chargés. Aucun téléchargement automatique.
- À venir : voir [roadmap_portail.md](roadmap_portail.md).

## Démarrer
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\python run.py
```
L'interface s'ouvre sur http://127.0.0.1:4310 ; le serveur se recharge automatiquement à chaque modification.

## Première utilisation
Ouvrir « Accueil et réglages », indiquer les installations existantes et vérifier les moteurs. Le diagnostic distingue fichiers présents et service joignable ; il ne garantit ni compatibilité ni génération. Il ne lance aucun moteur et ne télécharge pas de modèle. Image, musique et vidéo restent facultatives.

Les six réglages sont enregistrés dans `.vertia-local.json` (ignoré par Git), prioritaires sur `.env` au prochain démarrage. Arrêter puis relancer VertIA après modification ; les tâches actuelles conservent leurs réglages. Pour une installation utilisateur et le dépannage, suivre [MISE_EN_PROD.md](MISE_EN_PROD.md), qui contient aussi le plan d’installateur restant à réaliser. Ollama démarre automatiquement ; le badge indique sa disponibilité et la liste des modèles se met à jour à sa connexion.

## Tests
Guide d’extension et de vérification : [_docs/developpement.md](_docs/developpement.md).
Revue de consolidation : [_docs/revue_phase6.md](_docs/revue_phase6.md).

```powershell
.venv\Scripts\python -m pytest -q --basetemp=.tmp_tests
node --check src/vertia/static/js/chat.js
node --check src/vertia/static/js/markdown.js
node --check src/vertia/static/js/main.js
node --check src/vertia/static/js/resources.js
node --check src/vertia/static/js/actions.js
node --check src/vertia/static/js/files.js
```

Tests UI sans serveur et sans GPU : `npm install`, puis `npm run test:ui` (Microsoft Edge installé). Les routes et événements SSE sont simulés dans Playwright ; captures et téléchargement de contrôle dans `.tmp_ui/`. Le test peut utiliser une installation existante via `VERTIA_PLAYWRIGHT_MODULE`. Les vérifications avec Ollama réel restent listées dans `tests_manuels.md`.

Les conversations éphémères restent disponibles dans l'instance du serveur, y compris après un rechargement de la page ; elles disparaissent à l'arrêt du serveur. Stop interrompt la réponse courante et annule tous les messages en attente de cette discussion. Après un redémarrage, les messages persistés qui étaient en attente ou actifs sont marqués interrompus ; ils ne sont pas rejoués automatiquement.

## Ressources et jobs
Pour le même modèle Ollama déjà chargé avec le même contexte, le chat peut dépasser le seuil de chargement de 92 % si au moins 512 Mio et 3 % de la VRAM restent libres. La réserve est configurable via `VERTIA_RESIDENT_VRAM_RESERVE_MB`. Modèle différent, contexte différent ou métadonnées inconnues conservent le contrôle normal ; le seuil RAM reste toujours appliqué.
Les seuils `.env` `VERTIA_VRAM_LIMIT_PERCENT` (92) et `VERTIA_RAM_LIMIT_PERCENT` (90) sont contrôlés avant chaque appel GPU, après libération des autres moteurs. Un dépassement produit une erreur visible. Une mesure VRAM absente est signalée ; seul le contrôle RAM reste alors effectif. Chaque adaptateur déclare ses besoins connus ; avant un changement de moteur, Qwen réserve une marge RAM minimale de 17 000 Mo sous le seuil configuré pour son encodeur. Ce minimum exclut les autres allocations : ces contrôles ne garantissent pas l’absence de dépassement pendant une génération. Un moteur déjà actif est contrôlé sur son occupation courante, sans compter à nouveau sa marge de chargement.

`VERTIA_ENGINE_IDLE_SECONDS=300` libère les moteurs après cinq minutes sans utilisation, contrôlées toutes les cinq secondes ; `0` désactive cette libération. Le déchargement manuel refuse une tâche GPU active. Les modèles Ollama sont déchargés via son API. Le service démarre automatiquement avec VertIA ; seul le processus lancé par VertIA est arrêté à sa fermeture. `VERTIA_OLLAMA_AUTOSTART=false` désactive ce lancement ; `VERTIA_OLLAMA_EXECUTABLE` permet d’indiquer un chemin absolu d’installation.

La file conserve les 200 jobs les plus récents dans la vue (l'historique SQLite reste conservé). Une priorité élevée passe avant une priorité basse, sans interrompre un job actif. Au redémarrage, les jobs actifs deviennent interrompus et demandent une relance explicite ; les jobs en attente déclarés rejouables reprennent automatiquement si leur gestionnaire est enregistré. Les réponses et résumés Chat ne sont pas rejouables : renvoyer le message depuis la discussion. Le journal des jobs Chat ne stocke ni prompt ni réponse, y compris pour le mode éphémère.

Extension interne : enregistrer un gestionnaire async avec `services.jobs.register(type, handler)` avant le démarrage du worker, puis `submit(type, engine, payload, priority)`. Le gestionnaire reçoit `(payload, progress)` ; le payload doit être JSON et suffire à une reprise. L'appel `run(type, engine, operation)` attend une opération transitoire non rejouable. Les moteurs s'enregistrent dans l'arbitre avec `start()` et `free()` ; un échec de libération empêche le démarrage du suivant. API de suivi : `GET /api/ressources`, `GET /api/jobs`, `POST /api/ressources/liberer`, `PATCH /api/jobs/{id}`, `POST /api/jobs/{id}/annuler` et `/reprendre`. Les événements `ressources.maj`, `ressources.erreur` et `jobs.maj` utilisent le canal SSE existant.

## Cartes d’action et Qwen
Demander par exemple « Dessine une image de chat sur Mars ». Le filtre du module sélectionne les schémas utiles ; le LLM choisit ensuite une réponse ou une proposition d’action JSON. Une proposition mal formée, un outil inconnu ou des paramètres hors limites produisent un refus sans génération. Ce routage est un filtre lexical français/anglais, pas une classification exhaustive : une reformulation peut être nécessaire. Les 13 cas verrouillés dans `tests/test_tools.py` testent le filtre ; les décisions JSON du LLM sont simulées. La qualité réelle des prompts et des décisions n’a pas encore été mesurée.

La carte conserve prompt, dimensions, étapes et graine. La validation enregistre un job rejouable qui référence la carte ; une validation répétée est refusée. Les cartes éphémères et leurs paramètres restent en mémoire, leurs jobs sont non rejouables et leur journal ne contient aucun prompt. Les générations validées s’annulent depuis Mémoire. Une conversation ne peut pas être supprimée pendant un job image en attente ou actif. Les schémas sont comptés dans le budget du contexte et ne sont pas injectés dans les discussions ordinaires ; l’historique garde une référence courte à la carte, sans contenu de fichier.

`VERTIA_COMFY_DIR` et `VERTIA_COMFY_PORT` configurent l’installation existante. Aucun serveur n’est lancé au démarrage de VertIA : ComfyUI démarre lors du premier job image ou vidéo validé, avec un délai maximal de 600 secondes et les options `--lowvram --reserve-vram 1`. Une instance déjà active conserve ses propres options. VertIA vérifie le correctif GGUF par `git apply --reverse --check` ; s’il manque, l’utilisateur doit appliquer manuellement `correctifs/appliquer.bat` dans son installation. VertIA n’exécute pas ce script et ne réécrit pas les sources du moteur.

Utiliser une instance ComfyUI dédiée à VertIA : une file externe occupée bloque la libération et le changement de moteur. L’annulation supprime uniquement le prompt concerné et utilise `/interrupt` avec son identifiant ; elle attend sa sortie de la file. Un échec conserve le moteur bloqué jusqu’à une libération confirmée. `/free` est appelé lors des changements de moteur et de l’inactivité. Le processus lancé par VertIA est ensuite arrêté avec ses enfants ; un processus externe n’est jamais tué, et VertIA attend que sa mémoire PyTorch réservée descende à 64 Mio maximum avant de céder le GPU. Une mesure absente ou un délai dépassé bloque ce changement.

Les nouveaux résultats sont copiés dans `outputs/<conversation>/<identifiant>.<extension>` avant la fin du job. La table `fichiers` conserve type, MIME, taille, job source, carte, prompt et paramètres (références VertIA incluses). Les aperçus utilisent ensuite cette copie, même après arrêt de ComfyUI ou redémarrage de VertIA. Les anciennes cartes sans copie locale conservent leur aperçu `/view` avec repli en lecture seule dans les sorties ComfyUI ; elles ne sont pas importées automatiquement. Si la copie échoue, le job signale cette erreur et la carte conserve le résultat du moteur pour permettre sa récupération avant une nouvelle génération.

## Musique ACE-Step
Demander « Compose une chanson douce sur la mer, en français, 60 secondes » ou « Crée un instrumental ambient de 90 secondes ». Le Chat produit une carte `musique_ace` contenant demande, titre, caption anglais, paroles balisées, BPM, durée, langue, instrumental et graine. Aucun appel ACE-Step avant validation ; les paroles sont préparées pendant le job Ollama, sans appel LLM imbriqué dans le job musical. Les filtres français/anglais et les décisions JSON sont testés en simulation, pas avec le vrai modèle.

Le caption doit contenir 5 à 8 termes séparés par des virgules, sans tempo ni tonalité. Les paroles chantées exigent des sections non vides, au moins `[verse]` et `[chorus]`, des balises seules sur leur ligne et des refrains identiques. Le contrôle français refuse les lignes dépassant 12 syllabes estimées ; ce comptage reste approximatif, sans analyse phonétique. Le budget de paroles reprend l’heuristique CreaZik de 2,5 secondes par ligne et 3 secondes par section ; raccourcir les paroles ou augmenter la durée en cas de refus. La durée est limitée à 20–135 secondes, le tempo à 30–240 BPM et la langue chantée à français/anglais. Le schéma demande des textes originaux et un caption anglais ; ces qualités ne sont pas garanties par une validation linguistique automatique. Un instrumental impose des paroles vides et un caption indiquant `instrumental` ou `no vocals`. Une erreur de structure donne une consigne de correction sans afficher les valeurs reçues.

`VERTIA_ACESTEP_DIR` et `VERTIA_ACESTEP_PORT` configurent le dossier existant et le port (8001 par défaut). Au premier job validé, VertIA lance directement son Python avec `acestep/api_server.py`, sans script interactif, en mode turbo avec offload CPU, backend `pt` et LLM ACE désactivé. Le lancement attend au maximum dix minutes ; chaque génération attend au maximum quinze minutes. Paramètres fixes : un morceau, huit étapes, MP3, aucune reformulation interne et graine explicite. La file affiche l’acceptation à 5 %, les progrès numériques fournis par ACE (plafonnés à 95 %), puis la fin ; sans progrès numérique, la valeur reste à 5 % pendant l’attente. Les besoins mémoire sont déclarés inconnus en attendant les mesures : les seuils courants restent actifs, sans estimation fiable de la marge nécessaire.

ACE-Step ne propose pas de déchargement ni d’annulation par API. À l’annulation, à une erreur de génération, au changement de moteur, à l’inactivité ou à la fermeture, VertIA arrête uniquement le processus qu’il a lancé et ses enfants. Un enfant survivant bloque le prochain démarrage jusqu’à confirmation de son arrêt. Une instance ACE externe accessible bloque l’utilisation et le changement de moteur : l’arrêter manuellement, VertIA ne la tue pas. Consacrer cette instance à VertIA et ne pas y soumettre d’autres tâches.

Le MP3 est récupéré via `/v1/audio`, limité à 256 Mio, puis copié/catalogué par le stockage commun avant de rendre la file. Le lecteur de carte et la galerie utilisent ensuite la copie VertIA, disponible après arrêt d’ACE. Si la copie échoue, l’aperçu de secours `GET /api/actions/{id}/medias/{index}` dépend encore de l’instance ACE et de son fichier temporaire : récupérer le résultat avant son arrêt. Les cartes et copies éphémères restent en mémoire ; les sorties ACE peuvent subsister dans ses propres dossiers. La cover audio est indisponible : joindre un audio ne permet pas sa transformation.

## Vidéo Wan 2.2

Le modèle Wan 2.2 TI2V-5B GGUF Q4_K_M a été choisi par l’utilisateur le 2026-11-02. Demander « Crée une vidéo de la mer » ou joindre une image générée de la discussion puis « Anime cette image ». La carte `video_wan` propose sujet/mouvement, négatif, dimensions, nombre d’images, étapes et graine. L’image source unique est transférée à ComfyUI seulement après validation ; elle est ajustée et recadrée au format vidéo. Le mode texte n’accepte pas de référence. Une demande d’audio, de vidéo longue ou de plusieurs sources dépasse les capacités disponibles.

Défaut : 640×384, 49 images à 24 fps (environ deux secondes), 20 étapes ; sortie MP4 H.264 muette. Limites : dimensions multiples de 32 entre 256 et 960, surface maximale 960×544, 17 à 73 images de forme 4n+1, jusqu’à 30 étapes. Le graphe utilise uni_pc/simple, CFG 5, shift 8 et un VAE tuilé. Adaptation du [template officiel ComfyUI](https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/video_wan2_2_5B_ti2v.json), avec le chargeur GGUF et les modèles existants `Wan2.2-TI2V-5B-Q4_K_M.gguf`, `umt5_xxl_fp8_e4m3fn_scaled.safetensors`, `wan2.2_vae.safetensors`. Aucun téléchargement ni mise à jour automatique.

Qwen et Wan partagent le serveur, le suivi du prompt et l’identité `comfy` dans la file ; aucun deuxième processus vidéo n’est créé. Les seuils mémoire communs restent actifs, y compris la marge RAM minimale de Qwen au démarrage du serveur ; ce minimum conservateur n’est pas une mesure Wan. Le temps, le pic mémoire, la faisabilité sur 8 Go et la qualité attendent les tests réels dans `tests_manuels.md`. La génération attend au maximum 30 minutes ; sa progression reflète les étapes, puis l’encodage et la copie peuvent continuer avant 100 %.

La copie MP4 utilise le catalogue commun (256 Mio maximum), le lecteur de carte et la galerie. Après arrêt de ComfyUI, les copies persistantes restent accessibles avec téléchargement et requêtes partielles ; les médias éphémères sont servis intégralement depuis la mémoire. Sans copie locale, l’aperçu utilise `/view` puis la sortie ComfyUI en lecture seule si le serveur est inaccessible. Annulation, reprise, inactivité et refus d’un moteur occupé suivent les règles Qwen.

## Fichiers et pièces jointes
Le panneau Fichiers suit la discussion sélectionnée et les événements `fichiers.maj`. Les nouveaux fichiers apparaissent sans rechargement. « Ouvrir » affiche le média dans un autre onglet ; « Télécharger » fournit le fichier ; « Ouvrir le dossier » ouvre son dossier local sous Windows. Les chemins disque ne sont jamais acceptés par les routes. Les téléchargements persistants prennent en charge les requêtes partielles nécessaires aux lecteurs. Limite de stockage par résultat : 256 Mio ; image de référence Qwen : 32 Mio maximum.

« Utiliser dans le chat » ou un glisser-déposer sur le formulaire ajoute jusqu’à trois fichiers distincts, uniquement de cette discussion. Ils peuvent être retirés avant envoi ; changer de discussion efface la sélection. Le message transmis à Ollama contient seulement l’identifiant, le type et au plus 160 caractères du prompt d’origine, jamais les octets, un chemin local ou une image encodée. Joindre une image ne donne donc aucune capacité d’analyse visuelle au modèle Chat. Les références audio/vidéo sont disponibles pour les futurs outils ; elles ne déclenchent aucun moteur absent.

Pour modifier une image générée, la joindre et demander « Modifie cette image… ». Vérifier que la carte indique l’édition et les bons identifiants. Après validation, le job transfère les seules images choisies à `/upload/image` puis construit le graphe Qwen de référence. La résolution d’édition est calculée depuis l’image source (encodage Qwen 1024), les champs largeur/hauteur sont désactivés dans la carte d’édition. Aucun transfert ni appel GPU ne précède la validation. Les références importées restent dans le dossier d’entrée ComfyUI ; VertIA ne supprime pas les fichiers de ce moteur.

En discussion éphémère, catalogue et octets des copies restent en mémoire, sans écriture dans SQLite ni dans `outputs`. Ils disparaissent à la suppression de la discussion ou à l’arrêt du serveur ; les sorties et références déjà transférées à ComfyUI peuvent rester dans ses propres dossiers. Télécharger les fichiers à conserver. La suppression d’une discussion persistante supprime ses fichiers catalogués VertIA ; elle refuse les jobs en attente/actifs et conserve les fichiers étrangers au catalogue.

Extension : un outil peut exposer `artifacts(result)` async et retourner une liste de couples `(octets, MIME)` ; le stockage commun se charge du catalogue et des événements, sans connaître son moteur. Formats autorisés : PNG, JPEG, WebP, MP3, WAV, OGG, MP4 et WebM. API : `GET /api/conversations/{id}/fichiers`, `GET /api/fichiers/{id}/contenu` (paramètre `telecharger=true`), `POST /api/fichiers/{id}/dossier`. `POST /api/conversations/{id}/messages` accepte `fichiers: [identifiants]` en plus de `contenu`.

Les tests Python vérifient les octets, les en-têtes et les téléchargements partiels. Edge vérifie le déclenchement du lien et le nom proposé ; son téléchargement HTTP intercepté est annulé dans le montage sans serveur. Le téléchargement réel, les codecs audio/vidéo et l’ouverture de l’Explorateur restent dans les contrôles manuels.

Pour ajouter une IA, implémenter le protocole `engines/base.py` (cycle de vie, santé et `MemoryNeeds`) et `tools/base.py` (nom, description, schéma compact, filtre `matches`, validation et exécution). Enregistrer les modules dans `build_services`, point d’assemblage ; le registre vérifie les doublons et le moteur, l’orchestrateur ne connaît aucun outil particulier. Les extensions et leurs clients se substituent dans les tests via `overrides`. API : `GET /api/outils`, cartes dans `GET /api/conversations/{id}`, `PATCH /api/actions/{id}`, `POST /api/actions/{id}/valider` ou `/annuler`, et `GET /api/actions/{id}/images/{index}`. Les événements `actions.maj` partagent le canal SSE.

## Documentation
- [Architecture](_docs/architecture.md)
- [Mise en production](MISE_EN_PROD.md)
- [Recherche vidéo locale](_docs/benchmark_video.md)

## Licence
MIT
