"""Serveur local Atelier ; aucun stockage n'est créé à l'import."""
from __future__ import annotations

import json
import asyncio
import base64
import binascii
from contextlib import asynccontextmanager
from io import BytesIO
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import uuid
import warnings
from pathlib import Path

import psutil
from PIL import Image
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

MAX_CORPS_OCTETS = 200 * 1024 * 1024
DOSSIER_PROJETS = Path(__file__).resolve().parents[2] / "outputs" / "atelier"
NOM_PROJET = re.compile(r"[\w -]{1,80}", re.UNICODE)
NOMS_RESERVES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
RACINE = Path(__file__).resolve().parents[2]
MAX_PNG = 64 * 1024 * 1024
ERREURS_RETOUCHE = {4: "GPU occupé", 5: "délai dépassé", 6: "échec du moteur",
                    7: "GPU en pause à la demande de l'utilisateur", 8: "session inconnue",
                    9: "portail injoignable", 10: "paramètres invalides", 11: "plafond d'essais"}


def verifier_png(contenu: bytes) -> tuple[int, int]:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(contenu)) as image:
            if image.format != "PNG":
                raise ValueError("PNG attendu")
            taille = image.size
            image.verify()
        with Image.open(BytesIO(contenu)) as image:
            image.load()
        return taille


