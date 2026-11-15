# Mémoire projet
<!-- Fichier géré via /create_memory. Ne pas modifier manuellement sauf pour supprimer des entrées. -->

## 2026-11-15 — Reprise creation_llm vérifiée
Chaque fois que creation_llm reprend le jeton GPU après une pause, vérifier qu'il est bien reparti : nouvelle ligne `step N` dans `_orchestration/state/reprise_sortie.log`, REPRISE_OK dans `reprise.log`, aucune alerte dans `vram_lock.py status`. Sinon, le faire repartir sans demander (`reprise_auto.py --apres-pause`, sauf pause utilisateur active). Ne solliciter l'utilisateur que pour un problème majeur (échec persistant après relance, disque, GPU ou pilote en défaut, checkpoint illisible). Contrôle automatique : `_orchestration/verif_reprise.py` ; consulter les alertes à chaque réveil de la session.
