import json
from pathlib import Path
import time
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vertia.chat.context import estimate_messages
from vertia.engines.base import EngineError
from vertia.tools.base import ParameterError


class MessageHistorique(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    role: Literal['user', 'assistant']
    contenu: str = Field(max_length=32000)


class ParametresChat(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    prompt: str = Field(min_length=1, max_length=32000)
    modele: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$')
    systeme: str = Field(default='', max_length=8000)
    historique: list[MessageHistorique] | None = Field(default=None, max_length=50)
    temperature: float | None = Field(default=None, ge=0, le=2)
    num_predict: int | None = Field(default=None, ge=1, le=8192)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)

    @field_validator('prompt')
    @classmethod
    def non_vide(cls, valeur):
        if not valeur.strip():
            raise ValueError('Le prompt est vide.')
        return valeur


class OutilChat:
    capacite = 'chat.generer'
    moteur = 'ollama'
    parameters = {
        'prompt': 'texte, 1..32000 caractères',
        'modele': 'nom Ollama, modèle par défaut du portail si absent',
        'systeme': '0..8000 caractères, défaut vide',
        'historique': 'au plus 50 objets {role: user|assistant, contenu: texte de 32000 caractères maximum}',
        'temperature': '0..2, optionnel', 'num_predict': '1..8192, optionnel',
        'seed': '0..2147483647, optionnel',
    }

    def __init__(self, settings, chemins, moteurs):
        self.client = getattr(moteurs[self.moteur], 'client', None)
        self.modele = settings.default_model
        self.num_ctx = settings.num_ctx

    def valider(self, params):
        try:
            params = ParametresChat.model_validate(params).model_dump()
            if params['modele'] is None:
                params['modele'] = self.modele
            return ParametresChat.model_validate(params).model_dump()
        except ValueError as exc:
            raise ParameterError(str(exc)) from exc

    async def _digest(self, modele):
        def canonique(nom):
            return nom if ':' in nom.rsplit('/', 1)[-1] else nom + ':latest'

        try:
            for model in await self.client.models():
                nom = model.get('name') or model.get('model')
                digest = model.get('digest')
                if isinstance(nom, str) and canonique(nom) == canonique(modele) and isinstance(digest, str) and digest:
                    return digest
        except Exception:
            pass
        return 'non disponible'

    async def executer(self, params, dossier: Path):
        params = self.valider(params)
        messages = []
        if params['systeme']:
            messages.append(dict(role='system', content=params['systeme']))
        messages.extend(dict(role=m['role'], content=m['contenu']) for m in params['historique'] or [])
        messages.append(dict(role='user', content=params['prompt']))
        options = dict(num_ctx=self.num_ctx, num_predict=params['num_predict'] or min(2048, self.num_ctx // 4))
        options.update({cle: params[cle] for cle in ('temperature', 'seed') if params[cle] is not None})
        if estimate_messages(messages) + options['num_predict'] > self.num_ctx:
            raise ParameterError('Le texte et la réponse réservée dépassent la fenêtre de contexte num_ctx.')
        if self.client is None:
            raise EngineError('Client Ollama partagé indisponible.')
        debut = time.monotonic()
        try:
            await self.client.prepare_model(params['modele'])
            response = await self.client.client.post('/api/chat', json=dict(
                model=params['modele'], messages=messages, stream=False, keep_alive=-1, options=options))
            response.raise_for_status()
            resultat = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EngineError('La requête chat Ollama a échoué.') from exc
        if not isinstance(resultat, dict) or resultat.get('error'):
            raise EngineError('Réponse chat Ollama invalide.')
        message = resultat.get('message')
        texte = message.get('content') if isinstance(message, dict) else None
        if not isinstance(texte, str) or not texte.strip():
            raise EngineError('Le modèle Ollama a produit une réponse vide.')
        metadata = dict(modele=resultat.get('model') or params['modele'],
                        digest=await self._digest(params['modele']), parametres=options,
                        prompt_eval_count=resultat.get('prompt_eval_count'),
                        eval_count=resultat.get('eval_count'), elapsed_s=time.monotonic() - debut)
        fichiers = [dossier / 'reponse_1.md', dossier / 'reponse_1.json']
        fichiers[0].write_bytes(texte.encode('utf-8'))
        fichiers[1].write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        return fichiers
