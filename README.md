# VertIA

Studio d'intelligence artificielle **100 % locale**, pensé pour les personnes qui débutent. On discute avec un assistant qui prépare les demandes (images, musiques, bientôt vidéos), on valide, et tout tourne sur son propre ordinateur.

## État actuel (v0.1.0)
- Fondations : serveur FastAPI, interface à panneaux affichables/masquables (Discussion, Fichiers, Mémoire, Outils) avec préférences mémorisées, canal d'événements temps réel.
- À venir : voir [roadmap_vertia_v1.md](roadmap_vertia_v1.md).

## Démarrer
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\python run.py
```
L'interface s'ouvre sur http://127.0.0.1:4310 ; le serveur se recharge automatiquement à chaque modification.

## Tests
```powershell
.venv\Scripts\python -m pytest
```

## Documentation
- [Architecture](_docs/architecture.md)
- [Mise en production](MISE_EN_PROD.md)
- [Recherche vidéo locale](_docs/benchmark_video.md)

## Licence
MIT
