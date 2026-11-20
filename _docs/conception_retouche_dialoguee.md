# Retouche d'image dialoguée : conception (phase 7-bis, 2026-11-20)

Demande de l'utilisateur (2026-11-19) : partager une image, discuter avec un LLM local de vision qui propose des améliorations et des zones ; après validation, générations Qwen par zone (capture de la zone, génération, remplacement en calque).

## Mesures préalables (sonde du 2026-11-20, jeton GPU `vertia`)
Image : `outputs/retouche_essai/source.png` (phare, 768 x 768). Quatre zones de référence tracées à la main. IoU = recouvrement entre la boîte du modèle et la référence.

| Modèle | Phare | Soleil | Porte | Fleurs | Propositions de retouche |
|---|---|---|---|---|---|
| qwen2.5vl (6,0 Go) | 0,94 | 0,32 | 0,67 | 0,01 (une seule fleur) | 3, génériques (luminosité, contraste) |
| gemma4:12b (7,6 Go) | 0,23 (lanterne seule) | 0,52 | 0,73 | 0,29 | 1, créative (vagues sur les rochers) |
| gemma3:4b (3,3 Go) | 0 | 0 | 0 | 0,14 | 3, zones fausses |

- Les IoU sont obtenus après conversion du repère : qwen2.5vl répond en pixels d'une image qu'il a redimensionnée (924 x 924 pour 768 x 768, il le révèle lui-même dans une zone `[0, 0, 924, 924]`) ; gemma4 répond en `[y1, x1, y2, x2]` normalisé sur 1000 quand on lui demande des boîtes, mais en pixels dans un autre format de réponse : convention instable.
- Sans conversion, tous les IoU sont proches de 0 : le repère est le premier risque technique.
- Durées non comparables (chaque appel rechargeait le modèle, `keep_alive=0`).
- Une seule image carrée : la règle de redimensionnement de qwen2.5vl reste à confirmer sur une image non carrée.

### Sonde complémentaire (même jour, image non carrée 1200 x 750, modèles chauds)
- qwen2.5vl, invite native (« Locate X in the image, output its bbox coordinates using JSON format », réponse `bbox_2d`) : coordonnées en pixels de l'image envoyée, sans conversion ; boîtes précises au contrôle visuel (tour, lanterne, porte, disque du soleil). Les IoU mesurés (phare 0,47, soleil 0,22, porte 0,84) sont bas surtout parce que les références tracées à la main étaient larges (socle compris). Règle retenue : envoyer à qwen une image redimensionnée par VertIA à environ 1 Mpx, côtés multiples de 28, puis reconvertir ; l'image de 768 x 768 (0,59 Mpx) avait été agrandie à 924 x 924 par le modèle.
- qwen2.5vl : chargement 62 s, puis environ 2 s par zone.
- gemma4:12b (dialogue, JSON) : chargement 89 s, réponse 77 s, tour suivant 126 s modèle chargé. Le dialogue prend donc environ 2 minutes par tour : principal point faible pour l'usage, à réduire (image envoyée plus petite, contexte réduit) au lot 2.
- gemma4 : propositions pertinentes (ajouter un bateau, toit en vert, fleurs) mais JSON imparfait (clé mal orthographiée, titre incohérent) : validation tolérante obligatoire.
- Pour un ajout, l'objet n'existe pas encore (qwen : « There are none. » pour « boat ») : la proposition doit désigner un emplacement visible (« the water near the lighthouse ») ; sans zone trouvée, l'utilisateur la trace.
- Décisions de l'utilisateur (2026-11-20) : gemma4:12b pour le dialogue puis qwen2.5vl pour situer les zones ; outil placé dans l'Atelier.

## Parcours proposé
1. Dans l'Atelier, outil « Retouche dialoguée » : un panneau de discussion à côté du canevas. L'image composée (tous calques) part au portail.
2. Le modèle de vision répond en texte et en propositions structurées : `{titre, prompt, zone}`.
3. Chaque zone s'affiche en rectangle sur le canevas, déplaçable et redimensionnable, avec une case à cocher. L'utilisateur corrige les zones et les prompts : le repérage automatique n'est qu'un point de départ.
4. Validation : pour chaque zone cochée, l'Atelier découpe la zone avec une marge de contexte de 25 %, crée un masque rectangulaire adouci (affinable au pinceau de l'outil Retouche IA actuel) et lance `image.retoucher` sur le découpage. Le découpage donne plus de pixels à une petite zone que la retouche de l'image entière, plafonnée à 1,5 Mpx.
5. Chaque résultat revient comme calque « Retouche : <titre> » placé à la position de la zone. Les zones passent l'une après l'autre (une seule IA lourde à la fois).
6. La discussion continue sur l'image mise à jour.

## Architecture
- Portail : nouvelle capacité `image.analyser` (module `modules/image`) : image de l'inbox + question + historique, réponse JSON validée (zones bornées à l'image, au plus 6 propositions, prompt 1..4000 caractères). Un adaptateur par modèle convertit le repère des boîtes vers les pixels de l'image d'origine. Le moteur reste `ollama`, sous la file GPU et le jeton existants.
- Atelier : panneau de dialogue, rectangles de zone, découpage et recomposition en JavaScript ; appels `api/retouche` existants pour chaque zone (aucune nouvelle route de retouche). Une route `api/analyse` relaie `image.analyser` par `vertia_gen.py`, comme la retouche.
- GPU : le passage modèle de vision -> ComfyUI est déjà géré par l'arbitre (le moteur précédent est libéré avant le suivant). Avec la réservation de l'UI, le modèle de chat est rechargé après la retouche.

## Gate de la phase
Benchmark reproductible (règle CLAUDE.md, section Roadmap) : 6 images verrouillées (carrées et non carrées, photo, illustration, texte), 3 à 4 zones de référence chacune ; critère : IoU >= 0,5 sur au moins 70 % des zones après conversion du repère, et propositions JSON valides à 100 %. Tests unitaires : conversion des repères, validation JSON, découpage et recomposition (pixels hors zone identiques).

## Lots
1. Sonde complémentaire : image non carrée, modèle chaud (durées réelles), formulation native de chaque modèle. Claude, sous jeton GPU.
2. `image.analyser` et adaptateurs de repère, tests. Code délicat (validation, GPU) : Codex high si le drapeau est levé, sinon Claude.
3. Atelier : panneau de dialogue, rectangles, découpage et calques. JavaScript sur plusieurs fichiers : OpenCode ou Codex medium, revue par Claude.
4. Benchmark de gate et contrôles manuels (`tests_manuels.md`).

## Décisions à prendre par l'utilisateur
- Modèle : qwen2.5vl seul (zones fiables, propositions génériques, un seul chargement) ou gemma4:12b pour le dialogue puis qwen2.5vl pour situer les zones (meilleur dialogue, deux chargements successifs sur 8 Go).
- Emplacement : panneau dans l'Atelier (recommandé, les calques y sont) ou discussion du portail.

## Limites connues
- Un seul modèle en VRAM : chaque passage dialogue -> retouche -> dialogue recharge un modèle (durée à mesurer au lot 1).
- Texte manuscrit et petits objets : repérage faible attendu (fleurs : 0,01 et 0,29).
- Les propositions de qwen2.5vl visent des réglages globaux (luminosité, contraste) qu'une retouche par masque ne fait pas bien : la consigne système devra les orienter vers des changements locaux.
