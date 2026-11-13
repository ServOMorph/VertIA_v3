from __future__ import annotations
import httpx
from fastapi import APIRouter, Depends, HTTPException

from vertia.setup import SetupConfig, diagnose, save_config
from vertia.web.deps import services

router = APIRouter()


@router.get('/installation')
def configuration(svc=Depends(services)):
    active = SetupConfig.current(svc.settings)
    saved = active
    try:
        if svc.settings.local_config.is_file():
            saved = SetupConfig.model_validate_json(svc.settings.local_config.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise HTTPException(409, 'Configuration enregistrée illisible. Corrigez ou renommez .vertia-local.json puis redémarrez.')
    return {'configuration': saved.model_dump(), 'redemarrage_requis': saved != active,
            'accueil_termine': svc.db.get_preference('accueil_termine') == 'oui'}


@router.post('/installation/diagnostic')
async def diagnostic(config: SetupConfig, svc=Depends(services)):
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
        return await diagnose(config, client)


@router.put('/installation')
def enregistrer(config: SetupConfig, svc=Depends(services)):
    if svc.settings.port in {config.ollama_port, config.comfy_port, config.acestep_port}:
        raise HTTPException(422, 'VertIA et ses moteurs doivent utiliser des ports différents.')
    try:
        save_config(svc.settings.local_config, config)
    except OSError:
        raise HTTPException(503, 'Enregistrement impossible. Vérifiez les droits du dossier VertIA et l’espace disque.')
    return {'redemarrage_requis': config != SetupConfig.current(svc.settings)}


@router.post('/installation/terminer')
def terminer(svc=Depends(services)):
    svc.db.set_preference('accueil_termine', 'oui')
    return {'statut': 'ok'}
