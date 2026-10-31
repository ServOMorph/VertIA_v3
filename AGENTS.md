# AGENTS.md

Instructions pour les agents non-Claude (Codex, Gemini, etc.) intervenant sur ce projet.
Ce fichier ne duplique pas `.claude/CLAUDE.md` (protocole vibecoding start/close, réservé à
Claude Code) : il ne couvre que ce qui s'applique à tout agent, indépendamment de l'outil.

## Base de connaissances

Si ce projet dispose d'un dossier `DOCUMENTATION/` à la racine avec un fichier `INDEX.md`, il
centralise la documentation métier du projet, consultable par tout agent quel que soit l'outil
utilisé. Avant d'affirmer un fait métier non disponible dans le contexte immédiat, consulter
`DOCUMENTATION/INDEX.md` (catalogue, une ligne par document) puis n'ouvrir que le(s) document(s)
pertinent(s) — jamais tout le dossier. Absence de `DOCUMENTATION/` : rien à consulter.

## Projet VertIA_v3

- Lire `_docs/architecture.md` avant toute modification : une IA = un module `Engine` + `Tool`, GPU exclusif via la file de jobs.
- Stack : Python 3.11+ / FastAPI / sqlite3, front HTML/CSS/JS vanilla en modules ES, tests pytest.
- Tests : `.venv\Scripts\python -m pytest -q` ; syntaxe JS : `node --check <fichier>`.
- Interdits : lancer une génération GPU ou un serveur, écrire hors du dépôt, modifier `data/` ou `outputs/`, committer.
- Délégation : consignes permanentes dans `_codex/PREAMBULE.md` ; rapport final au format STATUT / FICHIERS / VERIFS / OUVERT.
