from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse

from vertia.web.chat import require_conversation
from vertia.web.deps import services

router = APIRouter()


@router.get('/conversations/{conv_id}/fichiers')
async def list_files(conv_id: str, svc=Depends(services)):
    require_conversation(svc, conv_id)
    return svc.files.list(conv_id)


@router.get('/fichiers/{file_id}/contenu')
async def content(file_id: str, telecharger: bool = False, svc=Depends(services)):
    try:
        meta = svc.files.get(file_id)
        headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
        disposition = 'attachment' if telecharger else 'inline'
        if meta['type'] == 'texte' and not telecharger:
            meta = dict(meta, mime='text/plain; charset=utf-8')
        if file_id in svc.files.ephemeral:
            data, mime = svc.files.read(file_id)
            mime = meta['mime']
            headers['Content-Disposition'] = f'{disposition}; filename="{meta["name"]}"'
            return Response(data, media_type=mime, headers=headers)
        path = svc.files.path(meta)
        if not path.is_file():
            raise LookupError()
        return FileResponse(path, media_type=meta['mime'], filename=meta['name'], content_disposition_type=disposition, headers=headers)
    except (LookupError, ValueError, OSError) as exc:
        raise HTTPException(404, 'Fichier introuvable ou inaccessible.') from exc


@router.post('/fichiers/{file_id}/dossier')
async def open_folder(file_id: str, svc=Depends(services)):
    try:
        meta = svc.files.get(file_id)
        if file_id in svc.files.ephemeral:
            raise ValueError('Fichier éphémère : téléchargez-le pour le conserver.')
        path = svc.files.path(meta)
        if not path.is_file():
            raise LookupError()
        if os.name != 'nt':
            raise ValueError('Ouverture du dossier disponible sous Windows.')
        os.startfile(str(path.parent))
        return {'statut': 'ouvert'}
    except (LookupError, OSError) as exc:
        raise HTTPException(404, 'Dossier inaccessible.') from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
