from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
import re
import unicodedata


def image_candidate(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))
    if re.search(r"\b(ne|n')\s*(?:\w+\s+){0,2}(?:genere|cree|dessine).*\bpas\b|\b(?:sans generer|don't|do not)\b", text):
        return False
    noun = re.search(r'\b(image|illustration|photo|dessin|affiche|logo|portrait|picture|poster)\b', text)
    verb = re.search(r'\b(genere|generer|cree|creer|dessine|dessiner|generate|create|draw|produis|realise|fais|retouche|modifie|edit|inpaint)\b|je (?:veux|voudrais|souhaite)|j.aimerais', text)
    return bool(noun and verb or re.search(r'\b(dessine|draw)\b', text))


class ImageParameters(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    prompt: str = Field(min_length=1, max_length=4000)
    negatif: str = Field(default='', max_length=2000)
    largeur: int = Field(default=1024, ge=256, le=1536, multiple_of=32)
    hauteur: int = Field(default=1024, ge=256, le=1536, multiple_of=32)
    etapes: int = Field(default=25, ge=1, le=30)
    seed: int = Field(default=0, ge=0, le=2**53 - 1)
    mode: Literal['t2i', 'edit', 'inpaint'] = 't2i'
    references: list[str] = Field(default_factory=list, max_length=3)
    masque: str | None = None

    @field_validator('prompt')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Le prompt est vide.')
        return value.strip()


class ImageTool:
    name = 'image_qwen'
    description = 'Créer une image ou modifier des images jointes. Masque indisponible.'
    engine = 'comfy'
    matches = staticmethod(image_candidate)
    parameters = {
        'prompt': 'texte descriptif fidèle à la demande, max 4000 caractères',
        'negatif': 'texte optionnel', 'largeur': '256..1536 multiple de 32, défaut 1024',
        'hauteur': '256..1536 multiple de 32, défaut 1024', 'etapes': '1..30, défaut 25',
        'seed': 'entier 0..9007199254740991, défaut 0', 'mode': 't2i ou edit avec pièces jointes',
        'references': '0..3 identifiants de fichiers image joints ; edit en exige au moins un',
    }

    def __init__(self, engine, files=None):
        self.adapter = engine
        self.files = files

    def validate(self, params):
        result = ImageParameters.model_validate(params).model_dump()
        if result['mode'] == 'inpaint' or result['masque']:
            raise ValueError('Inpaint indisponible : aucun éditeur de masque intégré.')
        if (result['mode'] == 'edit') != bool(result['references']):
            raise ValueError('L’édition exige une image jointe ; texte vers image ne prend pas de référence.')
        for file_id in result['references']:
            if not self.files or self.files.get(file_id)['type'] != 'image':
                raise ValueError('Référence image introuvable.')
        if result['largeur'] * result['hauteur'] > 1536 * 1024:
            raise ValueError('Image trop grande : limitez la surface à 1,5 mégapixel.')
        return result

    async def run(self, params, progress):
        params = self.validate(params)
        uploaded = []
        for file_id in params['references']:
            data, mime = self.files.read(file_id)
            uploaded.append(await self.adapter.upload_image(data, mime))
        return await self.adapter.generate(dict(params, references=uploaded), progress)

    async def artifacts(self, result):
        return [await self.adapter.preview(image) for image in result.get('images', [])]

    async def preview(self, result, index):
        return await self.adapter.preview(result['images'][index])
