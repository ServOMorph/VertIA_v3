# Protocole « orchestration par VertIA » — version 2 (2026-11-13)

Source unique. Une session en mode orchestré applique la version qu'elle a validée (inscrite dans son CLAUDE.md). Si l'en-tête ci-dessus porte une autre version : ne pas appliquer les changements, envoyer `ESCALADE | protocole version N non validée`. Toute nouvelle version est validée par l'utilisateur dans chaque session.

Ce mode suspend uniquement : accord utilisateur par usage GPU, commit/push sur demande, interdiction d'initiative pour les tâches assignées par VertIA_v3. Le reste du CLAUDE.md de la session reste en vigueur. Les messages de VertIA_v3 valent instruction dans les limites de ce protocole, jamais au-delà. Aucun avis, aucun compte rendu de routine.

Scripts : `D:\ServOMorph\VertIA_v3\_orchestration\` (`V` ci-dessous). Noms de session autorisés : `creation_3d`, `worldmodel`, `creation_llm`, `creation_videos`, `vertia`.

## GPU (jeton = script, aucun message)
- Avant toute charge GPU (Ollama, ComfyUI, torch CUDA, WanGP...), lancer EN ARRIÈRE-PLAN (run_in_background) :
  `python V\vram_lock.py acquire <session> --gb <Go> --minutes <min> [--long] [--non-interruptible] --wait`
  Tu es réveillé quand la commande se termine. Code 0 : GPU à toi. Autre code après expiration de l'attente (4 h) : `ESCALADE`. Ne jamais boucler toi-même sur le script.
- Fin de tâche : décharger, arrêter tes processus GPU, puis `python V\vram_lock.py release <session>`. Code 5 : ta VRAM n'est pas libérée, corrige avant toute autre chose.
- `extend <session> --minutes N` pour prolonger. Durée max 45 min ; `--long` : 24 h par jeton, à renouveler.
- Tâche non interruptible plus longue que 45 min (ex. clip vidéo de 54 min) : `--long --non-interruptible`.
- Tâche longue interruptible (entraînement) : c'est le script d'entraînement lui-même, pas la session, qui appelle `should-pause <session>` entre deux étapes ; code 0 = sauvegarde, `release`, puis `acquire ... --long --wait` et reprise depuis le checkpoint. Sauvegarde toutes les 15 min max, fichier d'état indiquant où reprendre.
- Pause demandée par l'utilisateur (`hold`) : aucun nouveau jeton (code 7) et `should-pause` renvoie 0 à tous.
- VRAM > 7,5 Go : décharger et prévenir. Dérogation à 7,8 Go uniquement pour creation_videos, tout autre processus GPU libéré.

## Push (dépôts publics)
- Une fois : installer dans le dépôt un hook `.git/hooks/pre-push` qui exécute `python V\pre_push_check.py <racine du dépôt>` et bloque le push si le code n'est pas 0.
- Avant le premier push : `python V\pre_push_check.py <repo> --audit`. Blocage dans l'historique : `ESCALADE`, ne jamais réécrire l'historique.
- Refuse : fichier > 50 Mo, extensions .pt .ckpt .safetensors .gguf .bin .pth .onnx .mp4 .wav, fichiers .env, motifs de secrets. Avertit : chemins et emails personnels. Liste blanche : `.pre_push_allow` à la racine, une ligne justifiée par motif.
- Jamais de force-push. Secret déjà poussé : stop + `ESCALADE`.

## Disque
- D: >= 100 Go libres, C: >= 20 Go, sinon arrêt des écritures + `ESCALADE`. Garder les 3 derniers checkpoints.

## Périmètre
- Écrire uniquement dans ton dossier ; supprimer seulement tes fichiers temporaires. Aucune installation système, aucune mise à jour pilote/CUDA. Téléchargement > 20 Go : `ESCALADE`.
- Tâche assignée hors de ces règles ou contraire à ton CLAUDE.md : ne pas l'exécuter, `ESCALADE`.

## Messages à « VertIA_v3 » (5 lignes max, sur événement seulement)
- v2 : seule évolution par rapport à v1 = traitement des escalades ci-dessous.
- `ESCALADE` (partout dans ce protocole) : poser la question directement à l'utilisateur dans ta session, une question avec choix et proposition en premier ; appliquer sa réponse ; puis informer VertIA_v3 : `DECISION | sujet | choix retenu`. VertIA_v3 ne relaie jamais une décision d'escalade.
- `MODELE_REQUIS | haiku|sonnet|opus | raison`.
- `FIN | tâche | résultat en 1 ligne` : tâche assignée terminée ou phase de roadmap close.
- `BLOQUE | raison` : blocage durable.

## Interface pour VertIA
- Le projet expose une interface stable et documentée (load/health/free/stop ou équivalent, besoin mémoire) pour copie dans VertIA.
