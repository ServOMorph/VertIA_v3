# Architecture cible du portail (phase 2, validée le 2026-11-15)

Statut : validée par l'utilisateur le 2026-11-15 (artefact de validation, 11 sections « D'accord », sans commentaire), gate de la phase 2 de `roadmap_portail.md`. Les points marqués **[décidé]** ont été retenus tels que proposés. Rien n'est implémenté ici : l'implémentation commence en phase 3.

Point de départ (code lu le 2026-11-15) : `Engine` (start, health, free, stop, `MemoryNeeds`), `Tool` (name, engine, parameters, validate, run), `ToolRegistry`, `GpuArbiter` (un moteur actif, libère les autres), `JobQueue` SQLite, `FileStore` (fichiers rattachés à une conversation), `Settings` (.env puis `.vertia-local.json`). Ces contrats sont conservés et étendus, pas remplacés.

## 1. Arborescence
```
VertIA_v3/
  run.py                    serveur + UI (existant) ; --headless pour le démarrage par la CLI
  vertia_gen.py             CLI pour les autres sessions (client léger de l'API)
  src/vertia/               cœur du portail (git)
    modules/registry.py     découverte des modules, écran d'accueil
    demandes/               boucle demande / essai / retour, outbox, journal
    api/v1/                 routes versionnées utilisées par la CLI
  modules/<nom>/            code repris des projets solo (git), un dossier par module
    module.py               déclaration (section 2)
    engines.py  tools.py    adaptateurs vers les moteurs
    tests/
  engines/<nom>/            installations tierces copiées (hors git) : comfyui, acestep, wangp...
    .venv/                  recréé, jamais déplacé
  models/                   poids partagés (hors git), section 3
  outputs/                  fichiers générés (hors git) : <conversation>/ pour l'UI
  outbox/<session>/         livraisons aux sessions (hors git), section 6
  inbox/                    fichiers fournis par l'utilisateur (images à retoucher...), hors git
  data/                     SQLite (hors git)
  config/chemins.toml       chemins des moteurs et des poids (hors git, modèle versionné)
```
`modules/` contient du code de l'utilisateur ; `engines/` du code tiers non modifié (les correctifs locaux, comme celui de ComfyUI-GGUF, sont versionnés dans `modules/<nom>/correctifs/` et appliqués par script à l'installation).

## 2. Contrat de module
`modules/<nom>/module.py` expose un objet `MODULE` :

| Champ | Rôle |
|---|---|
| `nom`, `activite`, `titre` | identifiant, activité de l'accueil (image, musique, voix, vidéo, chat, 3d, animation_3d, worldmodel, llm), libellé |
| `version` | version du module (semver), journalisée avec chaque essai |
| `moteurs` | fabriques d'`Engine` (reçoivent `Settings` et chemins résolus) |
| `outils` | fabriques de `Tool` ; chaque outil déclare ses `capacites` |
| `capacites` | verbes exposés à la CLI : `image.generer`, `image.retoucher`, `musique.generer`, `voix.dire`, `3d.depuis_image`... |
| `besoins` | `MemoryNeeds` par moteur (VRAM, RAM, durée typique, interruptible oui/non) |
| `poids` | liste des poids requis (chemin relatif sous `models/`), contrôlée au diagnostic |
| `sante()` | diagnostic passif (fichiers présents, venv présent), jamais de chargement GPU |

Règles : un module ne connaît pas les autres ; le cœur ne connaît aucun module en dur (découverte par le dossier `modules/`). Un module sans moteur (Comparatif-Image) déclare seulement des outils qui appellent les capacités des autres modules. Les moteurs gardent le cycle de vie actuel (`start/health/free/stop`) et passent tous par `GpuArbiter`.

## 3. Poids et jonctions
- `models/` organisé par format, pas par projet, pour qu'un poids serve à plusieurs moteurs :
  `models/hf/` (HF_HOME commun), `models/ollama/` (OLLAMA_MODELS), `models/comfy/{unet,clip,text_encoders,vae,loras,...}`, `models/<moteur>/` pour les formats propres (ACE-Step, WanGP, TripoSR...).
