from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal

from vertia import __version__
from vertia.tools.base import ParameterError

async def local_seulement(request: Request):
    if request.client is None or request.client.host not in {'127.0.0.1', '::1', 'testclient'}:
        raise HTTPException(403, 'API réservée à localhost.')


router = APIRouter(prefix='/api/v1', dependencies=[Depends(local_seulement)])


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


@router.post('/demandes/{demande_id}/annuler')
async def annuler(demande_id: str, request: Request):
    try:
        return await service(request).annuler(demande_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
