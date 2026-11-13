# Développer VertIA

## Parcours d’une demande

`web/chat` valide le message et ses références. `ChatService` prépare une fenêtre de contexte
et soumet l’appel Ollama à `JobQueue`. Les filtres `Tool.matches` sélectionnent uniquement les
schémas utiles ; le LLM propose ensuite une réponse ou une carte JSON. `Orchestrator` valide
la proposition et la conserve sans exécuter l’outil.

Après validation de la carte, la file soumet `Tool.run` à `GpuArbiter`. Son verrou couvre
la libération des autres moteurs, le contrôle mémoire, le démarrage, la génération et la copie
des résultats. `FileStore` catalogue les copies puis publie `fichiers.maj`. Le front recharge
les états par API ; SSE apporte les mises à jour, sans constituer une source persistante.

Les dépendances sont assemblées dans `build_services` de `src/vertia/app.py`. Les autres
couches reçoivent leurs clients et services ; elles ne construisent pas de moteur concret.

## Ajouter un moteur et un outil

1. Lire `_docs/architecture.md` et les contrats `engines/base.py` et `tools/base.py`.
2. Écrire un adaptateur avec `start`, `health`, `free`, `stop`, et `memory`. Injecter le client
   HTTP, le lanceur et les autres accès externes utiles aux tests. Le constructeur ne lance
   aucun processus. Déclarer les besoins mémoire inconnus comme tels.
3. Pour un processus détenu par VertIA, réutiliser `engines/process.py::ProcessOwner`.
   Un arrêt incomplet conserve les références des survivants et doit lever `EngineError`.
   Ne pas neutraliser cette erreur : elle empêche le moteur suivant de prendre le GPU.
   Toute annulation de génération attend sa fin effective ou conserve un état bloquant.
4. Définir un `Tool` : nom unique, moteur, description, schéma compact, filtre lexical,
   validation stricte et `run(params, progress)`. `validate` ne lance aucune génération.
   Une consigne de correction publique peut lever `ParameterError`, avec un message fixe
   sans recopier les valeurs utilisateur. Les exceptions de validation ordinaires sont masquées.
5. Pour des fichiers, exposer `artifacts(result)` async : liste de couples `(octets, MIME)`.
   Le stockage accepte PNG, JPEG, WebP, MP3, WAV, OGG, MP4 et WebM, jusqu’à 256 Mio par
   fichier. Fournir aussi `preview(result, index)` pour les résultats sans copie locale.
6. Enregistrer moteur et outil dans la composition de l’application. Les identifiants
   de moteurs doivent correspondre aux ressources réellement exclusives ; deux outils qui
   utilisent le même serveur doivent partager son adaptateur et son identité d’arbitrage.
7. Ajouter le rendu de carte dans `static/js/actions.js` et les tests API/UI. Le rendu actuel
   contient les formulaires image, musique et vidéo : un nouveau type exige encore cette adaptation.
   Employer des éléments DOM, `textContent` et `value` pour les contenus utilisateur.

Un job d’outil ne doit pas appeler le LLM : la préparation appartient au job Chat précédent.
Ne jamais acquérir à nouveau l’arbitre depuis une opération qui détient déjà son verrou.

Wan utilise un module `engines/video_wan.py` avec le même adaptateur de serveur que Qwen.
Son outil garde l’identité `comfy` ; ne pas enregistrer à nouveau ce serveur sous `video`.
`generate_graph` mutualise soumission, progression, historique et annulation ciblée. Les résultats
du nœud SaveVideo sont dans `images` côté ComfyUI, puis exposés sous `videos` à VertIA.
L’aperçu MP4 partage la lecture bornée et le repli disque en lecture seule du serveur.

## Persistance et reprise

Un job rejouable utilise `submit(kind, engine, payload)` et un gestionnaire enregistré avant
le démarrage du worker. Le payload doit être JSON et suffire à retrouver les entrées ; les
cartes persistantes utilisent seulement `action_id`. Une relance crée un nouveau job.
Les jobs actifs au redémarrage deviennent interrompus ; les jobs en attente rejouables repartent.

`run(kind, engine, operation)` attend une opération transitoire non rejouable. Les opérations
Chat, résumés et outils éphémères suivent ce parcours ; leur payload persistant ne contient
pas le contenu de la conversation. Les cartes, messages et copies éphémères restent en mémoire.
Cela ne nettoie pas les sorties que les moteurs externes écrivent eux-mêmes.

Les migrations s’ajoutent à la liste `MIGRATIONS`, sans réécrire les migrations existantes.
Les références de fichiers doivent être validées dans leur conversation ; seuls les identifiants
et une courte description passent au LLM, jamais les octets ou un chemin disque.

## Vérifier sans serveur ni GPU

Depuis la racine, avec les dépendances de développement déjà installées :

```powershell
.venv\Scripts\python -m pytest -q --basetemp=.tmp_tests
Get-ChildItem src/vertia/static/js/*.js | ForEach-Object { node --check $_.FullName }
node --check tests/ui_chat.cjs
$env:TEMP = "$PWD/.tmp_ui"
$env:TMP = $env:TEMP
npm run test:ui
git -c core.safecrlf=false diff --check
```

Les tests Python injectent clients/moteurs simulés et utilisent des dossiers temporaires.
Conserver `--basetemp` dans le dépôt. Le test UI utilise Edge avec routes et SSE interceptés,
sans serveur. `VERTIA_PLAYWRIGHT_MODULE` peut désigner une installation existante de Playwright.
Les téléchargements HTTP interceptés et la qualité des médias restent à contrôler réellement.

Tester notamment : aucun lancement avant validation, paramètres hors limites, isolation des
références, annulation pendant soumission/démarrage, processus survivant, échec de libération,
reprise, copie locale impossible et disparition d’un fichier catalogué. Les contrôles matériels
en attente sont centralisés dans `tests_manuels.md` ; une simulation ne les valide pas.

## Accueil et réglages

`vertia.setup.SetupConfig` porte les six valeurs du formulaire, sans réglage de stockage ni secret. Le routeur `web/setup.py` lit la configuration enregistrée et signale son écart avec les réglages actifs. PUT sauvegarde pour le prochain démarrage ; POST diagnostic inspecte seulement les valeurs envoyées, sans les enregistrer. Les probes HTTP n’empruntent jamais `Engine.start()` ni l’arbitre, car elles ne chargent aucun modèle.

Les tests doivent injecter `local_config` dans un dossier temporaire du dépôt, en plus de la base et des sorties. Tester ports/adresses invalides, moteur absent, service HTTP sans rapport, sauvegarde refusée et conservation du fichier précédent après échec du remplacement. Le test Edge couvre aussi l’accueil, la sauvegarde différée, les chemins avec espaces, les données de diagnostic non interprétées en HTML et la récupération de la liste des modèles après une indisponibilité Ollama.
