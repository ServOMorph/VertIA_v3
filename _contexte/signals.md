# Signals — vertia   (MAJ 2026-11-21)

## Actions ouvertes
<!-- ≤ 20 entrées (ligne « Backlog » exclue) ; dette et findings non urgents -> _contexte/backlog.md -->
Toutes les actions et le backlog sont suivis dans `roadmap_portail.md` (phase 7-bis et section « Actions ouvertes hors phase »), depuis le 2026-11-20.
- [à transférer vers visioaide] `gemma4:e4b` reste chargé « Forever » par le backend VisioAide (`AIDE_VISIO_OLLAMA_KEEP_ALIVE` défaut -1, `config.py:91`) ; à corriger dans cette session, aucune écriture faite chez elle (règle : jamais d'écriture dans les autres sessions). fait quand: la session VisioAide a changé le défaut ou l'utilisateur a tranché. réf: `roadmap_portail.md` phase 7-bis.

## Contexte chaud
- Pause GPU utilisateur : non. Un `unhold` ne se fait que sur ordre de l'utilisateur. Jeton GPU : `python _orchestration/vram_lock.py status`.
- Portail : instance headless démarrée le 2026-11-20 pour les images du gate, répond sur le port 4310 au 2026-11-21 ; 5 demandes image du gate non clôturées par `retour`.
- Jeton `vertia` partagé entre le portail et les scripts : un `acquire` renvoie `DEJA_DETENU` si le portail le tient, puis le portail le rend sans prévenir (creation_llm a repris le GPU pendant le gate). `scripts/benchmark_retouche_gate.py` attend désormais.
- Diffusion de la ligne portail : aucune autre session ne l'a (constaté 2026-11-21). VibeObs a refusé de relayer ; l'utilisateur a choisi la voie du kit, ligne proposée à VibeObs Général comme template (décision séparée, réponse attendue).
- Mode téléphone utilisé cette session, aucune correction de format reçue.
- Résidus non commités : dossiers `.codex-test-*` (accès refusé), `.tmp_*`.

## Dernière session (2026-11-21)
# Session du 2026-11-21

## Décisions prises
- `veille/`, `benchmarks/veille/` et `scripts/benchmark_*_veille.py` versionnés (9210a68).
- LFM3 : utilitaire texte + vision (LFM3-1.7B, LFM3-VL-2B), gemma4:12b reste le modèle de discussion, voix hors périmètre ; nouvelle phase 7-ter [TODO].
- granite4.2:8b supprimé d'Ollama, fichier partiel MOSS-Image supprimé, VAE MOSS gardé (`models/veille/vae`).
- Ligne d'usage du portail proposée à VibeObs Général seul, pour relais aux sessions.

## Livrables produits ou modifiés
- `benchmarks/retouche_gate/` (6 images, `references.json`, `resultats.json`) et `scripts/benchmark_retouche_gate.py` : commités (8ce600a).
- `roadmap_portail.md` (phase 7-ter, actions hors phase 2 à 4 retirées, état 7-bis), `tests_manuels.md` (références du gate), `_contexte/notes_a_faire.md` (note LFM3 retirée) : à jour.

## Hypothèses validées / invalidées
- VALIDE : gate de la retouche dialoguée, 21/24 zones IoU >= 0,5 (87,5 %), JSON valide 6/6 ; échecs : soleil 0,48, escalier 0,45, pins 0,31.
- INVALIDE : `--note` dans `vertia_gen.py` (option inexistante, citée à tort dans la roadmap, corrigée).
- EN ATTENTE : références du gate tracées par Claude, à valider par l'utilisateur ; durées du gate non représentatives (GPU partagé avec creation_llm).

## Prochaine étape exacte
Au PC : dérouler les tests manuels de `tests_manuels.md` (design du chat, GPU réservé, retouche dialoguée, retouche IA et logo, références du gate), puis `/compact` et clôture de la phase 7-bis.

## Question bloquante pour la session suivante
Aucune.
