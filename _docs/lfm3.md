# LFM3 (Liquid AI) : état des lieux pour VertIA

Recherche du 2026-11-16 (sources web citées en fin de document). Les chiffres sont ceux des fiches Hugging Face et de l'annonce du fournisseur ; ils n'ont pas été mesurés sur cette machine. Les mesures locales (texte et vision) sont dans « Mesures sur cette machine » ; voix et vidéo, testées seulement sur le processeur, sont dans la même section.

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

## Mesures sur cette machine (RTX 4060 8 Go, 2026-11-16)
Moteur : llama.cpp b12427 (CUDA 13.5), installé dans `engines/llamacpp/` avec l'accord de l'utilisateur ; poids dans `models/llamacpp/lfm3/`. Script : `outils/comparer_lfm3.py`, résultats bruts : `_docs/lfm3_resultats.json`. GPU pris par la session vertia via `vram_lock.py`, libéré à chaque fois ; creation_llm repart après chaque libération (voir journal du verrou).

### Texte : LFM3-1.7B (Q4_K_M) contre gemma4:12b (Ollama), 8 consignes en français
| | LFM3-1.7B | gemma4:12b |
|---|---|---|
| VRAM | 2,3 Go | 7,3 Go |
| Vitesse de génération | environ 140 jetons/s | environ 11 jetons/s |
| Première réponse | immédiate | 94 s (chargement du modèle) |

Qualité (lecture manuelle, 8 consignes) :
- gemma4:12b : correct partout (titre en 4 mots, JSON propre, choix d'outil, capitale de l'Australie avec 1913, consigne de trois phrases) ; le raisonnement chiffré (trains) est long et n'a pas été relu jusqu'au bout.
- LFM3-1.7B avec réflexion (comportement par défaut) : réfléchit en anglais avant de répondre ; correct sur résumé, JSON, choix d'outil, réécriture de prompt image et consigne ; **3 consignes sur 8 sans réponse après 1 500 jetons** (titre, connaissance, raisonnement : la réflexion boucle).
- LFM3-1.7B sans réflexion (`enable_thinking=false`) : réponses en 0,1 à 0,7 s, mais moins fiables : le titre ignore la limite de 5 mots (liste cinq propositions), balise `</think>` visible dans deux réponses, date de désignation de Canberra erronée (1908), calcul de trajet faux (3 h 40 au lieu de 2 h 45).
- Lecture : LFM3-1.7B convient aux tâches courtes et cadrées (résumé, extraction, choix d'outil, réécriture) ; il ne remplace pas gemma4:12b comme modèle de discussion (connaissances et arithmétique faibles, réflexion instable). Échantillon de 8 consignes, une seule passe : indicatif.

### Vision : LFM3-VL-2B (Q4_K_M + mmproj Q8_0) contre qwen2.5vl (Ollama)
| | LFM3-VL-2B | qwen2.5vl |
|---|---|---|
| VRAM | 2,9 Go | 7,7 Go |
| Vitesse | environ 148 jetons/s | environ 50 jetons/s |
| OCR d'une facture française (5 lignes, accents, €) | parfait | parfait |
| Description de la voiture 3D | détaillée, plausible | plus courte (une antenne est citée ; l'image n'a pas été relue pour la contrôler) |

Un seul cas d'image et un seul d'OCR : indicatif.

### Voix et vidéo (testés sur le processeur, GPU occupé par une autre session)
Outils : `llama-tts.exe` et `llama-cli.exe` de la build b12427 ; fichiers de test dans `outputs/lfm3_voix/` (non versionné).
- **Synthèse vocale en français (Audio-2B)** : « Bonjour, ceci est un test de synthèse vocale en français pour le portail VertIA. » produit un fichier WAV de 5 s (24 kHz) en 22 s sur le processeur, voix `female`, `--tts-lang fr`. Je n'ai pas écouté le fichier (`outputs/lfm3_voix/tts_fr.wav`) : la qualité de la voix et de la prononciation reste à juger à l'oreille par l'utilisateur.
- **Transcription en français (Audio-2B, ASR)** : le fichier précédent est retranscrit mot pour mot (seule différence : « Vertia » au lieu de « VertIA »), ce qui montre que la parole est intelligible pour une machine. Test sur une voix synthétique propre ; non testé sur une voix humaine, du bruit ou plusieurs locuteurs. Débit sur processeur : 25 jetons/s.
- **Vidéo avec son (Omni-2B)** : clip de 5 s (image de la voiture 3D fixe + la phrase parlée ci-dessus). La partie image est correctement décrite en français ; **la partie son est fausse** : le modèle affirme qu'il n'y a aucune voix et décrit un bourdonnement de moteur, alors que la phrase est audible. Un seul test, avec une image fixe : indicatif, mais la compréhension de la bande sonore d'une vidéo ne doit pas être considérée comme acquise. Durée : 3 min 40 s sur processeur.
- **Vidéo sans son (VL-2B)** : non testé séparément.

### Verdict provisoire
- Voix : Audio-2B est utilisable en français pour la synthèse et la transcription (à confirmer sur une voix humaine et à l'oreille) : candidat sérieux pour la brique voix de la phase 5, à comparer avec les autres options locales avant de choisir.
- Texte : utilitaire rapide, pas modèle de discussion (voir plus haut).
- Vision : OCR et description rapides et légers (2,9 Go) : bon candidat pour lire des scans ou des images dans le portail.
- Vidéo : à ne pas retenir en l'état pour la compréhension du son.

## Sources
- Annonce : https://www.liquid.ai/blog/lfm3
- Fiches Hugging Face : LiquidAI/LFM3-1.7B-GGUF, LFM3-VL-2B, LFM3-Audio-2B, LFM3-Omni-2B
- Revue de la licence et du déploiement : https://aicybr.com/blog/liquid-ai-lfm3-1-7b-multimodal-local-deployment-license-guide
- Synthèse de presse : https://aiweekly.co/alerts/liquid-ai-opens-six-model-lfm3-family-at-256k-context