- ComfyUI lit `models/comfy/` par `extra_model_paths.yaml` (pas de copie dans `engines/comfyui/models`).
- Déplacement d'un poids : copie vers `models/`, contrôle d'empreinte (SHA-256), suppression de l'original, jonction Windows (`mklink /J`, dossier) à l'emplacement d'origine. Le projet solo continue de fonctionner tant qu'il n'est pas supprimé.
- Dédoublonnage seulement après égalité d'empreinte (FLUX.1-dev : contrôle octet par octet déjà fait sur un shard, à compléter).
- Exclusion : poids et checkpoints de creation_llm tant que l'entraînement tourne.
- Script unique `outils/deplacer_poids.py` (phase 3) : mode `--simulation` par défaut, journal des déplacements, retour arrière (jonction supprimée, fichiers recopiés).

## 4. Configuration des chemins
- Racine déduite de l'emplacement du dépôt ; `engines/`, `models/`, `outputs/`, `outbox/`, `inbox/` relatifs à la racine par défaut.
- `config/chemins.toml` : chemin de chaque moteur et dossier de poids, surcharge des valeurs par défaut. Remplace progressivement `VERTIA_COMFY_DIR`, `VERTIA_ACESTEP_DIR` (lus encore en repli pendant la migration).
- Ordre de priorité inchangé : défauts, `chemins.toml`, `.env`, `.vertia-local.json`, overrides de test.
- Aucun chemin `D:\` en dur dans `src/` ni `modules/` (test de non-régression qui le cherche).

## 5. Contrat CLI / API v1
### API (localhost seulement, préfixe `/api/v1`)
| Route | Rôle |
|---|---|
| `GET /api/v1/sante` | `{version_api, version_vertia, pret}` |
| `GET /api/v1/capacites` | capacités disponibles, paramètres, besoins |
| `POST /api/v1/demandes` | `{session, capacite, params, critere?, essais_max?}` → `{id}` |
| `GET /api/v1/demandes/{id}` | état : attente, actif, livre, valide, a_refaire, echec, plafond ; chemins livrés |
| `POST /api/v1/demandes/{id}/retour` | `{verdict: valide|a_refaire, motif?}` ; `a_refaire` relance un essai |
| `POST /api/v1/demandes/{id}/annuler` | annulation |
Version : `version_api` dans `sante` ; changement incompatible = `/api/v2`, v1 conservée jusqu'à migration des clients (CreaZik_V3 compris).

### CLI `vertia_gen.py`
```
vertia_gen.py <capacite> --session <nom> [--prompt TXT] [--param k=v ...] [--critere TXT]
              [--essais N] [--timeout S] [--sans-attente]
