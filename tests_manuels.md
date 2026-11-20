# Tests manuels en attente

## Interface inspirée de Codex et copie des messages
Validation Edge simulée sur bureau et mobile ; validation sur l’instance utilisateur encore nécessaire.
1. Vérifier Nouveau chat, Épinglés et Projets, dossiers dépliables, conversations indentées, sélection active, Afficher plus au-delà de cinq conversations ; garder épinglage, renommage, suppression et déplacements fonctionnels.
2. Vérifier bulles utilisateur à droite, réponses assistant, saisie basse et sélection du modèle. Copier un message utilisateur puis assistant : texte exact, Markdown brut conservé, Unicode, réponse partielle et arrêtée. Tester changement de discussion et refus du presse-papiers.
3. Sur petit écran, vérifier l’accès à toute la navigation et au formulaire, l’envoi effectif et les cartes image/musique/vidéo ; pas de débordement horizontal ni de commandes inaccessibles.
4. Dans la saisie du message, vérifier Entrée pour envoyer et Maj+Entrée pour ajouter une ligne. Vérifier absence de doublon lors d’un maintien de touche et absence d’envoi pendant la composition IME ; les autres zones de texte gardent leur comportement habituel.

## Chat avec modèle déjà résident et VRAM proche du seuil
Validation automatisée avec modèle simulé ; aucun calcul GPU réel lancé par Codex.
1. Après préchargement du modèle configuré, avec VRAM au-dessus de 92 % mais au moins 512 Mio et 3 % libres, envoyer un message : réponse attendue si `/api/ps` confirme le même modèle et le même contexte. Tester aussi un résumé. Relever les pics VRAM pendant le calcul.
2. Avec une réserve libre inférieure à 512 Mio, vérifier le refus « VRAM presque saturée » avant génération. Ne pas saturer artificiellement une session contenant des travaux à conserver. Vérifier que la limite RAM reste appliquée.
3. Tester autre modèle, autre contexte et état Ollama inconnu : aucune exception au seuil normal. Décharger/recharger, alterner avec image/musique/vidéo : mêmes protections, exclusivité GPU et échantillon frais. Vérifier l’affichage des PID et VRAM dans Mémoire (compteur CIM `Name`).

## Préchargement du modèle Ollama au démarrage
Tests avec modèle et moteurs simulés uniquement ; aucun chargement réel lancé par Codex.
1. Définir un modèle installé dans Accueil et réglages puis redémarrer VertIA : vérifier la tâche `prechargement_ollama`, les états attente/chargement puis le nom du modèle chargé avant tout message. Comparer le délai du premier message et confirmer que le modèle et `num_ctx` correspondent au réglage.
2. Tester modèle absent et mémoire insuffisante : message explicite, interface utilisable, aucun téléchargement. Pendant le préchargement, envoyer un message et vérifier l’exécution exclusive via la file. Annuler : la libération du GPU doit attendre la fin du chargement puis son déchargement ; aucun moteur suivant avant cette fin.
3. Tester arrêt de VertIA pendant l’attente/le chargement, redémarrage avec ancienne tâche interrompue (une seule nouvelle tâche), service Ollama disponible après retard, déchargement manuel/inactivité puis image/musique/vidéo. Le modèle ne doit pas se recharger automatiquement après ces déchargements ; il sera rechargé par la demande suivante.

## Ancienne instance encore active sur le port VertIA
Diagnostic réel du 2026-11-03 : le port 4310 était servi par le PID 37100 lancé le 2026-10-31 ; son OpenAPI n’exposait que les fondations et les nouvelles API renvoyaient 404. Aucun processus arrêté par Codex.
1. Arrêter l’ancienne instance dans son terminal (Ctrl+C), relancer le `run.py` actuel puis Ctrl+F5. Vérifier les API `/api/installation`, `/api/ollama/etat` et le badge en ligne ; `/api/modeles` doit répondre avec la liste ou une erreur Ollama explicite, sans 404 de route.
2. Avec VertIA déjà actif, lancer une seconde fois `run.py` : il doit refuser le port occupé avec une explication, sans ouvrir le navigateur ni démarrer de seconde instance. Ne pas arrêter automatiquement un processus occupant ce port.