def decoder_png(valeur):
    if not isinstance(valeur, str):
        raise ValueError("PNG en base64 attendu")
    if valeur.startswith("data:image/png;base64,"):
        valeur = valeur.split(",", 1)[1]
    if len(valeur) > 4 * ((MAX_PNG + 2) // 3):
        raise ValueError("PNG trop volumineux")
    contenu = base64.b64decode(valeur, validate=True)
    if len(contenu) > MAX_PNG:
        raise ValueError("PNG trop volumineux")
    return contenu, verifier_png(contenu)


def arreter_arbre(processus):
    try:
        parent = psutil.Process(processus.pid)
        enfants = parent.children(recursive=True)
        for enfant in reversed(enfants):
            try:
                enfant.kill()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.kill()
        except psutil.NoSuchProcess:
            pass
        psutil.wait_procs(enfants + [parent], timeout=5)
    except psutil.NoSuchProcess:
        pass


def creer_app(dossier: Path = DOSSIER_PROJETS, *, racine_retouche: Path = RACINE) -> FastAPI:
    travaux = {}
    taches = set()
    verrou = threading.RLock()
    depot = racine_retouche.resolve()
    inbox = Path(os.getenv("ATELIER_INBOX", str(depot / "inbox"))).resolve()
    outbox = (depot / "outbox").resolve()
    script = Path(os.getenv("ATELIER_VERTIA_GEN", str(depot / "vertia_gen.py"))).resolve()

    def nettoyer(travail):
        for fichier in travail["entrees"]:
            fichier.unlink(missing_ok=True)

    def terminer(travail, **etat):
        nettoyer(travail)
        travail.update(**etat)

    def executer(travail, commande):
        try:
            with verrou:
                if travail.get("annulation"):
                    return
                options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
                processus = subprocess.Popen(commande, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                             cwd=depot, **options)
                travail.update(processus=processus, etat="en_cours", message="En cours")
            try:
                sortie, _ = processus.communicate(timeout=1720)
            except subprocess.TimeoutExpired:
                arreter_arbre(processus)
                processus.communicate()
                raise TimeoutError from None
            with verrou:
                if travail.get("annulation"):
                    return
                if processus.returncode:
                    terminer(travail, etat="echec", message=ERREURS_RETOUCHE.get(processus.returncode, "erreur interne"))
                else:
                    cible = (depot / Path(sortie.decode("utf-8").splitlines()[0])).resolve()
                    if not cible.is_relative_to(outbox) or not cible.is_file():
                        raise ValueError("Résultat hors outbox ou absent")
                    contenu = cible.read_bytes()
                    if len(contenu) > MAX_PNG:
                        raise ValueError("Résultat trop volumineux")
                    verifier_png(contenu)
                    terminer(travail, etat="termine", message="Terminé", resultat=cible)
        except Exception as erreur:
            with verrou:
                if not travail.get("annulation"):
                    terminer(travail, etat="echec", message="délai dépassé" if isinstance(erreur, TimeoutError) else "erreur interne")
        finally:
            with verrou:
                nettoyer(travail)
                if travail.get("annulation"):
                    travail.update(etat="annule", message="Annulé")

    @asynccontextmanager
    async def lifespan(app):
        yield
        for travail in list(travaux.values()):
            await asyncio.to_thread(annuler_travail, travail)
        if taches:
            await asyncio.gather(*taches)

    app = FastAPI(title="Atelier", lifespan=lifespan)
    racine = dossier.resolve()

    def obtenir(identifiant):
        travail = travaux.get(identifiant)
        if travail is None:
            raise HTTPException(404, "Retouche introuvable")
        return travail

    def annuler_travail(travail):
        with verrou:
            if travail["etat"] not in {"attente", "en_cours"}:
                return
            travail["annulation"] = True
            processus = travail.get("processus")
        if processus is not None:
            arreter_arbre(processus)
        with verrou:
            terminer(travail, etat="annule", message="Annulé")

    @app.post("/api/retouche")
    async def retoucher(request: Request):
        corps = bytearray()
        async for bloc in request.stream():
            corps.extend(bloc)
            if len(corps) > MAX_CORPS_OCTETS:
                raise HTTPException(413, "Retouche trop volumineuse")
        try:
            params = json.loads(corps)
            if not isinstance(params, dict):
                raise ValueError()
            prompt = params.get("prompt")
            force, etapes, seed = params.get("force", .85), params.get("etapes", 20), params.get("seed", -1)
            if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
                raise ValueError()
            if type(force) not in (int, float) or not .3 <= force <= 1:
                raise ValueError()
            if type(etapes) is not int or not 1 <= etapes <= 30 or type(seed) is not int or not -1 <= seed <= 2**63 - 1:
                raise ValueError()
            image, taille = decoder_png(params.get("image"))
            masque, taille_masque = decoder_png(params.get("masque"))
            if taille != taille_masque:
                raise ValueError()
        except (ValueError, TypeError, OSError, SyntaxError, binascii.Error, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(400, "Paramètres de retouche invalides (PNG, dimensions, texte ou réglages)") from None
        with verrou:
            if any(t["etat"] in {"attente", "en_cours"} for t in travaux.values()):
                raise HTTPException(409, "Une retouche est déjà active")
            identifiant = uuid.uuid4().hex
            entrees = [inbox / f"atelier_{identifiant}_{suffixe}.png" for suffixe in ("source", "masque")]
            travail = {"etat": "attente", "message": "En attente", "entrees": entrees}
            try:
                inbox.mkdir(parents=True, exist_ok=True)
                for cible, contenu in zip(entrees, (image, masque)):
                    with cible.open("xb") as fichier:
                        fichier.write(contenu)
            except OSError:
                nettoyer(travail)
                raise HTTPException(500, "Écriture de la retouche impossible") from None
            while len(travaux) >= 20:
                del travaux[next(iter(travaux))]
            travaux[identifiant] = travail
            commande = [sys.executable, str(script), "image.retoucher", "--session", "vertia", "--prompt", prompt]
            if seed < 0:
                seed = secrets.randbelow(2**31)
            for cle, valeur in {"source": entrees[0].name, "masque": entrees[1].name,
                                "force": force, "etapes": etapes, "seed": seed}.items():
                commande.extend(["--param", f"{cle}={valeur}"])
            commande.extend(["--timeout", "1700"])
            tache = asyncio.create_task(asyncio.to_thread(executer, travail, commande))
            taches.add(tache)
            tache.add_done_callback(taches.discard)
        return {"id": identifiant}

    @app.get("/api/retouche/{identifiant}")
    def etat_retouche(identifiant: str):
        with verrou:
            travail = obtenir(identifiant)
            return {cle: travail[cle] for cle in ("etat", "message")}

    @app.get("/api/retouche/{identifiant}/resultat")
    def resultat_retouche(identifiant: str):
        with verrou:
            travail = obtenir(identifiant)
            if travail["etat"] != "termine":
                raise HTTPException(409, "Résultat indisponible")
            try:
                cible = travail["resultat"].resolve()
                if not cible.is_relative_to(outbox):
                    raise ValueError()
                contenu = cible.read_bytes()
                if len(contenu) > MAX_PNG:
                    raise ValueError()
                verifier_png(contenu)
            except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                travail.update(etat="echec", message="Résultat PNG indisponible")
                raise HTTPException(404, travail["message"]) from None
        return Response(contenu, media_type="image/png")

    @app.delete("/api/retouche/{identifiant}")
    def annuler_retouche(identifiant: str):
        annuler_travail(obtenir(identifiant))
        return etat_retouche(identifiant)

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
