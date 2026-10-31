---
description: Vérifie les prérequis de mise en production de VertIA et affiche la checklist
allowed-tools: Read, Bash(python --version), Bash(git status*), Bash(git describe*), Bash(curl *), PowerShell(Get-Command *), PowerShell(Test-Path *)
---

# /mise_en_prod

1. Lire `MISE_EN_PROD.md` à la racine.
2. Pour chaque prérequis et moteur externe, exécuter une commande de contrôle (version Python, présence d'Ollama, existence des dossiers configurés dans `.env` ou `.env.example`, ports) et noter OK / MANQUANT.
3. Comparer `.env.example` et `.env` : lister les variables absentes de `.env` (noms seulement, jamais les valeurs).
4. Vérifier que le dépôt est propre (`git status`) et afficher la version (`git describe --tags --always`).
5. Afficher une checklist synthétique : prérequis, variables, installation, lancement, vérification.
6. Ne rien installer ni modifier. Toute action de déploiement nécessite une confirmation explicite de l'utilisateur.
