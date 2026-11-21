# Roadmap — Portail IA locale (consolidation des projets solo dans VertIA)

Objectif : regrouper sous `D:\ServOMorph\VertIA_v3\` tout le travail d'IA locale, piloté par une UI unique et exposé comme service aux autres sessions Claude, puis supprimer les projets solo.

## Cadrage (décisions utilisateur du 2026-11-13)
1. Copie seule : VertIA n'écrit jamais dans les dossiers d'origine ; suppression en fin de roadmap, projet par projet, avec accord.
2. Inventaire : D: et C: (caches HuggingFace, Ollama, etc. compris), lecture seule.
3. Sessions orchestrées : fermées après migration de leur projet ; VertIA devient l'unique session de R&D IA locale.
4. Git : code importé en un commit ; ancien dépôt archivé (zip ou distant) avant suppression ; pas de fusion d'historique.
5. Public : l'utilisateur d'abord. VertIA est l'atelier ; les produits pour novices sont des dépôts séparés qui réutilisent ses briques.
6. Service aux autres sessions : CLI `vertia_gen.py` (pas de MCP), client léger de l'API VertIA (localhost), passage par la file de jobs et le jeton GPU, sortie = chemin du fichier produit sur une ligne, codes de sortie explicites. Démarrage automatique du serveur VertIA si absent.
7. Autonomie : validation par phase (checkpoint) ; seuils de sollicitation inchangés (téléchargement > 20 Go, < 100 Go libres sur D:, installation système, suppression de données, dépense).
8. Modules cibles : chat, image, musique, vidéo, 3D, animation 3D, entraînement de LLM (avec utilisation des LLM créés), WorldModel, voix (TTS_Local : Chatterbox, Kokoro ; whisper), ajouté le 2026-11-14 et rattaché à la phase 5 (CreaZik utilise Chatterbox pour ses jingles).
9. Musique : génération ACE-Step et système d'apprentissage de CreaZik_V3 basculés dans VertIA ; CreaZik_V3 devient client de VertIA via un contrat d'API versionné. Génération uniquement sur la machine de l'utilisateur (la version distribuée de CreaZik ne génère pas) : pas d'empaquetage moteur.
10. Exception : VertIA est autorisé à modifier CreaZik_V3 pour le seul branchement à VertIA.
11. Poids de modèles : déplacés vers `VertIA/models/`, l'original pointe dessus par jonction Windows (exception à la copie seule, limitée aux poids). Poids et checkpoints de creation_llm intouchés tant que l'entraînement tourne.
12. Ordre : image, musique, vidéo, chat, 3D, animation 3D, WorldModel, creation_llm.

Arborescence cible (à confirmer en phase 2) :
```
VertIA_v3/
  src/       portail (git)
  modules/   code repris des projets solo (git)
  engines/   installations tierces : ComfyUI, ACE-Step... (hors git)
  models/    poids partagés entre moteurs (hors git)
  outputs/   fichiers générés (hors git)
