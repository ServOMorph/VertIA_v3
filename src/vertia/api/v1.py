from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import stat
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal

from vertia import __version__
from vertia.tools.base import ParameterError

async def local_seulement(request: Request):
    if request.client is None or request.client.host not in {'127.0.0.1', '::1', 'testclient'}:
        raise HTTPException(403, 'API réservée à localhost.')


router = APIRouter(prefix='/api/v1', dependencies=[Depends(local_seulement)])
LIMITE_AUDIO = 200 * 1024**2
EXTENSIONS_AUDIO = {'.wav', '.mp3', '.flac', '.ogg', '.m4a'}
EXTENSIONS_IMAGE = {'.png', '.jpg', '.jpeg', '.webp'}
LIMITE_IMAGE = 50 * 1024**2
MULTIPART_DISPONIBLE = importlib.util.find_spec('python_multipart') is not None


class Demande(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    session: str = Field(pattern=r'^[a-z0-9_-]{1,40}$')
    capacite: str
    params: dict = Field(default_factory=dict)
    critere: str = ''
    essais_max: int = Field(default=3, ge=1, le=5)


class Retour(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    verdict: Literal['valide', 'a_refaire']
    motif: str = ''


def service(request):
    return request.app.state.services.demandes


@router.get('/sante')
async def sante(request: Request):
    registre = request.app.state.services.modules
    diagnostics = registre.sante()
    return dict(version_api='1', version_vertia=__version__,
                pret=not registre.erreurs and all(d.get('pret', False) for d in diagnostics.values()),
                erreurs=registre.erreurs, modules=diagnostics)


@router.get('/capacites')
async def capacites(request: Request):
    return service(request).capacites()


@router.get('/modules')
async def modules(request: Request):
    registre = request.app.state.services.modules
    diagnostics = registre.sante()
    activites = [
        ('image', 'Image'), ('musique', 'Musique'), ('voix', 'Voix'),
        ('video', 'Vidéo'), ('chat', 'Discussion'), ('3d', 'Modélisation 3D'),
        ('animation_3d', 'Animation 3D'), ('worldmodel', 'WorldModel'),
        ('llm', 'LLM'), ('outil', 'Outils'),
    ]
    return {'activites': [
        {'activite': activite, 'titre': titre, 'modules': [
            {'nom': module.nom, 'titre': module.titre, 'version': module.version,
             'capacites': module.capacites, 'lien': module.lien,
             'sante': diagnostics[module.nom]}
            for module in registre.par_activite(activite)
        ]} for activite, titre in activites
    ], 'erreurs': registre.erreurs}


@router.post('/demandes', status_code=202)
async def creer(body: Demande, request: Request):
    try:
        return {'id': service(request).creer(**body.model_dump())}
    except ParameterError as exc:
        raise HTTPException(422, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, {'motif_code': 'session_inconnue', 'message': str(exc)}) from exc


@router.get('/demandes/{demande_id}')
async def etat(demande_id: str, request: Request):
    try:
        return service(request).get(demande_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post('/demandes/{demande_id}/retour')
async def retour(demande_id: str, body: Retour, request: Request):
    try:
        return await service(request).retour(demande_id, **body.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/demandes/{demande_id}/fichiers/{index}')
async def fichier_demande(demande_id: str, index: int, request: Request):
    if not re.fullmatch(r'[A-Za-z0-9]+', demande_id) or index < 0:
        raise HTTPException(404, 'Fichier introuvable.')
    try:
        chemins = service(request).get(demande_id)['chemins']
        fichier = Path(chemins[index])
        racine = service(request).livraison.outbox.resolve(strict=True)
        relatif = fichier.relative_to(racine)
        if '..' in relatif.parts:
            raise ValueError
        for parent in (fichier, *fichier.parents):
            if parent == racine:
                break
            infos = parent.lstat()
            if (parent.is_symlink()
                    or getattr(infos, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError
        infos = fichier.lstat()
        if (not stat.S_ISREG(infos.st_mode) or infos.st_nlink != 1
                or not fichier.resolve(strict=True).is_relative_to(racine)):
            raise ValueError
        mime = {'.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.flac': 'audio/flac',
                '.txt': 'text/plain; charset=utf-8',
                '.json': 'application/json', '.png': 'image/png', '.mp4': 'video/mp4'}.get(fichier.suffix.lower())
        if mime is None:
            raise ValueError
        return FileResponse(fichier, media_type=mime)
    except (LookupError, OSError, ValueError, TypeError) as exc:
        raise HTTPException(404, 'Fichier introuvable.') from exc


@router.post('/inbox')
async def televerser_audio(request: Request, extension: str = ''):
    formulaire = None
    cible = None
    try:
        if request.headers.get('content-type', '').split(';')[0] == 'multipart/form-data':
            if not MULTIPART_DISPONIBLE:
                raise HTTPException(415, 'Envoyez le corps audio brut avec le paramètre extension.')
            formulaire = await request.form()
            fichier = formulaire.get('fichier')
            if fichier is None or not hasattr(fichier, 'read'):
                raise HTTPException(422, 'Champ fichier requis.')
            suffixe = Path(fichier.filename or '').suffix.lower()

            async def blocs():
                while bloc := await fichier.read(1024**2):
                    yield bloc
        else:
            if request.headers.get('content-type', '').split(';')[0] != 'application/octet-stream':
                raise HTTPException(415, 'Type attendu : application/octet-stream.')
            suffixe = '.' + extension.lower().lstrip('.')
            blocs = request.stream
        if suffixe not in EXTENSIONS_AUDIO | EXTENSIONS_IMAGE:
            raise HTTPException(422, 'Extension non prise en charge (audio ou image PNG, JPEG, WebP).')
        image = suffixe in EXTENSIONS_IMAGE
        limite = LIMITE_IMAGE if image else LIMITE_AUDIO
        inbox = request.app.state.services.chemins.inbox_dir
        inbox.mkdir(parents=True, exist_ok=True)
        nom = ('image_' if image else 'voix_') + uuid4().hex + suffixe
        cible = inbox / nom
        taille = 0
        with cible.open('xb') as sortie:
            async for bloc in blocs():
                taille += len(bloc)
                if taille > limite:
                    raise HTTPException(413, 'Fichier supérieur à la taille autorisée.')
                sortie.write(bloc)
        return {'nom': nom}
    except BaseException:
        if cible is not None:
            cible.unlink(missing_ok=True)
        raise
    finally:
        if formulaire is not None:
            await formulaire.close()


@router.post('/demandes/{demande_id}/annuler')
async def annuler(demande_id: str, request: Request):
    try:
        return await service(request).annuler(demande_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