## Démarrage automatique Ollama et badge d’état
Validation automatisée avec HTTP et processus simulés uniquement ; aucun service ni modèle lancé par Codex.
Régression Windows du 2026-11-07 : exécutable détecté dans D:\Ollama ; contrôle réel du port fermé : ConnectTimeout à deux secondes, ConnectError après environ 2,04 secondes avec un délai de cinq secondes. Après redémarrage de VertIA corrigé, vérifier que cette situation déclenche le lancement automatique et que le badge devient disponible. Le lancement réel reste à valider par l’utilisateur.
1. Ollama arrêté et installé : lancer uniquement VertIA, vérifier le démarrage caché d’une seule instance, le badge « démarrage » puis « disponible », l’actualisation automatique des modèles et le préchargement du modèle par défaut avant le premier message. Après déchargement/inactivité, le badge doit revenir à la liste vide.
2. Ollama déjà ouvert : vérifier la réutilisation sans seconde instance et sa conservation à l’arrêt de VertIA. Pour le service lancé par VertIA, confirmer au contraire l’arrêt de son arbre à la fermeture ; aucun arrêt global d’autres Ollama/processus.
3. Tester installation personnalisée via `VERTIA_OLLAMA_EXECUTABLE`, PATH absent et installation Windows standard, exécutable absent, droits d’exécution refusés, port occupé par un autre service, démarrage lent/échoué, `VERTIA_OLLAMA_AUTOSTART=false`. Vérifier une erreur lisible et une interface utilisable. Vérifier l’adresse/port local configuré et l’héritage de `OLLAMA_MODELS` sans nouveau téléchargement.
4. Vérifier modèles chargés inconnus si `/api/ps` échoue, reprise du badge lorsque le service redevient joignable, état inconnu si VertIA perd sa connexion, affichage sur petit écran et actualisation au retour SSE. Vérifier qu’un diagnostic manuel ne lance rien lui-même, puis l’alternance Ollama → Qwen/ACE/Wan : aucun modèle ne doit être préchargé hors file GPU.

## Navigation latérale et accès à la discussion
Tests API et Edge simulés uniquement ; aucune base utilisateur modifiée par Codex.
1. Redémarrer VertIA puis recharger avec Ctrl+F5. Dans Accueil et réglages, cliquer « Accéder à la discussion » : fermeture immédiate, discussion visible et saisie focalisée. Réessayer avec erreur réseau sur l’enregistrement de l’accueil : avertissement visible et interface accessible ; lors d’une nouvelle réussite, l’avertissement disparaît.
2. Vérifier conservation des anciennes discussions après la migration, création et renommage de dossiers et discussions, épinglage/désépinglage et ordre après redémarrage. Déplier/replier les dossiers, ouvrir une discussion, créer « Nouvelle discussion ici ». Confirmer le bon modèle et le bon dossier lors de l’envoi.
3. Glisser des dossiers entre eux, des discussions entre elles et vers un autre dossier ; déposer sur « Sans dossier » pour sortir une discussion. Refaire au clavier avec les menus …, la sélection de destination et Monter/Descendre. Les éléments épinglés restent avant les autres ; l’ordre se modifie dans un même groupe d’épinglage. Vérifier les petits écrans et les titres longs.
4. Supprimer uniquement une discussion de test et ses fichiers après confirmation. Supprimer un dossier de test contenant des discussions : celles-ci doivent rester sans dossier. Avec une tâche réelle active, vérifier le refus du déplacement ou de la suppression concernés. Une discussion éphémère et son épinglage disparaissent au redémarrage.
5. Lancer uniquement VertIA, attendre le badge Ollama disponible et l’actualisation automatique des modèles, puis envoyer un premier message dans une nouvelle discussion. Vérifier le cas service arrêté et nom de modèle absent ; se référer aux tests de démarrage automatique ci-dessus.

