"""Serveur local Atelier ; aucun stockage n'est créé à l'import."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

MAX_CORPS_OCTETS = 200 * 1024 * 1024
DOSSIER_PROJETS = Path(__file__).resolve().parents[2] / "outputs" / "atelier"
NOM_PROJET = re.compile(r"[\w -]{1,80}", re.UNICODE)
NOMS_RESERVES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def creer_app(dossier: Path = DOSSIER_PROJETS) -> FastAPI:
    app = FastAPI(title="Atelier")
    racine = dossier.resolve()

    def chemin(nom: str) -> Path:
        if not NOM_PROJET.fullmatch(nom) or not nom.strip() or nom.strip().upper() in NOMS_RESERVES:
            raise HTTPException(400, "Nom de projet invalide")
        cible = (racine / f"{nom}.json").resolve()
        if cible.parent != racine:
            raise HTTPException(400, "Chemin de projet invalide")
        return cible

    @app.get("/api/projets")
    def liste():
        if not racine.exists():
            return []
        return sorted(p.stem for p in racine.glob("*.json")
                      if p.is_file() and p.resolve().parent == racine
                      and NOM_PROJET.fullmatch(p.stem))

    @app.post("/api/projets/{nom:path}")
    async def enregistrer(nom: str, request: Request):
        cible = chemin(nom)
        taille = 0
        corps = bytearray()
        async for bloc in request.stream():
            taille += len(bloc)
            if taille > MAX_CORPS_OCTETS:
                raise HTTPException(413, "Projet trop volumineux")
            corps.extend(bloc)
        try:
            projet = json.loads(corps)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, "JSON invalide") from None
        if not isinstance(projet, dict):
            raise HTTPException(400, "Un objet JSON est attendu")
        racine.mkdir(parents=True, exist_ok=True)
        temporaire = None
        try:
            with tempfile.NamedTemporaryFile(dir=racine, suffix=".tmp", delete=False) as fichier:
                temporaire = Path(fichier.name)
                fichier.write(corps)
                fichier.flush()
                os.fsync(fichier.fileno())
            os.replace(temporaire, cible)
        finally:
            if temporaire is not None:
                temporaire.unlink(missing_ok=True)
        return {"nom": nom}

    @app.get("/api/projets/{nom:path}")
    def lire(nom: str):
        cible = chemin(nom)
        try:
            return json.loads(cible.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise HTTPException(404, "Projet introuvable") from None
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, "Projet illisible") from None

    @app.api_route("/api", methods=["GET", "POST"])
    @app.api_route("/api/{route:path}", methods=["GET", "POST"])
    def api_inconnue(route: str = ""):
        raise HTTPException(404, "Route API introuvable")

    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))
    return app


app = creer_app()