```

## Prérequis
- Revue et commit des phases Codex 1 à 8 (action P1 de `_contexte/signals.md`, `_docs/archives/roadmap_vertia_v1.md`).
- Mise à jour de `.claude/CLAUDE.md` (section Spécificités projet) selon les décisions 1, 3, 10 et 11, validée par l'utilisateur.

## Modèles par phase (efficacité et abonnement)

| Phase | Pilotage | Exécution |
|---|---|---|
| 1 Inventaire | Sonnet | scripts locaux |
| 2 Architecture cible | Opus (Fable 5.2 seulement si blocage de conception) | — |
| 3 Socle, CLI, accueil UI | Opus | Codex |
| 4 Image (pilote) | Opus | Codex |
| 5 Musique et CreaZik | Opus | Codex |
| 6 Vidéo | Sonnet | Codex |
| 7 Chat | Sonnet | Codex |
| 7-bis Demandes du 2026-11-19 | Opus (Sonnet pour le seul design du chat) | Codex |
| 8 3D | abandonnée | — |
| 9 Animation 3D | abandonnée | — |
| 10 WorldModel | abandonnée | — |
| 11 creation_llm | Opus | Codex |
| 12 Nettoyage du disque | Sonnet | — |

Règles transverses :
- `/start` : Haiku. `/close` et commits : Sonnet. Messages de commit, changelogs : Ollama (`ollama_call.py`).
- Changer de modèle au checkpoint de phase, juste après `/compact`, pas en cours de phase.
- Phases Sonnet : repasser sur Opus uniquement en cas d'incident (casse, conception imprévue).
- Fable 5.2 : jamais par défaut.
- Codex et OpenCode : modèle et effort choisis à chaque délégation selon `_docs/benchmark_agents.md` (le plus adapté au type de tâche) ; benchmark relancé quand un nouveau modèle apparaît (`opencode models`, config Codex) ou quand un modèle échoue deux fois sur un même type de tâche.

Règles communes aux phases de migration (4 à 11) :
- Copie du code, venv recréé (jamais déplacé), chemins en dur corrigés, poids déplacés avec jonction.
- Page du module dans l'UI portail.
- Tests de non-régression : le module produit dans VertIA le même résultat que le projet d'origine.
- Ancien dossier conservé ; session correspondante fermée après validation.

## Phase 1 — Inventaire D: et C: (lecture seule) [FAIT]
**Modèle Claude à sélectionner :** Sonnet 5.5. Passer sur ce modèle juste après le `/compact` du checkpoint précédent.
- Projets d'IA locale : rôle, état (actif / abandonné), taille, dépôt git (propre, non poussé), venv et version Python, dépendances.
- Modèles et caches (HuggingFace, Ollama, ComfyUI...) sur D: et C: : taille, doublons.
- Chemins absolus en dur (scripts, config, tâche Windows `VertIA_reprise_auto`, CLAUDE.md).
- CreaZik_V3 : nature exacte des paramètres et du système d'apprentissage musical.
- Espace libre sur D: et estimation de l'espace nécessaire.
- Livrable : `_docs/inventaire_ia_locale.md`, avec une proposition par projet : `modules/`, `engines/` ou archive.
- Gate : inventaire relu et décision par projet validée par l'utilisateur.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 2 — Architecture cible [FAIT]
**Modèle Claude à sélectionner :** Opus 5.5. Passer sur ce modèle juste après le `/compact` du checkpoint précédent.
- Arborescence définitive, contrat de module (déclaration, capacités, besoins VRAM, adaptateur), `models/` partagé et jonctions, config des chemins.
- Contrat CLI / API versionné (commandes, codes de sortie, timeout, démarrage automatique).
- Boucle demande / génération / retour (décision utilisateur du 2026-11-15, version hybride) : demande avec critère de réussite et nombre d'essais maximal ; livraison dans `outbox/<session>/` (jamais d'écriture dans le dossier d'une session) ; retour de la session (valide / à refaire + motif) ; analyse des frictions par VertIA seulement pour un type de demande nouveau ou après 2 échecs ; journal de chaque demande, essai et retour, pour améliorer les zones et les sessions.
- Procédure d'archivage des dépôts.
- Mise à jour de `_docs/architecture.md`.
- Gate : architecture validée par l'utilisateur.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 3 — Socle, CLI et accueil UI [FAIT]
**Modèle Claude à sélectionner :** Opus 5.5. Passer sur ce modèle juste après le `/compact` du checkpoint précédent.
- Paramètres `-Model` et `-Effort` dans `_codex/run_codex.ps1` (défaut : `gpt-6.1-sol`, `medium`).
- Benchmark des agents : un même jeu de briefs VertIA (revue read-only, code simple, code délicat) soumis aux modèles OpenCode disponibles, Ollama locaux compris, et à Codex en `medium` / `high` ; critères : tests verts, qualité du diff, respect du brief, durée. Résultat et choix par type de tâche dans `_docs/benchmark_agents.md`.
- Pour les modèles Ollama locaux (décision utilisateur du 2026-11-15, remplace « relancé sur ordre écrit ») : toute demande GPU passe avant l'entraînement de creation_llm, qui tourne quand rien d'autre n'est à faire ; le benchmark local a pris le jeton `vertia` et creation_llm a repris seul, contrôlé par `_orchestration/verif_reprise.py`. Fait le 2026-11-16 : synthèse dans `_docs/benchmark_agents.md`.
- Dossiers, `.gitignore` (engines, models, outputs), registre de modules, résolution des chemins par config.
- `vertia_gen.py` : soumission de job, démarrage automatique du serveur, attente, sortie sur une ligne.
- Boucle demande / retour dans `vertia_gen.py` : `outbox/<session>/`, commande de retour, plafond d'essais, journal ; tests (succès au premier essai, refus puis succès, plafond atteint).
- Écran d'accueil du portail (choix d'activité), alimenté par le registre.
- Tests : registre, chemins, module factice, CLI (serveur absent, GPU occupé, timeout, succès).

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 4 — Image (pilote) [FAIT]
**Modèle Claude à sélectionner :** Opus 5.5. Passer sur ce modèle juste après le `/compact` du checkpoint précédent.
- Migration du moteur image (ComfyUI / Qwen) selon les règles communes.
- `vertia_gen.py image` opérationnel ; ligne d'usage ajoutée au CLAUDE.md de VertIA, proposée aux autres sessions par message.
- Procédure de migration écrite dans `_docs/` pour les phases suivantes.
- Bilan de dette : décider s'il faut une phase de refacto avant la phase 5.
- Atelier (éditeur d'image type Canva + Photoshop, demande utilisateur du 2026-11-15) : la v1 autonome, faite avant la phase 3 pour la demande de jean-luc-dariol, devient un module du portail (registre, import `inbox/`, retouche IA par masque via la file GPU).
- Faits le 2026-11-16 : module `modules/image` (`image.generer`, `image.retoucher`), poids ComfyUI-Qwen déplacés vers `models/comfy/` avec jonctions (54 Go, `outils/deplacer_poids.py`), verrou GPU pris par le portail, essais réels (génération identique pixel pour pixel à la référence ; retouche par masque : hors masque identique), procédure `_docs/migration_module.md`, ligne d'usage dans `CLAUDE.md`.
- Bilan de dette : pas de phase de refacto dédiée avant la phase 5. À absorber : moteur Qwen sans besoin VRAM déclaré (jeton demandé à 8 Go par défaut), module image sans page propre dans l'UI (tuile d'accueil seulement).
- Reporté : diffusion de la ligne d'usage aux autres sessions (utilisateur, 2026-11-16 : une seule fois quand musique et voix seront dans le portail) ; contrôles manuels de l'interface Atelier (`tests_manuels.md`, 9 à 11).

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 5 — Musique, voix et branchement CreaZik_V3 [FAIT]
**Modèle Claude à sélectionner :** Opus 5.5. Passer sur ce modèle juste après le `/compact` du checkpoint précédent.
- Module voix : migration de TTS_Local (Chatterbox, Kokoro) et de whisper selon les règles communes ; `vertia_gen.py voice`.
- Migration d'ACE-Step et du système d'apprentissage de CreaZik_V3. Précision de l'inventaire : ce système est un calcul de préférences sur les votes de la webradio, pas un entraînement ; le contrat d'API précise où vit ce calcul (décision de phase 2).
- `vertia_gen.py music` et API musique versionnée.
- Modification de CreaZik_V3 (exception décision 10) pour qu'il génère via VertIA ; aucune autre écriture dans CreaZik_V3.
- Tests : génération identique avant/après, entraînement reproductible, CreaZik_V3 fonctionnel via VertIA.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 6 — Vidéo [FAIT]
**Modèle Claude à sélectionner :** Sonnet 5.5. Passer sur ce modèle juste après le `/compact` du checkpoint précédent.
- Migration du projet creation_videos selon les règles communes ; `vertia_gen.py video`.
- Clips longs non interruptibles : blocs GPU entiers.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 7 — Chat [FAIT]
**Modèle Claude à sélectionner :** Sonnet 5.5. Passer sur ce modèle juste après le `/compact` du checkpoint précédent.
- Clôture de la phase 1 de `_docs/archives/roadmap_vertia_v1.md` et intégration du chat comme module du portail.
- Reprise des éléments IA_V7 non encore portés, selon l'inventaire.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 7-bis — Demandes de l'utilisateur du 2026-11-19 (ajoutées en session) [EN COURS]
**Modèle Claude à sélectionner :** Opus 5.5 (VRAM à l'ouverture de l'UI, préchargement sous jeton, retouche dialoguée) ; Sonnet 5.5 pour le design du chat repris d'IA_V7. Passer sur ce modèle juste après le `/compact` du checkpoint précédent.
- Correction de la retouche IA par masque (Atelier) : échec « moteur » constaté le 2026-11-19, lecture de l'encodeur de texte (16,7 Go) en erreur mémoire ; corriger puis vérifier une retouche de bout en bout (test manuel 165 de `tests_manuels.md`). Fait le 2026-11-19 côté portail (cause : sous-processus asyncio indisponible sous le serveur à rechargement ; correctif dans `verrou.py`) ; reste le test manuel dans l'Atelier.
- État au 2026-11-20 : les quatre demandes ci-dessous et le point `gemma4:e4b` sont codés et commités (1df9546, 098dbf9, 6a68c13, d112ba9, 56d0e81 ; 1070 tests verts). Gate benchmark de la retouche dialoguée atteint le 2026-11-20 (21/24 zones IoU >= 0,5, JSON 6/6, `benchmarks/retouche_gate/`, commit 8ce600a ; références tracées par Claude, à valider). Restent : contrôles manuels à l'écran (`tests_manuels.md`, références du gate comprises), correction du `keep_alive` -1 dans la session VisioAide (client identifié, `AIDE_VISIO_OLLAMA_KEEP_ALIVE`).
- Libération de la VRAM au lancement de l'UI de VertIA : l'utilisateur doit pouvoir se servir des LLM locaux depuis l'UI ; une fonction met en pause ou libère le GPU (jeton `vertia`, pause de creation_llm) à l'ouverture de l'UI et le rend à la fermeture.
- Design du chat : reprendre celui d'IA_V7 (disposition, couleurs, polices identiques), le design actuel ne convient pas à l'utilisateur.
- Outil de retouche d'image dialoguée : partager une image, discuter avec un LLM local (modèle de vision) pour proposer des améliorations et des zones ; après validation de l'utilisateur, déclenchement des générations Qwen par zone (capture de la zone, génération, remplacement en calque). Limites relevées : un seul modèle à la fois sur 8 Go, texte manuscrit difficile, repérage de zones à tester.
- Avec la libération de la VRAM : identifier le client qui charge `gemma4:e4b` en « Forever » (suspects : Aide_Visio, `keep_alive` -1 ; préchargement du portail hors `--headless`) et faire passer le préchargement par le jeton GPU (`src/vertia/engines/ollama_preload.py`). Déclarer le besoin VRAM du moteur Qwen (`src/vertia/engines/comfy_qwen.py`, test ajouté).

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 7-ter — LFM3 comme utilitaire texte et vision (décision utilisateur du 2026-11-20) [TODO]
**Modèle Claude à sélectionner :** Opus 5.5 (moteur llama.cpp sous jeton GPU, routage) ; Sonnet 5.5 pour les tests et l'intégration UI.
- Décision : LFM3-1.7B (texte) et LFM3-VL-2B (vision, OCR) deviennent des utilitaires légers (2,3 à 2,9 Go de VRAM) ; gemma4:12b reste le modèle de discussion. Voix (Audio-2B, Omni-2B) hors périmètre. Base : `_docs/lfm3.md`.
- Moteur llama.cpp (`engines/llamacpp/`, b12427) branché au portail sous le jeton GPU, poids `models/llamacpp/lfm3/`.
- Routage des tâches courtes et cadrées vers LFM3 (titres, résumés, extraction, choix d'outil, réécriture de prompt) ; réflexion à cadrer (boucle avec, réponses moins fiables sans).
- Vision : OCR et description d'image par LFM3-VL ; comparer avec qwen2.5vl pour le repérage de zones de la retouche dialoguée avant tout remplacement.
- Licence LFM Open License v1.0 (usage commercial < 10 M$ de CA) à garder en tête avant toute distribution.
- Tests : unitaires du moteur et du routage, puis benchmark à cas verrouillés (qualité et vitesse face à gemma4:12b sur les tâches routées).

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Actions ouvertes hors phase (classées du plus urgent au moins urgent, 2026-11-20)
Source unique des actions depuis le 2026-11-20 (signals et backlog y renvoient). Retirer un point une fois fait.
1. Contrôles manuels à valider (`tests_manuels.md`) : retouche IA et logo (sections « Retouche IA et logo » et « Atelier dans le portail », Atelier v1 points 9 à 11), GPU réservé, design du chat, retouche dialoguée ; conditionne la fin de la phase 7-bis. Inclut la validation des références du gate (`benchmarks/retouche_gate/references.json`).
2. Diffuser une fois la ligne d'usage du portail (`vertia_gen.py`) aux autres sessions : VibeObs refuse de relayer (2026-11-21) : envoi direct par VertIA à chaque session concernée quand elle est en ligne (décision utilisateur) (l'option `--note` n'existe pas dans `vertia_gen.py`) ; message à jean-luc-dariol (scan abandonné, images à la main, retouche IA disponible) ; trois validations utilisateur pour toucher le CLAUDE.md d'une autre session.
3. Fermer les sessions creation_videos (migration validée en phase 6), creation_3d et WorldModel (abandonnés le 2026-11-20).
4. Renouveler la pause Windows Update avant le 2026-12-18 si creation_llm s'entraîne encore.
5. Reprise auto de creation_llm après un vrai redémarrage Windows : à constater au prochain redémarrage (ligne dans `_orchestration/state/reprise.log`, `tests_manuels.md`, « Reprise auto après redémarrage ») ; sans objet si l'entraînement se termine avant.
6. FLUX 3 Klein : licence à accepter et jeton à fournir par l'utilisateur, puis essai dans `engines/comfy-flux3` (~11 Go, ComfyUI 0.46.0 jamais lancé : vérifier la prise en charge de FLUX 3) ; résultat dans `benchmarks/veille/rapport_resultats.md`.
7. MemoryError de l'encodeur Qwen sous pression de RAM : options ComfyUI `--disable-pinned-memory` ou `--disable-dynamic-vram` si l'erreur revient.
8. Page d'interface dédiée au module image, ou besoin écarté.
9. Licence Qwen Research de Qwen-Image 2.1 à lire avant tout usage commercial.
10. Benchmark agents : tâches plus discriminantes, T1 OpenCode rejoué avec contrôle des fichiers.
11. 9 dépôts avec travail non poussé : traité en phase 12 (archivage avant suppression).

## Phases 8 (modélisation 3D), 9 (animation 3D) et 10 (WorldModel) [ABANDONNÉ]
- Décision utilisateur du 2026-11-20 : creation_3d et WorldModel arrêtés, les résultats montrant qu'aucun outil local n'est assez performant pour la machine (RTX 4060 8 Go). Aucune migration ; les projets sont traités en phase 12.

## Phase 11 — Entraînement de LLM et LLM créés [TODO]
**Modèle Claude à sélectionner :** Opus 5.5 (migration de checkpoints et de la reprise auto : risque de perte). Passer sur ce modèle juste après le `/compact` du checkpoint précédent.
- Uniquement après la fin du pré-entraînement en cours.
- Migration de creation_llm, de ses checkpoints, de `reprise_auto.py`, `reprise.json` et de la tâche Windows.
- LLM créés utilisables dans le chat VertIA (export vers Ollama ou moteur équivalent).
- Tests : reprise auto sur le nouveau chemin, reprise d'entraînement depuis un checkpoint, LLM créé répondant dans le chat.

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.

## Phase 12 — Nettoyage du disque [TODO]
**Modèle Claude à sélectionner :** Sonnet 5.5 (suppressions une par une, accord explicite). Passer sur ce modèle juste après le `/compact` du checkpoint précédent.
- Archivage puis suppression des projets solo migrés et des projets abandonnés (creation_3d, WorldModel), un par un, avec accord explicite pour chacun ; avant archivage, audit d'historique `pre_push_check.py --audit` et push des 9 dépôts au travail non poussé.
- Suppression des poids en double et des jonctions devenues inutiles.
- Fin de l'orchestration multi-sessions (`_orchestration/sessions.md`, `protocole.md` ; roadmap d'origine archivée dans `_docs/archives/roadmap_orchestration.md`).

**⏸ Checkpoint** — Demander à l'utilisateur de faire `/compact` avant de continuer.
Attendre sa réponse écrite. Ne pas commencer la phase suivante sans confirmation.