## Phase 8 — Première installation et prise en main réelles
Aucun serveur ni moteur lancé par Codex ; diagnostic, API et interface testés uniquement en simulation.
1. Sur une machine Windows distincte et un dossier accessible en écriture, suivre `MISE_EN_PROD.md` avec chemins comportant espaces/accents, puis sans lecteur D:. Vérifier les prérequis et erreurs de lancement lisibles. Aucun installateur livré : son plan reste à réaliser avant distribution.
2. Vérifier accueil automatique, navigation clavier/Échap, fermeture mémorisée, réouverture et défilement sur petit écran. Un utilisateur novice doit pouvoir choisir son modèle, comprendre carte/validation, file GPU et galerie à partir des aides affichées.
3. Vérifier le diagnostic avec Ollama ouvert/fermé, modèle choisi absent, ComfyUI/ACE arrêtés ou partiellement installés, port occupé par un autre service. Confirmer qu’aucun processus moteur, chargement GPU ni téléchargement ne se produit. Pour ACE, seul le marqueur de configuration turbo est détecté ; tester réellement poids/VAE/encodeur séparément.
4. Modifier chemins et ports, diagnostiquer les valeurs non enregistrées puis enregistrer. Vérifier que les tâches actuelles restent inchangées et que seul un arrêt/relancement de VertIA applique les réglages. Tester ports identiques, chemin relatif, adresse distante refusée, dossier sans droits et disque plein ; le fichier précédent doit rester intact.
5. Ouvrir Ollama après une indisponibilité, actualiser les modèles, démarrer une nouvelle discussion et confirmer qu’une discussion existante garde son modèle. Tester modèle par défaut absent, liste vide, message d’erreur durable et absence de blocage des autres panneaux.
6. Vérifier priorité `.vertia-local.json` sur `.env`, retour à `.env` après renommage, message de configuration corrompue, sauvegarde/restauration complète et mise à jour/retour arrière sur copie des données. Valider un chat et chaque moteur installé hors réseau après installation complète, puis renseigner qualité/mémoire ; la présence des fichiers ne valide pas les générations.

## Phase 7 — Wan 2.2 TI2V-5B réel
Choix du modèle validé par l’utilisateur le 2026-11-02. Aucun serveur ni GPU lancé par Codex ; simulations uniquement.
1. Depuis VertIA lancé par l’utilisateur, demander « Crée une vidéo de la mer ». Vérifier le routage, le prompt de mouvement/caméra et la carte avant lancement. Tester aussi « Anime cette image », « Explique la vidéo » et « Ne génère pas de vidéo » ; les deux dernières ne doivent rien générer. Le filtre lexical ne remplace pas la validation du vrai LLM.
2. Valider un texte → vidéo à 640×384, 49 images, 20 étapes. Vérifier le chargement GGUF/umt5/VAE, le démarrage ComfyUI partagé en lowvram avec 1 Go réservé, la progression puis le MP4 muet 24 fps. Mesurer temps, pic VRAM/RAM, erreurs et qualité dans `_docs/benchmark_video.md`. Les 8 Go restent à valider, sans garantie de succès.
3. Générer une image Qwen, l’utiliser dans le chat et demander de l’animer. Vérifier une seule référence de cette discussion, son transfert uniquement après validation, le recadrage au format choisi et la fidélité du début de vidéo. Modifier dimensions, nombre d’images (4n+1), étapes et graine, enregistrer puis recharger la carte. Tester une surface >960×544, 50 images et deux références : refus sans job.
4. Alterner Qwen → Wan → Chat → musique. Vérifier qu’aucun second ComfyUI ne démarre, que la file sérialise toutes les générations, et que la mémoire du précédent moteur est libérée avant Ollama ou ACE. Surveiller le cache image/vidéo du serveur partagé ; consigner toute insuffisance mémoire. Une instance ComfyUI externe conserve ses options : utiliser une instance dédiée avec les options indiquées.
5. Annuler un démarrage puis une génération vidéo, relancer explicitement depuis la file, tester l’inactivité et la fermeture. Vérifier l’arrêt effectif du prompt identifié avant le moteur suivant, sans annuler un autre prompt externe. Une file externe occupée ou une libération non mesurable doit bloquer le changement de moteur.
6. Vérifier lecteur de carte et galerie, lecture MP4 H.264 dans Edge, téléchargement, recherche temporelle et copie persistante après arrêt/redémarrage de ComfyUI/VertIA. Tester aussi une discussion éphémère, l’absence du modèle/nœud/encodeur vidéo et un disque inaccessible ; en cas d’échec de copie, récupérer le média de secours avant nettoyage externe. Aucun téléchargement de modèle ni mise à jour ComfyUI n’est automatique.

## Phase 6 — Arrêt et récupération sur la machine réelle
Tests automatisés de cette phase : HTTP et processus simulés uniquement.
1. Dans VertIA lancé par l’utilisateur, annuler un démarrage puis une génération Qwen et ACE. Envoyer ensuite un message Chat : vérifier dans le panneau Mémoire et les processus Windows que le moteur précédent a fini de s’arrêter avant Ollama. Répéter Annuler pendant l’arrêt ; la file doit rester bloquée jusqu’à sa fin effective.
2. Si un arrêt incomplet survient réellement, vérifier que Décharger signale l’échec, que le prochain moteur ne démarre pas et qu’une nouvelle libération permet la reprise après disparition du processus survivant. Ne pas provoquer d’arrêt forcé sur une session contenant un travail à conserver.
3. Sur une discussion de test avec une copie locale déjà téléchargée, supprimer cette copie via l’Explorateur puis ouvrir les aperçus de carte et galerie : erreur de média absent, aucun lancement de moteur. Supprimer ensuite la discussion de test.

