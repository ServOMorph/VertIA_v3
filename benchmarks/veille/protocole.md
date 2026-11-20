# Protocole d'essais comparatifs (veille du 2026-11-19)

Contexte : demande de l'utilisateur relayée par VibeObs (2026-11-19), après les rapports `veille/2026-11-19*.md`.
Règles : jeton GPU `vertia` par `_orchestration/vram_lock.py` (45 min au plus, VRAM sous 7,5 Go, `release vertia` en fin de lot), aucun téléchargement sans accord de l'utilisateur, aucune licence supposée commerciale.

## Critères communs
- VRAM mesurée : pic de `nvidia-smi` pendant la génération moins la ligne de base relevée avant le lot (le jeton étant tenu, creation_llm est en pause).
- Vitesse : chat en jetons par seconde (`eval_count / eval_duration`), image et vidéo en secondes par génération (durée mur, hors chargement et chargement compris, les deux notés).
- Qualité : jugée par Claude sur les mêmes cas, grille 0 à 2 par critère, avec les limites d'un juge unique ; les contrôles automatiques sont notés à part.
- Tout résultat non mesuré est écrit « non mesuré ».

## Lot 1 : chat (Ollama, modèles déjà présents)
Modèles : gemma4:12b (référence actuelle), gemma4:12b-32k, gemma4:e4b, qwen3.5:latest (9b). granite4.2:8b est absent : téléchargement à demander.
Paramètres fixes : `num_ctx` 8192, `temperature` 0, `seed` 7, `think` désactivé, `keep_alive` 0 (déchargement après chaque modèle), un essai à vide de chargement avant la mesure.
Cas (français, fichier `cas_chat.json`) : 1 résumé en deux phrases ; 2 extraction JSON (contrôle automatique : JSON valide, trois valeurs exactes) ; 3 problème à réponse unique (contrôle automatique : valeur exacte) ; 4 consigne stricte « un seul mot » (contrôle automatique) ; 5 rédaction d'un courriel de cinq lignes (jugement : correction du français, accents, ton, respect de la longueur).
Sortie : `resultats_chat.json`, puis tableau dans le rapport.

## Lot 2 : image (ComfyUI, poids déjà présents)
Modèles présents : Qwen-Image 2.1 Q4_K_M (référence actuelle, via le portail) et Z-Image Turbo Q4_K_M (poids dans `models/comfy/unet`). MOSS-Image et FLUX 3 Klein : poids absents, téléchargement à demander.
Cas : 3 prompts fixes (scène avec texte en français lisible, portrait, objet sur fond transparent ou uni), seed 0, 1024x1024, étapes par défaut du modèle.
Sortie : images dans `benchmarks/veille/image/`, durée et pic de VRAM par image.

## Lot 3 : vidéo (poids déjà présents)
Modèles présents : Wan 2.1 14B int8 via Wan2GP (référence actuelle, via le portail) et Wan 2.2 TI2V-5B Q4_K_M (`models/comfy/unet`). 
Cas (trois, identiques pour tous les modèles, à valider par l'utilisateur avant tout essai vidéo) :
1. Sujet simple : « Une tasse de café fumante posée sur une table en bois près d'une fenêtre, lumière du matin, plan fixe. »
2. Mouvement de caméra : « Travelling avant lent dans une forêt de sapins couverte de brume, lumière douce traversant les branches. »
3. Scène avec personnage : « Une femme en manteau rouge marche dans une rue pavée sous la pluie, elle ouvre un parapluie, plan moyen. »
Paramètres : 832x480, 17 images pour borner le temps, seed 0. Critères de jugement : cohérence du sujet, stabilité temporelle, respect du prompt, artefacts (grille 0 à 2).
Sortie : clips dans `benchmarks/veille/video/`, durée et pic de VRAM.

## Ordre et garde-fous
Lot 1 d'abord (le plus fiable à mesurer). Lots 2 et 3 seulement si l'intégration ComfyUI sans modification du portail est faisable ; sinon, constat écrit dans le rapport.