vertia_gen.py retour <id> valide|a_refaire [--motif TXT]
vertia_gen.py etat <id>      vertia_gen.py capacites
```
- Sortie standard : un chemin de fichier livré par ligne, rien d'autre. Messages sur la sortie d'erreur. Première ligne d'erreur = `id=<demande>` pour permettre le retour.
- Démarrage automatique : si `sante` ne répond pas, lancement détaché de `run.py --headless`, attente 60 s.
- Timeout par défaut 1800 s (premier prompt Qwen relevé jusqu'à 345 s), réglable.
- Codes de sortie, alignés sur `vram_lock.py` quand le sens est le même :

| Code | Sens |
|---|---|
| 0 | livré |
| 1 | erreur interne |
| 2 | encore en attente (avec `--sans-attente`) |
| 4 | GPU occupé |
| 5 | timeout |
| 6 | échec de génération (moteur) |
| 7 | pause GPU utilisateur |
| 8 | session inconnue |
| 9 | serveur injoignable après démarrage automatique |
| 10 | paramètres invalides |
| 11 | plafond d'essais atteint |

## 6. Boucle demande / génération / retour (version hybride)
1. La session dépose une demande (capacité, paramètres, critère de réussite en une phrase, `essais_max` : défaut 3, maximum 5).
2. VertIA valide les paramètres. Analyse des frictions (relecture du prompt, réécriture) seulement si la capacité est nouvelle pour cette session ou après 2 retours `a_refaire` : sinon la demande part telle quelle (économie de tokens).
3. Génération par la file de jobs. Livraison par copie dans `outbox/<session>/<id>/essai_<n>.<ext>` + `essai_<n>.json` (capacité, paramètres finaux, modèle, version du module, seed, durée). VertIA n'écrit jamais dans le dossier d'une session : la session copie elle-même.
4. Retour de la session : `valide` clôt la demande ; `a_refaire` + motif relance un essai (paramètres ajustés) jusqu'au plafond ; au plafond, état `plafond`, code 11, signalement à VertIA.
5. Journal : tables SQLite `demandes`, `essais`, `retours` ; export `outbox/journal.jsonl` pour l'analyse (taux de validation au premier essai par capacité et par session, motifs fréquents).
6. Rétention : `outbox/` purgé des demandes validées depuis plus de 30 jours **[décidé]**.

## 7. GPU : deux niveaux d'arbitrage
- Dans VertIA : `GpuArbiter` (un moteur à la fois) + `JobQueue` (ordre des jobs).
- Entre sessions : `vram_lock.py` reste la source unique tant qu'il existe des sessions hors VertIA. Le serveur VertIA prend le jeton `vertia` (note = session demandeuse et capacité) quand un job GPU démarre et le rend après inactivité (`engine_idle_seconds`). L'ordre d'urgence de l'utilisateur s'applique aux demandes de la file VertIA (rang de la session demandeuse).
- Les tâches longues (entraînement creation_llm, phase 11) deviennent des jobs VertIA interruptibles avec point de reprise ; `vram_guard`/`reprise_auto` sont repris à ce moment-là.

## 8. Entrées utilisateur
`FileStore` n'accepte que les fichiers générés. Ajout : import d'un fichier par l'UI (glisser-déposer) ou dépôt dans `inbox/`, enregistré comme fichier « fourni » (type, empreinte), utilisable comme entrée d'une capacité (retouche d'image, image vers 3D). Nécessaire pour la demande de retouche de la session jean-luc-dariol.

## 9. CreaZik_V3
Préférences calculées côté CreaZik (votes de la webradio, `regles_modeles.json`) ; VertIA reçoit des paramètres déjà résolus par `musique.generer` (API v1). VertIA reste générique et ne connaît pas la webradio **[décidé]**.

## 10. Archivage des dépôts (avant suppression, phase 12)
1. Prérequis : travail non poussé traité (décision 4 de l'inventaire : pousser, archiver ou abandonner).
2. Dépôt git : `git bundle create <projet>.bundle --all`, puis `git bundle verify`, puis clone de test depuis le bundle.
3. Fichiers hors git (non suivis, non ignorés) : zip, sans `.venv`, caches ni poids (ceux-ci sont déjà dans `models/`).
4. Empreintes SHA-256 et inventaire (`MANIFEST.txt` : date, commit HEAD, branches, taille).
5. Destination : `D:\ServOMorph\_archives\<projet>_<date>\` **[décidé]** ; push vers le distant en plus s'il existe.
6. Suppression du dossier d'origine seulement après accord écrit de l'utilisateur, projet par projet.

## 11. Décisions complémentaires et points ouverts
- **[décidé]** Une seule installation ComfyUI (`engines/comfyui`, union des nœuds de ComfyUI-Qwen et ComfyUI-SANA) au lieu de deux : moins de disque et un seul serveur, au prix d'un contrôle de compatibilité des nœuds en phase 4.
- Les autres « à qualifier » de l'inventaire (chat, animation 3D) sont tranchés à l'ouverture de leur phase.