## Phase 5 — Musique ACE-Step réelle
Codex n’a lancé aucun serveur ni génération : adaptateur, LLM et processus ont été simulés.
1. Vérifier le chemin ACE-Step et ses modèles, fermer toute instance ACE externe, puis lancer VertIA soi-même. Tester « Bonjour », « Explique la musique », « Ne génère pas de musique », « Écris du code pour créer une chanson », « Compose une chanson douce sur la mer en français, 60 secondes », « Generate a song in English », « Crée un instrumental ambient de 90 secondes ». Consigner routage, JSON, tags, originalité, langue et caption anglais ; aucune génération ne doit précéder la validation. Un refus JSON demande une reformulation ; aucune boucle automatique de correction n’est ajoutée.
2. Modifier titre, caption, paroles, BPM, durée, langue et graine ; enregistrer, recharger, annuler une carte. Tester une section vide, un refrain différent, une ligne française très longue, trop de lignes pour 20 secondes, une durée >135 et un caption hors 5–8 termes : refus sans job et consigne adaptée (les bornes/types donnent une erreur générale). Pour un instrumental, vider les paroles et indiquer instrumental dans le caption. Vérifier sur mobile la lisibilité et les champs.
3. Valider un morceau chanté et un instrumental : contrôler le déchargement Ollama avant ACE, le lancement paresseux, offload CPU/backend pt/LLM ACE désactivé, un MP3 de huit étapes, progression et lecteur. Évaluer chant français/anglais, intelligibilité, instruments, fidélité, durée réelle, tempo, absence de coupure et qualité. Tester 60, 90 et 125 secondes ; relever temps à froid/chaud, RAM/VRAM maximales. Le comptage des syllabes et le budget de durée sont approximatifs ; aucune marge mémoire ACE n’est encore chiffrée.
4. Télécharger le MP3, tester lecture et déplacement temporel en galerie, ouvrir son dossier Windows. Après arrêt d’ACE et redémarrage de VertIA, vérifier lecture et téléchargement depuis la copie locale. En mode éphémère, vérifier la disparition des copies VertIA après redémarrage et l’absence de prompt dans les jobs, sans attendre le nettoyage des sorties ACE externes. Vérifier qu’une demande de cover avec audio joint est explicitement refusée.
5. Pendant une musique, envoyer un message Chat puis préparer une image : vérifier la séquence exclusive ACE → Ollama → Qwen, la fin de l’arbre ACE avant le moteur suivant, puis un nouveau lancement musical à froid. Annuler pendant démarrage et génération depuis Mémoire : vérifier arrêt effectif et reprise possible. Avec un délai d’inactivité court, vérifier l’arrêt après repos ; rétablir le délai choisi.
6. Tester installation/modèle absent, port occupé par une instance externe et erreur de génération : erreurs lisibles, aucun arrêt d’un processus externe et aucun moteur suivant tant que la libération reste impossible. Redémarrer VertIA avec job musical actif puis en attente : actif interrompu, attente rejouée une fois ; relance explicite et copie du bon résultat. Ne pas réutiliser une discussion contenant des fichiers à conserver pour tester la suppression. En cas de copie locale impossible, récupérer l’audio depuis le lecteur de secours avant l’arrêt du moteur.

