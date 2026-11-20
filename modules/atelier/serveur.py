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
MAX_JSON_ANALYSE = 1024 * 1024
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


def refuser_constante_json(valeur):
    raise ValueError(f"Constante JSON invalide : {valeur}")


def verifier_json_analyse(contenu):
    resultat = json.loads(contenu.decode("utf-8"), parse_constant=refuser_constante_json)
    if not isinstance(resultat, dict):
        raise ValueError("Objet JSON attendu")


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
    analyses = {}
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

    def lire_resultat(cible, verifier, maximum):
        cible = cible.resolve()
        if not cible.is_relative_to(outbox) or not cible.is_file():
            raise ValueError("Résultat hors outbox ou absent")
        with cible.open("rb") as fichier:
            contenu = fichier.read(maximum + 1)
        if len(contenu) > maximum:
            raise ValueError("Résultat trop volumineux")
        verifier(contenu)
        return contenu

    def executer(travail, commande, verifier, maximum, arguments=None):
        try:
            with verrou:
                if travail.get("annulation"):
                    return
                options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
                if arguments is not None:
                    options["stdin"] = subprocess.PIPE
                processus = subprocess.Popen(commande, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                             cwd=depot, **options)
                travail.update(processus=processus, etat="en_cours", message="En cours")
            try:
                entree = {"input": arguments} if arguments is not None else {}
                sortie, _ = processus.communicate(timeout=1720, **entree)
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
                    lire_resultat(cible, verifier, maximum)
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

    def lancer(registre, identifiant, travail, commande, verifier, maximum, arguments=None):
        while len(registre) >= 20:
            del registre[next(iter(registre))]
        registre[identifiant] = travail
        tache = asyncio.create_task(asyncio.to_thread(executer, travail, commande, verifier, maximum, arguments))
        taches.add(tache)
        tache.add_done_callback(taches.discard)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            for travail in [*travaux.values(), *analyses.values()]:
                await asyncio.to_thread(annuler_travail, travail)
            if taches:
                await asyncio.gather(*taches)

    app = FastAPI(title="Atelier", lifespan=lifespan)
    racine = dossier.resolve()

    def obtenir(identifiant, registre=travaux, nom="Retouche"):
        travail = registre.get(identifiant)
        if travail is None:
            raise HTTPException(404, f"{nom} introuvable")
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
            commande = [sys.executable, str(script), "image.retoucher", "--session", "vertia", "--prompt", prompt]
            if seed < 0:
                seed = secrets.randbelow(2**31)
            for cle, valeur in {"source": entrees[0].name, "masque": entrees[1].name,
                                "force": force, "etapes": etapes, "seed": seed}.items():
                commande.extend(["--param", f"{cle}={valeur}"])
            commande.extend(["--timeout", "1700"])
            lancer(travaux, identifiant, travail, commande, verifier_png, MAX_PNG)
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
                contenu = lire_resultat(travail["resultat"], verifier_png, MAX_PNG)
            except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                travail.update(etat="echec", message="Résultat PNG indisponible")
                raise HTTPException(404, travail["message"]) from None
        return Response(contenu, media_type="image/png")

    @app.delete("/api/retouche/{identifiant}")
    def annuler_retouche(identifiant: str):
        annuler_travail(obtenir(identifiant))
        return etat_retouche(identifiant)

    @app.post("/api/analyse")
    async def analyser(request: Request):
        corps = bytearray()
        async for bloc in request.stream():
            corps.extend(bloc)
            if len(corps) > MAX_CORPS_OCTETS:
                raise HTTPException(413, "Analyse trop volumineuse")
        try:
            params = json.loads(corps)
            if not isinstance(params, dict):
                raise ValueError()
            prompt = params.get("prompt")
            if not isinstance(prompt, str) or not 1 <= len(prompt) <= 4000 or not prompt.strip():
                raise ValueError()
            historique = params.get("historique", [])
            if not isinstance(historique, list) or len(historique) > 20 or any(
                not isinstance(m, dict) or m.keys() != {"role", "contenu"}
                or m["role"] not in ("user", "assistant")
                or not isinstance(m["contenu"], str) or len(m["contenu"]) > 8000
                for m in historique
            ):
                raise ValueError()
            image, _ = decoder_png(params.get("image"))
        except (ValueError, TypeError, OSError, SyntaxError, binascii.Error, RecursionError,
                Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(400, "Paramètres d’analyse invalides (PNG, question ou historique)") from None
        with verrou:
            if any(t["etat"] in {"attente", "en_cours"} for t in analyses.values()):
                raise HTTPException(409, "Une analyse est déjà active")
            identifiant = uuid.uuid4().hex
            cible = inbox / f"atelier_{identifiant}_analyse.png"
            travail = {"etat": "attente", "message": "En attente", "entrees": [cible]}
            try:
                inbox.mkdir(parents=True, exist_ok=True)
                with cible.open("xb") as fichier:
                    fichier.write(image)
            except OSError:
                nettoyer(travail)
                raise HTTPException(500, "Écriture de l’analyse impossible") from None
            question = [f"--prompt={prompt}"] if prompt.startswith("-") else ["--prompt", prompt]
            commande = [sys.executable, str(script), "image.analyser", "--session", "vertia",
                        *question, "--param", f"source={cible.name}"]
            if "historique" in params:
                commande.extend(["--param", f"historique={json.dumps(historique)}"])
            commande.extend(["--timeout", "1700"])
            arguments = None
            # Au-delà des limites du système, transmettre le même argv par l'entrée standard.
            trop_long = (len(subprocess.list2cmdline(commande).encode("utf-16-le", "surrogatepass")) >= 65534
                         if os.name == "nt" else any(len(os.fsencode(arg)) >= 65536 for arg in commande))
            if trop_long or "\0" in prompt:
                arguments = json.dumps(commande[1:]).encode("ascii")
                commande = [sys.executable, "-c",
                            "import json, os, runpy, sys; sys.argv = json.load(sys.stdin); "
                            "sys.path.insert(0, os.path.dirname(sys.argv[0])); "
                            "runpy.run_path(sys.argv[0], run_name='__main__')"]
            lancer(analyses, identifiant, travail, commande, verifier_json_analyse, MAX_JSON_ANALYSE, arguments)
        return {"id": identifiant}

    @app.get("/api/analyse/{identifiant}")
    def etat_analyse(identifiant: str):
        with verrou:
            travail = obtenir(identifiant, analyses, "Analyse")
            return {cle: travail[cle] for cle in ("etat", "message")}

    @app.get("/api/analyse/{identifiant}/resultat")
    def resultat_analyse(identifiant: str):
        with verrou:
            travail = obtenir(identifiant, analyses, "Analyse")
            if travail["etat"] != "termine":
                raise HTTPException(409, "Résultat indisponible")
            try:
                contenu = lire_resultat(travail["resultat"], verifier_json_analyse, MAX_JSON_ANALYSE)
            except (OSError, ValueError, RecursionError):
                travail.update(etat="echec", message="Résultat JSON indisponible")
                raise HTTPException(404, travail["message"]) from None
        return Response(contenu, media_type="application/json")

    @app.delete("/api/analyse/{identifiant}")
    def annuler_analyse(identifiant: str):
        annuler_travail(obtenir(identifiant, analyses, "Analyse"))
        return etat_analyse(identifiant)

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
