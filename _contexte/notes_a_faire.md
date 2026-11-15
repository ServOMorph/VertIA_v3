# Notes à faire (lues par /start, étape 3)

Une ligne par note : date de la demande, échéance, tâche. Supprimer la note une fois faite et validée par l'utilisateur.

- 2026-11-15 | à partir du 2026-11-16 01:00 | Voir si le modèle lfm3 est utilisable et le comparer à gemma4:12b (modèle Ollama par défaut de VertIA, `VERTIA_DEFAULT_MODEL`). Passage par `vram_lock.py` (session vertia, prioritaire sur creation_llm, qui reprend seul ensuite ; vérifier sa reprise selon `.claude/memory.md`). Vérifier d'abord que lfm3 existe dans Ollama ou sur HuggingFace (taille, quantification) ; téléchargement > 20 Go ou < 100 Go libres sur D: : demander à l'utilisateur. Comparer sur un même jeu de prompts : qualité, vitesse (tokens/s), VRAM (8 Go), français. Résultat dans `_docs/` et proposition à l'utilisateur.