## Phase 4 — Fichiers et édition avec les moteurs réels
Codex a testé uniquement des clients simulés et des dossiers temporaires du dépôt, sans serveur ni génération GPU.
1. Dans VertIA lancé par l’utilisateur, générer une image persistante. Vérifier sa carte dans Fichiers, le prompt, l’aperçu, « Ouvrir », « Télécharger » et le nom/format du fichier téléchargé. Vérifier « Ouvrir le dossier » dans l’Explorateur et la copie sous `outputs/<conversation>/`. Le test Edge sans serveur annule les téléchargements HTTP interceptés ; seuls leur lien/nom et le contenu côté API ont été automatisés.
2. Arrêter ComfyUI, redémarrer VertIA, rouvrir la discussion : vérifier que la galerie et l’aperçu de la carte utilisent toujours la copie VertIA. Les anciennes cartes antérieures à cette phase ne sont pas importées automatiquement et dépendent encore de leur sortie ComfyUI.
3. Sélectionner « Utiliser dans le chat », retirer la pièce jointe, puis glisser l’image sur le formulaire. Vérifier la sélection, la limite de trois, l’absence de doublons et son effacement au changement de discussion. Envoyer « Modifie cette image pour ajouter des étoiles ». Vérifier la référence courte dans le message et la carte d’édition avec le bon identifiant, sans prétendue analyse visuelle par le Chat.
4. Modifier le prompt d’édition, valider, vérifier la progression, la nouvelle image et la conservation de l’original. Évaluer fidélité au sujet, instruction et qualité sur une, puis plusieurs références. Le format est calculé depuis l’image source (résolution Qwen 1024) ; largeur/hauteur sont désactivées. L’inpaint doit être refusé. Vérifier dans ComfyUI que le transfert d’image n’a lieu qu’après validation.
5. En discussion éphémère, générer et réutiliser une image : aperçu et téléchargement disponibles, ouverture du dossier refusée avec message explicite. Redémarrer : discussion et copies VertIA disparues. Les sorties et entrées du moteur externe peuvent subsister ; elles ne sont pas nettoyées par VertIA.
6. Supprimer une discussion de test persistante après téléchargement de son résultat : confirmer la suppression de ses fichiers catalogués et le refus pendant un job. Ne pas utiliser une discussion contenant des fichiers à conserver. Vérifier qu’un résultat manquant ou un dossier inaccessible donne une erreur lisible.
7. Vérifier avec de vrais médias la lecture, les codecs, le déplacement temporel et le téléchargement. La musique est branchée en phase 5, avec validation réelle ci-dessus ; la vidéo attend son moteur et la cover reste indisponible. La future réutilisation vidéo devra être contrôlée lors de son intégration.

## Phase 3 — Cartes d’action et Qwen réel
Validation réservée à l’utilisateur ; tous les appels LLM, démarrages et générations de cette phase ont été simulés par Codex.
1. Vérifier les chemins et les modèles indiqués dans `_docs/architecture.md`. Dans ComfyUI, vérifier/appliquer manuellement le correctif GGUF si nécessaire ; VertIA effectue uniquement une vérification en lecture seule. Lancer VertIA soi-même et vérifier que ComfyUI ne démarre pas avant validation d’une carte.
2. Avec le modèle Chat choisi, essayer ces demandes : « Bonjour », « Explique la diffusion des images », « Ne génère pas une image », « Écris du code pour créer une image », « Dessine un chat sur Mars », « Crée une affiche vintage avec le texte BONJOUR », « Create a picture of the sea », « Modifie cette image ». Consigner carte attendue/obtenue, réponse correcte, respect du texte/langue et qualité du prompt. Une explication, un refus ou une demande de code ne doit pas lancer de génération ; l’édition sans image jointe doit demander une référence. Le benchmark automatique verrouille le filtre et simule les décisions JSON, sans valider le vrai LLM.
3. Modifier prompt, dimensions, étapes et graine ; enregistrer et recharger. Vérifier leur conservation. Annuler une carte et vérifier qu’aucun job image n’apparaît. Des dimensions non multiples de 32 ou une surface supérieure à 1,5 mégapixel doivent être refusées.
4. Valider une carte texte vers image. Vérifier le déchargement Ollama avant Qwen, le démarrage paresseux (jusqu’à dix minutes à froid), la progression, le résultat et l’aperçu. Vérifier qu’un double clic n’ajoute aucun doublon. Refaire une image à chaud et relever temps, RAM, VRAM et qualité.
5. Pendant une génération, envoyer un message Chat : vérifier l’exécution séquentielle et la libération de Qwen avant Ollama. Vérifier l’aperçu après l’arrêt du ComfyUI lancé par VertIA et après rechargement de la page. Ne pas déplacer/supprimer son fichier de sortie.
6. Annuler un job image depuis Mémoire ; vérifier l’interruption du seul prompt concerné et la fin effective avant le job suivant. Tester ComfyUI indisponible, correctif absent, modèle manquant et RAM insuffisante : erreur lisible, puis reprise possible après correction. Tester également une instance externe occupée : refus du changement de moteur, sans suppression globale de sa file ni arrêt de son processus.
7. Redémarrer VertIA avec un job image actif puis avec un job en attente : actif marqué interrompu/reprise explicite, attente rejouée une seule fois. Vérifier la reprise depuis Mémoire et l’état de la carte associée, puis la suppression d’une discussion après sa fin.
8. En conversation éphémère, préparer et valider une carte ; vérifier l’aperçu et le journal des jobs sans prompt. Après redémarrage, vérifier la disparition de la carte et l’absence de rejeu. Le fichier généré peut rester dans les sorties ComfyUI, comme toute sortie de ce moteur.

