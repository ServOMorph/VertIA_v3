# Procédure de migration d'un projet vers un module du portail

Écrite à l'issue de la phase 4 (module image), à suivre pour les phases 5 à 11. Référence d'architecture : `architecture_portail.md`. Le module image sert d'exemple : `modules/image/`.

## 1. Avant de commencer
- Lire l'inventaire du projet (`inventaire_ia_locale.md`) et la décision validée (module, moteur ou archive).
- Le projet d'origine reste intact (copie seule). Aucune session d'origine fermée avant la validation de l'utilisateur.
- Vérifier la place sur D: (au moins 100 Go libres avant tout déplacement de poids) et que le GPU est libre ou pris par `vram_lock.py` (session `vertia`).

## 2. Module (code)
1. Créer `modules/<nom>/module.py` avec `MODULE = Module(nom, activite, titre, version, capacites=['domaine.verbe'], outils={...}, poids=[...], sante=...)`.
2. Un outil par capacité : attributs `capacite` et `moteur` (nom d'un moteur de l'arbitre, ou `None`), méthodes `valider(params)` (lève `ParameterError`) et `executer(params, dossier)` (écrit ses fichiers dans `dossier`, renvoie la liste des chemins). La fabrique de l'outil peut recevoir `(settings, chemins, moteurs)` : réutiliser le moteur déjà enregistré, jamais une seconde instance du même processus.
3. `sante()` : diagnostic passif (dossiers et poids présents), sans chargement GPU ni appel réseau.
4. Aucun chemin `D:\` dans `src/` ni `modules/` (un test le contrôle) ; tout passe par `Chemins` (`config/chemins.toml`).
5. Tests avec un faux moteur (aucun GPU) : demande par l'API v1, livraison dans `outbox/<session>/<id>/essai_1.<ext>`, paramètres invalides refusés.

## 3. Poids
1. Simulation : `python outils/deplacer_poids.py deplacer <dossier_source> <racine>/models/<format>/<dossier>` (sans `--appliquer`). Contrôler la taille, l'espace libre et la liste des fichiers.
2. Aucun poids de creation_llm (le script le refuse). Éviter de déplacer pendant qu'un moteur lit le dossier (le script refuse un fichier utilisé).
3. Application : même commande avec `--appliquer`, un dossier à la fois (copie, SHA-256, suppression de l'original, jonction). Débit observé : environ 16 Mo/s en moyenne (copie plus deux calculs d empreinte), soit 54 Go en 57 min environ.
4. Contrôle : la jonction existe (`os.path.isjunction`), les fichiers sont visibles depuis l'ancien chemin, journal dans `models/_deplacements.jsonl`. Retour arrière : `outils/deplacer_poids.py retour <id> --appliquer`.
5. Ne jamais supprimer l'ancien dossier du projet : la jonction y pointe.

## 4. Essai réel (obligatoire avant de marquer la phase faite)
1. Prendre le GPU : `vram_lock.py acquire vertia --gb <n> --minutes 40 --wait --note "<essai>"` (creation_llm se met en pause et reprend seul).
2. `python vertia_gen.py <activite> --session vertia --prompt "..." [--param k=v ...]` : démarre le portail et le moteur, attend la livraison, imprime le chemin du fichier. Premier essai à froid mesuré pour l'image : environ 9 min (démarrage du portail et de ComfyUI, chargement des modèles, 768 x 768, 20 étapes), dont 280 s de génération.
3. Regarder le résultat (image, son) : un fichier présent n'est pas un résultat correct.
4. Arrêter le portail et le moteur lancés pour l'essai, vérifier la VRAM libre, `vram_lock.py release vertia`, puis vérifier que creation_llm repart (nouvelle ligne `step N` dans `_orchestration/state/reprise_sortie.log`, premier pas attendu environ 11 minutes après la reprise du jeton).

## 5. Fin de phase
- Ajouter une ligne d'usage à `CLAUDE.md` (validation de l'utilisateur requise, trois validations) et la proposer aux autres sessions par message.
- Bilan de dette : refacto dédié avant la phase suivante ou non.
- Session d'origine fermée et ancien dossier supprimé seulement sur accord écrit de l'utilisateur, projet par projet.
