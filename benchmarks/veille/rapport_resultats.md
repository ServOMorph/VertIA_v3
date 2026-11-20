# Résultats des essais comparatifs (2026-11-19)

Protocole : `protocole.md`. Cas chat : `cas_chat.json`. Scripts : `scripts/benchmark_chat_veille.py`, `scripts/benchmark_media_veille.py`, `scripts/benchmark_video_reference.py`.
Conditions : RTX 4060 8 Go, jeton GPU `vertia` pris par `vram_lock.py` pour chaque lot et rendu ensuite. Un seul passage par cas, seed fixe : aucune statistique, des constats. Qualité jugée par Claude seul (juge unique, sans test à l'aveugle).
Licences : aucune supposée commerciale. Les textes complets de licence n'ont pas été lus (voir les rapports de veille). Qwen-Image 2.1 est sous Qwen Research License.
Rien n'a été téléchargé : seuls les modèles déjà présents ont été testés.

## Lot 1 : chat (Ollama, `num_ctx` 8192, température 0, seed 7, 5 cas)

| Modèle | Jetons/s | VRAM ajoutée | Contrôles auto (3) | Jugement |
|---|---|---|---|---|
| gemma4:12b (actuel) | 8,7 à 12,2 | ~6,2 Go (pic 7,4 Go) | 3/3 | français propre, courriel de 6 lignes pour 5 demandées, résumé qui omet les deux équipes en retard |
| gemma4:12b-32k | 8,8 à 13,5 | ~6,2 Go | 3/3 | réponses identiques à gemma4:12b |
| gemma4:e4b | 53 à 60 | ~4,4 Go (pic 5,6 Go) | 3/3 | résumé complet, mais courriel avec champ « [Numéro de commande] » laissé en blanc et 2 paragraphes au lieu de 5 lignes |
| qwen3.5:latest (9b) | 28 à 34 | ~6,3 Go (pic 7,4 Go) | 3/3 | faute de français relevée (« votre prochaine achat »), courriel en 2 paragraphes |
| granite4.2:8b (ajouté plus tard le 2026-11-19) | 31 à 34 | ~6,1 Go (pic 7,0 Go) | 2/3 : extraction et consigne réussies ; raisonnement : bonne réponse 13:00 atteinte mais réponse longue coupée à 700 jetons avant la ligne « HH:MM » finale, donc contrôle strict échoué | résumé complet (revue de sécurité incluse), courriel de 6 lignes avec « [Votre nom / Service Client] » laissé en blanc ; réponses plus verbeuses |

- Mesuré : gemma4:e4b est 5 à 6 fois plus rapide que gemma4:12b pour une qualité comparable sur ces cinq cas ; gemma4:12b a un pic de 7,4 Go, donc la lenteur vient probablement du débordement en mémoire centrale (non vérifié par un contrôle de la répartition CPU/GPU).
- Contrôles automatiques : mon premier « attendu » du cas raisonnement (13:15) était faux, la bonne réponse est 13:00 ; les résultats ont été corrigés. Le contrôle de date de l'extraction a été assoupli (les deux formats acceptés).
- Non confirmé : qualité sur des conversations longues, en français soutenu ou sur des tâches de code ; granite4.2:8b n'a pas été testé (modèle absent).
- Limite : 5 cas courts. Ne justifie pas à lui seul de changer le modèle par défaut.

## Lot 2 : image (ComfyUI, 1024x1024, seed 0)

| Modèle | Étapes | Durée (s) : affiche / portrait / objet | Pic VRAM | Jugement |
|---|---|---|---|---|
| Qwen-Image 2.1 Q4_K_M (actuel) | 25 | 321 (chargement inclus) / 100 / 143 | 7,4 à 7,5 Go | texte français parfait et lisible ; portrait réussi (port breton en fond) ; théière sans anse visible (défaut) |
| Z-Image Turbo Q4_K_M | 8 | 161 (chargement inclus) / 70 / 28 | 7,1 à 7,2 Go | texte de l'affiche déformé et dupliqué (« DU LUID », « SAMBI ») ; portrait réaliste mais décor de champ, pas de port ; théière bien formée, fond gris dégradé et non blanc uni |

- Mesuré : Z-Image est 1,4 à 5 fois plus rapide (hors premier chargement) pour une VRAM un peu moindre.
- Jugé : Qwen-Image 2.1 est nettement meilleur pour le texte dans l'image ; Z-Image est bon sur les objets et portraits mais ne respecte pas toujours le décor demandé.
- Non testés : MOSS-Image, FLUX 3 Klein (poids absents, téléchargement non demandé), prompts en anglais, autres tailles. Les durées varient d'un cas à l'autre (un seul passage).
- Fichiers : `image/`.

## Lot 3 : vidéo (832x480, 17 images, seed 0)

| Modèle | Cas | Durée | Pic VRAM | Jugement |
|---|---|---|---|---|
| Wan 2.2 TI2V-5B Q4_K_M (ComfyUI, 24 i/s, 20 étapes) | tasse | 185 s (chargement inclus) | 7,6 Go | cohérent, mouvement de vapeur discret, contraste marqué |
| | forêt | 48 s | 7,6 Go | image nette, quasi statique, travelling à peine visible |
| | personnage | 48 s | 7,6 Go | femme vue de dos, parapluie absent |
| Wan 2.1 14B int8 (portail, 16 i/s) | tasse | non mesuré (voir plus bas) | non mesuré | vapeur très marquée, grand mouvement, fort contraste |
| | forêt | échec : RAM à 96 % (limite du portail à 90 %) | non mesuré | non testé |
| | personnage | non mesuré | non mesuré | parapluie présent, silhouette cohérente, mais murs en mosaïque de blocs |

- Mesuré : Wan 2.2 5B tient en 7,6 Go (7 621 MiB de pic, sous les 7,5 Go de 7 680 MiB annoncés par le protocole) en 48 s par clip hors chargement, sur une durée de 0,7 s.
- Non mesuré fiable : les durées et pics de VRAM du Wan 2.1 14B par le portail (1 504 s, 136 s, 1 181 s ; pics de 2,7 à 7,2 Go) mélangent l'attente du jeton, le chargement du moteur et un dépassement de délai de mon script ; la tasse a été livrée après l'expiration de mon délai de 1 500 s. Aucune comparaison de vitesse entre Wan 2.1 et Wan 2.2 n'est donc établie.
- Jugé : Wan 2.1 14B respecte mieux le prompt (parapluie, mouvement) mais montre des artefacts de texture sur le personnage ; Wan 2.2 5B est plus propre mais plus statique et a omis le parapluie. Clips de 0,7 s : trop courts pour juger l'action « elle ouvre un parapluie ».
- Non testés : forêt en Wan 2.1, clips plus longs, HunyuanVideo 1.5, LTX-2.5.
- Fichiers : `video/` (clips et planches de trois images).

## Incidents
- Premier lot image : échec de Qwen-Image faute du module `websockets` dans mon script ; graphe recopié sans dépendance, lot relancé sous le même jeton.
- RAM du poste à 98 % pendant le lot vidéo de référence : demande refusée par la garde du portail (limite 90 %). Je n'ai pas relancé le cas forêt.
- Le portail sans interface lancé par `vertia_gen.py` (PID 51164, 08:30) a été arrêté après les essais, afin de libérer le port 4310.

## Suites possibles (aucune lancée)
1. Télécharger MOSS-Image ou FLUX 3 Klein (tailles à relever) puis les comparer à Qwen-Image 2.1.
2. Télécharger granite4.2:8b (5,3 Go d'après Ollama) pour le chat.
3. Relancer Wan 2.1 14B cas forêt quand la RAM le permet, avec un délai plus long, et mesurer proprement.
4. Contrôler la licence de Qwen-Image 2.1 avant tout usage commercial.

## Ajouts du 2026-11-19 (essais complémentaires, décidés par VibeObs dans le cadre délégué par l'utilisateur)

- granite4.2:8b (5,3 Go, Ollama) : téléchargé puis testé sur les mêmes 5 cas, même méthode (ligne ajoutée au tableau du lot 1). Il génère à 31 à 34 jetons/s, soit environ 3,5 fois plus vite que gemma4:12b mais moins vite que gemma4:e4b (59), avec un pic de VRAM de 7,0 Go (le modèle pèse 5,3 Go, la différence vient du cache de contexte). Licence non lue.
- MOSS-Image : essai impossible avec le ComfyUI actuel (v0.38.0, daté du 1er octobre ; support de MOSS-Image apparu le 18 octobre d'après le changelog ComfyUI). Je n'ai trouvé aucun code MOSS dans `supported_models.py`, `model_detection.py`, `sd.py` ni `nodes.py` (recherche textuelle, sans lancement du moteur). Il faudrait installer ou mettre à jour ComfyUI : à décider par l'utilisateur. Ordre de grandeur de ce que demanderait l'essai : poids ~13 Go (modèle SFT int8 5,41 Go, encodeur de texte w4a8 7,34 Go, VAE 0,25 Go) plus un environnement torch pour un second ComfyUI (taille non relevée). Téléchargement suspendu : seul le VAE (0,25 Go) est complet, un fichier partiel de 0,25 Go du modèle SFT int8 est laissé dans `models/veille/diffusion_models/` ; rien d'autre n'est téléchargé.
- FLUX 3 Klein : non téléchargé. Dépôt à accès protégé, licence « FLUX Kommunity » à accepter sur Hugging Face par l'utilisateur ; ni compte ni acceptation faits à sa place. Tailles relevées pour l'essai éventuel : modèle distillé int8 5,83 Go, encodeur qwen3vl 4b int8 4,86 Go, VAE 0,34 Go, soit environ 11 Go.
- Après le lot chat de granite, `release vertia` a été fait ; la reprise de creation_llm est contrôlée séparément.
