from __future__ import annotations

import base64
import binascii
import json
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from vertia.chat.commandes import HELP, MAX_CAPTURE, execute, save_capture
from vertia.web.deps import services

router = APIRouter()


class FolderBody(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    system_prompt: str = Field(default='', max_length=30000)


class ConversationBody(BaseModel):
    modele: str = Field(default='', max_length=200)
    dossier_id: str | None = None
    ephemere: bool = False


class ConversationUpdate(BaseModel):
    titre: str | None = Field(default=None, min_length=1, max_length=80)
    dossier_id: str | None = None
    epingle: bool | None = None
    modele: str | None = Field(default=None, min_length=1, max_length=200)


class PinBody(BaseModel):
    epingle: bool


class OrderBody(BaseModel):
    type: Literal['dossiers', 'conversations']
    ids: list[str] = Field(max_length=10000)


class MessageBody(BaseModel):
    contenu: str = Field(min_length=1, max_length=100000)
    fichiers: list[str] = Field(default_factory=list, max_length=3)


def require_conversation(svc, conv_id):
    conv = svc.chat.repository.conversation(conv_id)
    if conv is None:
        raise HTTPException(404, 'Conversation introuvable.')
    return conv


@router.get('/chat/aide')
async def help_chat():
    return {'local': True, 'contenu': HELP}


@router.get('/modeles')
async def models(svc=Depends(services)):
    try:
        return {'modeles': await svc.ollama.models(), 'defaut': svc.settings.default_model}
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, 'Ollama ne répond pas encore. Consultez son état dans la barre du haut et les réglages.') from exc


@router.get('/ollama/etat')
async def ollama_state(svc=Depends(services)):
    return svc.ollama_service.state


@router.get('/dossiers')
async def folders(svc=Depends(services)):
    return svc.chat.repository.folders()


@router.post('/dossiers', status_code=201)
async def create_folder(body: FolderBody, svc=Depends(services)):
    if not body.nom.strip():
        raise HTTPException(422, 'Le nom est vide.')
    return svc.chat.repository.create_folder(body.nom.strip(), body.system_prompt)


@router.put('/dossiers/{folder_id}')
async def update_folder(folder_id: str, body: FolderBody, svc=Depends(services)):
    if not svc.chat.repository.folder(folder_id):
        raise HTTPException(404, 'Dossier introuvable.')
    if not body.nom.strip():
        raise HTTPException(422, 'Le nom est vide.')
    return svc.chat.repository.update_folder(folder_id, body.nom.strip(), body.system_prompt)


@router.delete('/dossiers/{folder_id}')
async def delete_folder(folder_id: str, svc=Depends(services)):
    if not svc.chat.repository.folder(folder_id):
        raise HTTPException(404, 'Dossier introuvable.')
    if any(svc.chat.busy(c['id']) or svc.actions.busy(c['id'])
           for c in svc.chat.repository.conversations() if c['dossier_id'] == folder_id):
        raise HTTPException(409, 'Une discussion de ce dossier est en cours.')
    svc.chat.repository.delete_folder(folder_id)
    return {'statut': 'supprime'}


@router.patch('/dossiers/{folder_id}')
async def pin_folder(folder_id: str, body: PinBody, svc=Depends(services)):
    if not svc.chat.repository.folder(folder_id):
        raise HTTPException(404, 'Dossier introuvable.')
    return svc.chat.repository.pin_folder(folder_id, body.epingle)


@router.put('/navigation/ordre')
async def reorder(body: OrderBody, svc=Depends(services)):
    try:
        svc.chat.repository.reorder(body.type, body.ids)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'statut': 'ok'}


@router.get('/conversations')
async def conversations(svc=Depends(services)):
    return svc.chat.repository.conversations()


@router.post('/conversations', status_code=201)
async def create_conversation(body: ConversationBody, svc=Depends(services)):
    if body.dossier_id and not svc.chat.repository.folder(body.dossier_id):
        raise HTTPException(404, 'Dossier introuvable.')
    return svc.chat.repository.create_conversation(body.modele.strip() or svc.settings.default_model, body.dossier_id, body.ephemere)


@router.get('/conversations/{conv_id}')
async def conversation(conv_id: str, svc=Depends(services)):
    return {**require_conversation(svc, conv_id), 'messages': svc.chat.messages(conv_id), 'actions': svc.actions.list(conv_id)}


