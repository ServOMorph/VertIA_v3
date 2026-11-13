from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class Priority(BaseModel):
    priority: int = Field(ge=-100, le=100)


@router.get('/ressources')
async def resources(request: Request):
    services = request.app.state.services
    state = dict(services.monitor.latest)
    state.update(engine=services.arbiter.active,
                 limits=dict(vram=services.settings.vram_limit_percent, ram=services.settings.ram_limit_percent),
                 engines=list(services.arbiter.engines))
    return state


@router.post('/ressources/liberer')
async def free(request: Request, engine: str | None = None, modele: str | None = None):
    services = request.app.state.services
    if services.arbiter.lock.locked() or services.jobs.active or services.chat.pending or services.chat.maintenance:
        raise HTTPException(409, 'Une tâche utilise le GPU. Arrêtez-la avant de libérer la mémoire.')
    try:
        if modele:
            if engine != 'ollama':
                raise ValueError('Le déchargement par modèle est réservé à Ollama.')
            async with services.arbiter.lock:
                await services.ollama.unload_model(modele)
                if not await services.ollama.loaded_models() and services.arbiter.active == 'ollama':
                    services.arbiter.active = None
        else:
            await services.arbiter.free(engine)
        state = dict(await services.monitor.sample(), engine=services.arbiter.active)
        services.events.publish('ressources.maj', state)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, 'Le moteur n’a pas pu libérer sa mémoire. Vérifiez sa disponibilité.') from exc
    return {'statut': 'libere'}


@router.get('/jobs')
async def jobs(request: Request):
    return request.app.state.services.jobs.list()


@router.post('/jobs/{job_id}/annuler')
async def cancel(job_id: str, request: Request):
    queue = request.app.state.services.jobs
    try:
        await queue.cancel(job_id)
        return queue.get(job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch('/jobs/{job_id}')
async def priority(job_id: str, body: Priority, request: Request):
    queue = request.app.state.services.jobs
    try:
        queue.prioritize(job_id, body.priority)
        return queue.get(job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/jobs/{job_id}/reprendre', status_code=202)
async def retry(job_id: str, request: Request):
    queue = request.app.state.services.jobs
    try:
        return queue.get(queue.retry(job_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
