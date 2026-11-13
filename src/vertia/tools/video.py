from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vertia.tools.base import ParameterError


def video_candidate(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))
    if re.search(r"\b(?:sans generer|don't|do not)\b|\b(?:ne|n')\s*(?:\w+\s+){0,2}(?:genere|cree|anime).*\bpas\b", text):
        return False
    noun = re.search(r'\b(video|clip|animation|film)\b', text)
    verb = re.search(r'\b(genere|generer|cree|creer|generate|create|produis|realise|fais|anime|animer|animate)\b|je (?:veux|voudrais|souhaite)|j.aimerais', text)
    return bool(noun and verb or re.search(r'\b(?:anime|animer|animate)\b.*\b(?:image|photo|picture)\b', text))


class VideoParameters(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    prompt: str = Field(min_length=1, max_length=4000)
    negatif: str = Field(default='', max_length=2000)
    largeur: int = Field(default=640, ge=256, le=960, multiple_of=32)
    hauteur: int = Field(default=384, ge=256, le=960, multiple_of=32)
    images: int = Field(default=49, ge=17, le=73)
    etapes: int = Field(default=20, ge=1, le=30)
    seed: int = Field(default=0, ge=0, le=2**53 - 1)
    mode: Literal['t2v', 'i2v'] = 't2v'
    references: list[str] = Field(default_factory=list, max_length=1)

    @field_validator('prompt')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Le prompt est vide.')
        return value.strip()


class VideoTool:
    name = 'video_wan'
    engine = 'comfy'
    description = 'Créer une courte vidéo MP4 muette depuis un texte ou une seule image jointe (Wan 2.2 5B).'
    matches = staticmethod(video_candidate)
    parameters = {
        'prompt': 'description du sujet, du mouvement et de la caméra, max 4000 caractères',
        'negatif': 'texte optionnel', 'largeur': '256..960 multiple de 32, défaut 640',
        'hauteur': '256..960 multiple de 32, défaut 384 ; surface max 960*544',
        'images': '17..73 de forme 4n+1, défaut 49 ; cadence fixe 24 fps, environ 0,7..3 secondes',
        'etapes': '1..30, défaut 20', 'seed': '0..9007199254740991, défaut 0',
        'mode': 't2v sans référence, i2v avec une image jointe',
        'references': '0..1 identifiant image joint de cette discussion, jamais un chemin',
    }

    def __init__(self, engine, files=None):
        self.adapter, self.files = engine, files

    def validate(self, params):
        result = VideoParameters.model_validate(params).model_dump()
        if (result['mode'] == 'i2v') != bool(result['references']):
            raise ParameterError('Image vers vidéo exige une seule image jointe ; texte vers vidéo ne prend pas de référence.')
        if result['images'] % 4 != 1:
            raise ParameterError('Le nombre d’images doit être de forme 4n+1 : 17, 21, …, 73.')
        if result['largeur'] * result['hauteur'] > 960 * 544:
            raise ParameterError('Vidéo trop grande : limitez la surface à 960 × 544 pixels.')
        for file_id in result['references']:
            if not self.files or self.files.get(file_id)['type'] != 'image':
                raise ParameterError('Joignez une image de cette discussion pour l’animer.')
        return result

    async def run(self, params, progress):
        params = self.validate(params)
        uploaded = []
        for file_id in params['references']:
            data, mime = self.files.read(file_id)
            uploaded.append(await self.adapter.upload_image(data, mime))
        return await self.adapter.generate(dict(params, references=uploaded), progress)

    async def artifacts(self, result):
        return [await self.adapter.preview(video) for video in result.get('videos', [])]

    async def preview(self, result, index):
        return await self.adapter.preview(result['videos'][index])
