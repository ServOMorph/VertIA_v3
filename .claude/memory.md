# Mémoire projet
<!-- Fichier géré via /create_memory. Ne pas modifier manuellement sauf pour supprimer des entrées. -->

## 2026-11-15 — Contrôle reprise creation_llm après VibeObs
Contrôle demandé par l'utilisateur : quand il lance une nouvelle session VibeObs (qui prend le jeton GPU), tester que creation_llm se met en pause puis repart seul. Au démarrage, demander si la session VibeObs a été lancée ; si oui, relire `_orchestration/state/journal.log` (PAUSE_DEMANDEE par vibeobs, LIBERE creation_llm, JETON vibeobs, LIBERE vibeobs, JETON creation_llm), `_orchestration/state/reprise.log` (REPRISE_OK avec un pas supérieur à celui d'avant) et `vram_lock.py status` (aucune alerte REPRISE_KO). Le contrôle automatique est `_orchestration/verif_reprise.py`.