## Phase 2 — Ressources et file GPU avec le matériel réel
Validation réservée à l'utilisateur ; Codex utilise uniquement des moteurs et routes simulés pour les générations.
1. Dans l'application lancée par l'utilisateur, ouvrir Mémoire. Comparer la RAM avec le Gestionnaire des tâches, la VRAM avec `nvidia-smi` et les modèles avec `ollama ps`. Vérifier les compteurs par PID Windows et les avertissements si une source est indisponible.
2. Envoyer un message Chat : vérifier l'apparition du job, son état actif puis terminé. Annuler depuis Mémoire pendant une réponse : vérifier la fermeture du flux et la conservation du texte partiel dans Discussion.
3. Pendant une réponse, cliquer Tout libérer : vérifier le refus explicite. Après la réponse, tester Décharger sur un modèle, puis Tout libérer ; comparer avec `ollama ps`.
4. Avec un délai d'inactivité court configuré, terminer un échange puis attendre : vérifier le déchargement du modèle sans arrêt global du service Ollama. Remettre ensuite le délai souhaité.
5. Régler temporairement le seuil RAM en dessous de l'occupation courante, redémarrer puis envoyer un message : vérifier le refus lisible sans génération. Restaurer le seuil ; vérifier qu'un nouveau message fonctionne.
6. Redémarrer pendant une réponse : vérifier le statut interrompu du job et des messages, sans rejeu automatique. Vérifier qu'un rechargement de page retrouve les jobs et leur état final.
Les changements entre moteurs réels et la reprise de jobs image/musique seront à contrôler après branchement de leurs adaptateurs ; ils sont couverts ici uniquement avec des moteurs simulés.

## Phase 1 — Chat avec Ollama réel
Validation réservée à l'utilisateur ; aucune génération GPU ni aucun serveur lancé par Codex.
1. Dans l'application lancée par l'utilisateur, créer un dossier avec une instruction distinctive et une conversation avec un modèle installé. Vérifier le streaming, le titre et le respect de l'instruction.
2. Envoyer un deuxième message pendant une réponse : vérifier sa mise en attente puis sa réponse avec l'historique du premier échange.
3. Cliquer Stop pendant une réponse longue avec un message en attente : vérifier l'arrêt, la conservation du texte partiel, l'annulation du message suivant et la possibilité de reprendre.
4. Recharger la page pendant le streaming puis rouvrir la discussion : vérifier l'absence de perte ou de duplication du texte. Vérifier la persistance après redémarrage et le marquage des messages interrompus.
5. En mode éphémère, donner un prénom puis le demander : vérifier la mémoire de l'échange ; redémarrer l'application et vérifier la disparition de cette discussion.
6. Tester une longue discussion jusqu'au déclenchement du résumé, attendre une période d'inactivité, puis vérifier la conservation d'un fait ancien. Un message trop long doit être refusé explicitement.
7. Demander un livrable : vérifier Copier et Télécharger. Changer de modèle dans une nouvelle discussion : vérifier le déchargement ciblé du précédent avec `ollama ps`.
8. Rendre Ollama indisponible puis envoyer un message : vérifier une erreur visible et la possibilité d'envoyer à nouveau après son rétablissement.

## Reprise auto après redémarrage (orchestration)
1. Tant que creation_llm s'entraîne : redémarrer Windows (ou attendre un redémarrage) et ouvrir la session utilisateur.
2. Attendre 3 min puis lire `_orchestration/state/reprise.log` : une ligne « creation_llm : jeton perime, reprise » doit apparaître.
3. Vérifier `python _orchestration/vram_lock.py status` : creation_llm détenteur, VRAM occupée, reprise au dernier checkpoint (pas de perte au-delà de 15 min).

## Vidéo n°1 — Wan 2.2 TI2V-5B (aucun téléchargement)
1. Fermer Ollama ou décharger les modèles (`ollama ps` doit être vide).
2. Lancer ComfyUI-Qwen en mode basse VRAM :
   ```powershell
   cd D:\ServOMorph\ComfyUI-Qwen
   .\.venv\Scripts\python.exe main.py --port 8189 --lowvram --reserve-vram 1
   ```