@router.patch('/conversations/{conv_id}')
async def rename_conversation(conv_id: str, body: ConversationUpdate, svc=Depends(services)):
    require_conversation(svc, conv_id)
    fields = body.model_dump(exclude_unset=True)
    if 'titre' in fields and (body.titre is None or not body.titre.strip()):
        raise HTTPException(422, 'Le titre est vide.')
    if 'epingle' in fields and body.epingle is None:
        raise HTTPException(422, 'Épinglage invalide.')
    if 'titre' in fields:
        fields['titre'] = body.titre.strip()
    if 'modele' in fields:
        if svc.chat.busy(conv_id):
            raise HTTPException(409, 'Attendez la fin des réponses avant de changer de modèle.')
        if body.modele is None or not body.modele.strip():
            raise HTTPException(422, 'Modèle invalide.')
        try:
            installed = await svc.ollama.models()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(503, 'Liste des modèles Ollama indisponible.') from exc
        if body.modele.strip() not in {m['name'] for m in installed}:
            raise HTTPException(422, 'Modèle Ollama inconnu.')
        if svc.chat.busy(conv_id):
            raise HTTPException(409, 'Attendez la fin des réponses avant de changer de modèle.')
        fields['modele'] = body.modele.strip()
    if 'dossier_id' in fields:
        if svc.chat.busy(conv_id) or svc.actions.busy(conv_id):
            raise HTTPException(409, 'Arrêtez les tâches de cette discussion avant de la déplacer.')
        if body.dossier_id is not None and not svc.chat.repository.folder(body.dossier_id):
            raise HTTPException(404, 'Dossier introuvable.')
    svc.chat.repository.update_conversation(conv_id, **fields)
    return require_conversation(svc, conv_id)


@router.delete('/conversations/{conv_id}')
async def delete_conversation(conv_id: str, svc=Depends(services)):
    require_conversation(svc, conv_id)
    if svc.chat.busy(conv_id) or svc.actions.busy(conv_id):
        raise HTTPException(409, 'Arrêtez la discussion avant de la supprimer.')
    try:
        svc.files.forget(conv_id)
    except (OSError, ValueError) as exc:
        raise HTTPException(409, 'Suppression des fichiers impossible. Vérifiez leur dossier et réessayez avant de supprimer la discussion.') from exc
    svc.chat.summaries.pop(conv_id, None)
    svc.actions.forget(conv_id)
    svc.chat.repository.delete_conversation(conv_id)
    return {'statut': 'supprime'}


@router.post('/conversations/{conv_id}/messages', status_code=202)
async def send_message(conv_id: str, body: MessageBody, svc=Depends(services)):
    require_conversation(svc, conv_id)
    if not body.contenu.strip():
        raise HTTPException(422, 'Le message est vide.')
    try:
        if body.contenu.lstrip().startswith('/'):
            return execute(svc, conv_id, body.contenu.strip())
        references = svc.files.message(conv_id, body.fichiers)
        return svc.chat.submit(conv_id, body.contenu.strip() + references)
    except LookupError as exc:
        raise HTTPException(404, 'Pièce jointe introuvable.') from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(422, 'Écriture impossible : fichier existant ou dossier inaccessible.') from exc


@router.post('/captures', status_code=201)
async def capture(request: Request, svc=Depends(services)):
    limit = 4 * ((MAX_CAPTURE + 2) // 3) + 128
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > limit:
            raise HTTPException(413, 'Capture supérieure à 10 Mio.')
        raw.extend(chunk)
    try:
        body = json.loads(raw)
        image = body.get('image') if isinstance(body, dict) else None
        prefix = 'data:image/png;base64,'
        if not isinstance(image, str) or not image.startswith(prefix):
            raise ValueError('Image PNG en data URL requise.')
        data = base64.b64decode(image[len(prefix):], validate=True)
        if len(data) > MAX_CAPTURE:
            raise HTTPException(413, 'Capture supérieure à 10 Mio.')
        return {'fichier': save_capture(svc.files.root, data)}
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(422, 'Capture PNG ou encodage invalide.') from exc
    except OSError as exc:
        raise HTTPException(422, 'Dossier des captures inaccessible.') from exc


@router.post('/conversations/{conv_id}/stop')
async def stop(conv_id: str, svc=Depends(services)):
    require_conversation(svc, conv_id)
    await svc.chat.stop(conv_id)
    return {'statut': 'arrete'}


@router.get('/chat/file')
async def queue(svc=Depends(services)):
    return svc.chat.state()
