# Signals — vertia   (MAJ 2026-11-19)

## Actions ouvertes
<!-- ≤ 20 entrées (ligne « Backlog » exclue) ; dette et findings non urgents -> _contexte/backlog.md -->
Toutes les actions et le backlog sont suivis dans `roadmap_portail.md` (phase 7-bis et section « Actions ouvertes hors phase »), depuis le 2026-11-20.

## Contexte chaud
- Pause GPU utilisateur : non ; creation_llm repris (REPRISE_OK pas 40590 à 21:16 le 2026-11-19). Un `unhold` ne se fait que sur ordre de l'utilisateur.
- Jeton GPU : état courant par `python _orchestration/vram_lock.py status`.
- Portail relancé le 2026-11-19 en headless (code avec correctifs, sortie dans `data/logs/portail.err`) ; l'Atelier de l'utilisateur a été fermé par ce redémarrage. L'UI avec rechargement automatique (`run.py`) prend désormais le jeton GPU sans erreur (repli en thread).
- 2026-11-19 : wrapper Codex remplacé par la version du kit v7.2 (politique centrale, verrou, seuils 50 % / 60 %), sur proposition de VibeObs et validation de l'utilisateur ; `run_codex.ps1 -Statut` : modèle gpt-6.2-sol, sous les seuils, flag de blocage en place ; `_codex/garde_codex.sh` ajouté.
- 2026-11-19 : section « Modèle Codex » d'AGENTS.md réécrite (modèle imposé par ~/.codex/politique_delegation.json) sur proposition de VibeObs, après les trois validations de l'utilisateur dans cette session.
- Résidus non commités : dossiers `.codex-test-*` (accès refusé), `.tmp_*`.

## Dernière session (2026-11-19)
# Session du 2026-11-19 (journal du 2026-11-16 au 2026-11-19 intégré)

## Décisions prises
- Phases 5 (voix, musique, branchement CreaZik), 6 (vidéo WanGP, Atelier dans le portail) et 7 (chat, module chat.generer, ports IA_V7) livrées ; la phase 7 reste à confirmer par `/compact`.
- Veille et benchmarks (chat, image, vidéo) faits sous jeton ; FLUX 3 Klein sauté (licence à accepter par l'utilisateur), MOSS-Image bloqué (ComfyUI 0.38.0).
- Demandes du 2026-11-19 rangées en phase 7-bis : VRAM libérée au lancement de l'UI, design du chat d'IA_V7, retouche dialoguée, correction de la retouche IA.
- Copie séparée de ComfyUI (engines/comfy-flux3, v0.46.0) autorisée pour FLUX ; logo VertIA remplacé par l'arbre-circuit de l'utilisateur.
- Délégation Codex : wrapper du kit v7.2 appliqué (0a10d23) et section « Modèle Codex » d'AGENTS.md réécrite (16aeed6) sur proposition de VibeObs, après validation de l'utilisateur (trois validations pour AGENTS.md).

## Livrables produits ou modifiés
- Modules voix, musique, vidéo, chat, Atelier intégré : faits et commités (voir CHANGELOG v0.4.0).
- Correctifs retouche IA : verrou GPU en repli thread sous boucle Selector (cause du NotImplementedError dans l'UI à rechargement), erreur jamais vide, journal de ComfyUI dans `data/logs/comfy_qwen.log`, trace des échecs de demande ; 930 tests verts.
- `veille/`, `benchmarks/veille/` : créés, non versionnés.

## Hypothèses validées / invalidées
- VALIDE : retouche IA par masque livrée par le portail (10 min, session de test) une fois l'ancienne instance arrêtée.
- INVALIDE : cause mémoire seule de l'échec de retouche -> l'échec dans l'UI venait du sous-processus asyncio sous Windows ; l'erreur mémoire de l'encodeur (16,7 Go) reste possible sous pression de RAM.
- EN ATTENTE : test manuel de la retouche dans l'Atelier, design du chat, FLUX 3 Klein.

## Prochaine étape exacte
`/compact`, puis phase 7-bis (libération de la VRAM à l'ouverture de l'UI, design du chat d'IA_V7).

## Question bloquante pour la session suivante
Supprimer ou garder granite4.2:8b et `models/veille/` ?
