# LFM3 (Liquid AI) : état des lieux pour VertIA

Recherche du 2026-11-16 (sources web citées en fin de document). Les chiffres sont ceux des fiches Hugging Face et de l'annonce du fournisseur ; ils n'ont pas été mesurés sur cette machine. Aucun test d'exécution n'a encore eu lieu (voir « Blocage »).

## La famille
LFM3 est sortie le 2026-10-27 : six modèles open-weight d'environ 2 milliards de paramètres, issus d'une base commune (LFM3-1.7B-Base, 22 000 milliards de tokens).

| Modèle | Entrées | Sorties | Contexte | Taille GGUF Q4_K_M (+ mmproj) |
|---|---|---|---|---|
| LFM3-1.7B | texte | texte | 256 K | 1,1 Go |
| LFM3-VL-2B | texte, images, vidéo | texte | 128 K | 1,1 Go + 0,2 Go (Q8_0) |
| LFM3-Audio-2B | texte, audio | texte, parole | 32 K | 1,1 Go + 0,17 Go |
| LFM3-Omni-2B | texte, images, vidéo (avec ou sans son), audio | texte, parole | 32 K | 1,1 Go + 0,29 Go |
| d1-2B, d1-omni-2B | texte, images, vidéo (+ audio) | réponses structurées calibrées | non relevé | non téléchargés |

## Fonctionnalités par usage
- **Texte (LFM3-1.7B)** : 16 langues, dont le français (confirmé sur les fiches VL et Omni, non listé en toutes lettres sur la fiche texte). Annoncé fort en suivi de consignes (IFEval 96,7), appels d'outils (BFCL V4 71,4) et code court (LiveCodeBench v6 73,5) ; faible en raisonnement long et en connaissances (GPQA Diamond 63,4, RULER 128K 65,6). Le fournisseur le déconseille pour le code agentique et le raisonnement en plusieurs étapes. Poids 1 Go en 4 bits, cache de contexte 1,6 Go pour 128 K.
- **Vision et documents (VL-2B)** : images à résolution native, OCR et documents (DocVQA 96,7 ; OCRBench 86,3), raisonnement dans un bloc de réflexion. Déconseillé pour le code et les conversations en plusieurs tours.
- **Vidéo (VL-2B, Omni-2B)** : premier modèle vision de la famille à accepter la vidéo, échantillonnée à 2 images par seconde. Avec llama.cpp, le rythme est fixe (4 à 768 images pour VL, soit environ 6,4 minutes ; 4 à 384 pour Omni) et ffmpeg est nécessaire. La vidéo est de la compréhension (questions sur un clip), pas de la génération.
- **Voix (Audio-2B, Omni-2B)** : reconnaissance vocale multilingue (WER anglais 6,23 %, multilingue 6,03 %), synthèse vocale 24 kHz avec choix de voix « female » ou « male » par consigne, pas de clonage mentionné, premier token en 50 ms annoncé. Le français figure dans la liste des langues de synthèse, mais le dialogue vocal et la transcription en direct sont limités à l'anglais.
- **Décision (d1)** : classification et notation avec réponses structurées calibrées ; sans intérêt direct pour VertIA aujourd'hui.

## Ce que cela change pour le portail
- Texte : candidat léger à côté de gemma4:12b (7,6 Go de VRAM) : 1,1 Go de poids laisserait de la place à un autre moteur sur 8 Go. À valider en français sur des tâches réelles de VertIA (titres, résumés, extraction, appel d'outils).
- Voix : brique manquante du portail (phase 5, « voix »). Transcription multilingue et synthèse en français à tester ; la conversation vocale en français n'est pas annoncée.
- Vision et vidéo : lecture de scans, de documents et de clips pour le portail (par exemple décrire une image avant retouche dans l'Atelier). Pas de génération d'image ni de vidéo.
- Omni : un seul modèle de 2,2 milliards de paramètres pour voix, image et vidéo en entrée ; plus économique que trois moteurs séparés si la qualité suffit.

## Licence
LFM Open License v1.0 : usage commercial réservé aux entités de moins de 10 millions de dollars de chiffre d'affaires annuel (entités liées incluses) ; redistribution avec la licence et mention des modifications ; usage de recherche et non commercial possible sous conditions. Ce n'est pas une licence open source au sens de l'OSI. À relire en entier avant tout usage commercial ou toute redistribution (le projet est destiné à rester privé tant que ce n'est pas tranché).

## Exécution locale
- Poids GGUF officiels pour llama.cpp (build b11960 ou plus récent). Ollama 0.31.2 est installé sur cette machine ; les sources parlent d'une prise en charge LFM3 à partir d'Ollama 0.40.12 (annoncée pour macOS), non confirmée sur Windows : l'installé est probablement trop ancien.
- Poids téléchargés dans `models/llamacpp/lfm3/` (non versionné) : texte Q4_K_M, VL Q4_K_M + mmproj Q8_0, Audio Q4_K_M + mmproj Q4_K_M, Omni Q4_K_M + mmproj Q4_K_M (environ 5,1 Go en tout).
- Le plan de comparaison avec gemma4:12b (mêmes consignes en français, vitesse en tokens par seconde, VRAM, qualité jugée sur grille) passe par le verrou GPU (session `vertia`, priorité sur creation_llm).

## Blocage
Pour exécuter ces GGUF il faut un moteur récent : soit les binaires llama.cpp (release b12427, archive CUDA 13.5 Windows x64 du dépôt officiel ggml-org/llama.cpp, à décompresser dans `engines/llamacpp/`, non versionné), soit la mise à jour d'Ollama (installation système). Le téléchargement des binaires a été refusé par le contrôle d'autorisation de la session ; l'accord de l'utilisateur donne le feu vert pour les poids, pas pour un programme exécutable. Décision demandée à l'utilisateur.

## Sources
- Annonce : https://www.liquid.ai/blog/lfm3
- Fiches Hugging Face : LiquidAI/LFM3-1.7B-GGUF, LFM3-VL-2B, LFM3-Audio-2B, LFM3-Omni-2B
- Revue de la licence et du déploiement : https://aicybr.com/blog/liquid-ai-lfm3-1-7b-multimodal-local-deployment-license-guide
- Synthèse de presse : https://aiweekly.co/alerts/liquid-ai-opens-six-model-lfm3-family-at-256k-context
