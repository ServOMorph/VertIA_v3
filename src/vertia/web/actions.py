from __future__ import annotations

from dataclasses import asdict
import httpx

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from vertia.web.chat import require_conversation
from vertia.web.deps import services
from vertia.engines.base import MemoryNeeds
from vertia.tools.base import ParameterError

router = APIRouter()


class ParametersBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    parameters: dict


@router.get('/outils')
async def tools(svc=Depends(services)):
    return [dict(name=t.name, description=t.description, engine=t.engine,
                 parameters=t.parameters, memory=asdict(getattr(svc.arbiter.engines[t.engine], 'memory', MemoryNeeds()))) for t in svc.tools.tools.values()]


@router.get('/conversations/{conv_id}/actions')
async def actions(conv_id: str, svc=Depends(services)):
    require_conversation(svc, conv_id)
    return svc.actions.list(conv_id)


def change(svc, action_id, operation):
    try:
        return operation()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ParameterError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        # Les détails Pydantic peuvent contenir le prompt ; ne pas les journaliser.
        raise HTTPException(422, 'Paramètres invalides ou carte déjà traitée. Vérifiez les valeurs et son état.') from exc


@router.patch('/actions/{action_id}')
async def edit(action_id: str, body: ParametersBody, svc=Depends(services)):
    return change(svc, action_id, lambda: svc.actions.edit(action_id, body.parameters))


@router.post('/actions/{action_id}/valider', status_code=202)
async def confirm(action_id: str, body: ParametersBody, svc=Depends(services)):
    return change(svc, action_id, lambda: svc.actions.confirm(action_id, body.parameters))


@router.post('/actions/{action_id}/annuler')
async def cancel(action_id: str, svc=Depends(services)):
    return change(svc, action_id, lambda: svc.actions.cancel(action_id))


@router.get('/actions/{action_id}/images/{index}')
@router.get('/actions/{action_id}/medias/{index}')
async def preview(action_id: str, index: int, svc=Depends(services)):
    try:
        action = svc.actions.get(action_id)
        if index < 0:
            raise IndexError()
        if action['result'].get('files'):
            content, media_type = svc.files.read(action['result']['files'][index])
        else:
            content, media_type = await svc.tools.get(action['tool']).preview(action['result'], index)
        return Response(content, media_type=media_type, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
    except (LookupError, KeyError, OSError) as exc:
        raise HTTPException(404, 'Média introuvable.') from exc
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(503, 'Média indisponible. Vérifiez que son moteur est accessible.') from exc