3. Ouvrir http://127.0.0.1:8189, menu Workflow > Browse Templates > Video > « Wan 2.2 5B TI2V ».
4. Remplacer « Load Diffusion Model » par « Unet Loader (GGUF) » → `Wan2.2-TI2V-5B-Q4_K_M.gguf`. Vérifier : CLIP = `umt5_xxl_fp8_e4m3fn_scaled`, VAE = `wan2.2_vae`. Remplacer « VAE Decode » par « VAE Decode (Tiled) ».
5. Test A (texte → vidéo) : 960×544, 49 images, 24 fps, 20 steps, CFG 5. Prompt : « a red fox walking through a snowy forest at sunrise, cinematic ».
6. Test B (image → vidéo) : charger une image Qwen existante (`D:\ServOMorph\ComfyUI-Qwen\output\`) sur `start_image`, mêmes réglages.
7. Me donner pour chaque test : temps total, plantage éventuel, note de qualité de 1 à 5 (fluidité, déformations, respect du prompt).

## Atelier v1
Tests automatisés (pytest serveur, Node sur images synthétiques) et contrôle HTTP réalisés ; aucun test navigateur. Lancer `python run_atelier.py` (port 4320).
1. Import d'un scan : importer un vrai scan de mandala (3000 px ou plus) par bouton puis par glisser-déposer, et un scan du modèle colorié (PNG, JPEG, WebP). Vérifier l'ajustement à l'écran, le zoom (molette, +/-, ajuster, 100 %), le défilement, puis les calques : visibilité, ordre, opacité, renommage, suppression.
2. Pot de peinture sur le mandala : remplir plusieurs zones. Vérifier l'arrêt au trait, l'absence de liseré blanc, le crayon conservé (calque « Couleurs » en multiplication), le seuil automatique puis manuel, la fermeture des trous 0 à 3 px, la tolérance, la source calque actif/visibles, le mode direct décoché, la réactivité et le curseur d'attente.
3. Palette depuis une image : extraire 2, 8 et 24 couleurs du modèle colorié, avec et sans filtre papier/trait ; pastilles au clic et au clavier ; pipette (calque actif, image composée, Alt+clic avec le pot) ; couleurs récentes après rechargement de la page.
4. Pinceau et gomme : taille, dureté, opacité non cumulée dans un même trait, aperçu du curseur, calque déplacé.
5. Texte et formes : créer texte, rectangle, ellipse, ligne (Maj pour carré/cercle/45°), sélectionner, déplacer, redimensionner aux poignées (Maj : proportions), modifier les propriétés, double-clic pour éditer un texte, Suppr.
6. Annuler/rétablir : Ctrl+Z, Ctrl+Y, Ctrl+Maj+Z sur au moins 30 pas mêlant calques, remplissages, pinceau et éléments ; raccourcis ignorés pendant la saisie de texte.
7. Export PNG : taille identique au scan d'origine, couleurs, trait et éléments présents.
8. Enregistrement et réouverture : Ctrl+S (nom demandé la première fois), fermer, rouvrir par « Ouvrir » ; calques, éléments, calque « Couleurs » lié et palette restaurés.
9. Retouche IA : peindre un masque à plusieurs niveaux de zoom, régler sa taille, gommer, inverser et effacer ; vérifier la surimpression rouge, sans nouveau calque ni entrée d'historique. Masque vide ou texte vide : erreur et aucun envoi.
10. Retouche IA : sur plusieurs calques (visibilité, déplacement, opacité et fusion), décrire la modification, régler la force puis lancer ; vérifier le suivi et le temps écoulé, les commandes protégées pendant l'attente, puis le calque supérieur « Retouche IA » à la résolution du document. Annuler/rétablir en un pas et exporter le PNG.
11. Retouche IA : annuler pendant l'exécution, vérifier l'état annulé et le nettoyage des deux fichiers d'inbox ; relancer. Contrôler les messages GPU occupé, pause utilisateur et échec moteur. Fermer la page pendant l'attente : aucune interrogation supplémentaire ; le serveur termine et nettoie les entrées.

## Portail phase 5 — pages /voix et /musique
Essais GPU réels faits par la CLI (kokoro, chatterbox, whisper, ACE-Step) ; pages non testées dans un navigateur. Lancer `python run.py`, ouvrir l'accueil.
1. Accueil : les cartes Voix et Musique ouvrent `/voix` et `/musique`.
2. `/voix` : synthèse Kokoro puis Chatterbox (avec une voix de référence téléversée), écoute et téléchargement du WAV ; transcription d'un fichier audio téléversé, texte affiché.
3. `/musique` : un instrumental de 30 s puis un morceau chanté avec paroles ; écoute, téléchargement, qualité de 1 à 5.
4. Pendant une génération, `python _orchestration/vram_lock.py status` montre le jeton `vertia` ; creation_llm repart après 5 min d'inactivité.

## CreaZik via VertIA en conditions réelles
Branchement essayé sur une playlist de test hors CreaZik (2 pistes générées). Non essayé sur la radio elle-même.
1. Lancer une génération de la rotation (ou une création d'auditeur) : la piste apparaît dans la playlist, MP3 et visualisation produits, lecture normale sur la radio.
2. Vérifier que la première piste à froid tient dans le délai (900 s minimum) et que les suivantes prennent moins d'une minute.

## Atelier dans le portail
1. Redémarrer le portail (`run.py`), ouvrir `http://127.0.0.1:4310`, cliquer la tuile Atelier : l'éditeur s'ouvre dans le même onglet sous `/atelier/`.
2. Ouvrir, modifier et enregistrer un projet existant de `outputs/atelier` ; le recharger : rien n'est perdu.
3. Lancer une retouche IA par masque depuis l'Atelier : le résultat revient dans le calque.

## Page /video
1. Ouvrir `http://127.0.0.1:4310/video`, générer un clip texte vers vidéo de 17 images : lecture et téléchargement du MP4.
2. Image vers vidéo : téléverser une image PNG, générer 17 images : le clip part de l'image.

## Chat portail phase 7 — commandes et fonctions reprises d'IA_V7
1. Taper `/` dans la saisie : les suggestions `/help`, `/write`, `/rgpd` s'affichent ; `/help` affiche l'aide sans laisser de message dans la discussion après rechargement.
2. Demander au modèle un bloc ```livrable html```, puis `/write page.html` : le fichier apparaît dans l'onglet Fichiers ; « Ouvrir » l'affiche en texte brut, « Télécharger » donne `page.html`. Un second `/write page.html` est refusé.
3. `/rgpd Mme Alice Martin, alice@example.fr, 06 12 34 56 78` : texte anonymisé affiché ; après rechargement, la discussion ne contient plus le texte d'origine.
4. Bouton Capture : sélectionner une zone, un PNG est créé dans `outputs/captures/`.
5. Changer le modèle d'une discussion au repos : la réponse suivante vient du nouveau modèle ; le sélecteur est bloqué pendant une réponse.
6. Double-clic sur une discussion ou un dossier : renommage ; bouton télécharger d'un livrable `json` : fichier `.json`.

## Retouche IA et logo après correctif du 2026-11-19
1. Lancer `python run.py` (avec rechargement), ouvrir l'Atelier, faire une retouche IA par masque : le résultat revient dans le calque (avant correctif : échec « moteur » en 5 s).
2. Vérifier que le nouveau logo (arbre-circuit) s'affiche dans l'en-tête et l'onglet, sans cadre rond ni fond blanc.

## Phase 7-bis — GPU réservé tant que l'interface est ouverte
1. Lancer `python run.py` et laisser l'interface ouverte : `python _orchestration/vram_lock.py status` affiche le détenteur `vertia` (note « portail : ollama ») ; creation_llm est en pause ; le badge indique gemma4:12b chargé.
2. Laisser l'interface ouverte plus de 5 minutes sans rien faire : le jeton reste à `vertia` (pas de libération sur inactivité).
3. Recharger la page (F5) : le jeton reste à `vertia`, pas de nouveau préchargement visible.
4. Fermer l'onglet : environ 30 à 35 s plus tard, le jeton est rendu, `ollama ps` est vide et creation_llm reprend (ligne REPRISE_OK dans le statut).
5. Rouvrir l'interface : le préchargement repart et le jeton revient à `vertia`.

## Phase 7-bis — Design du chat repris d'IA_V7
1. Lancer `python run.py`, ouvrir Discussion : colonne de gauche de 280 px (Nouveau chat, Projets), bulles utilisateur à droite en teal et assistant à gauche avec bordure, polices Inter et Space Grotesk, comme dans IA_V7.
2. Basculer le thème de Windows (clair puis sombre) : le chat et la navigation suivent le thème ; l'en-tête VertIA et les panneaux Fichiers, Mémoire, Outils gardent leur thème vert.
3. Vérifier les fonctions : cartes d'action, pièces jointes, suggestions `/`, Capture, glisser-déposer et épinglage dans la navigation, Stop, largeur réduite (moins de 900 px).
4. Signaler ce qui diffère encore d'IA_V7 (par exemple le sélecteur de modèle, resté sous la zone de saisie au lieu de la barre du haut).
