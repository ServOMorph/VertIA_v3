import base64
import json
from pathlib import Path
import time
from typing import Literal

import httpx
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vertia.engines.base import EngineError
from vertia.tools.base import ParameterError

from .outil_retouche import ouvrir_image_inbox, png
from .vision import analyser_dialogue, cadre_reperage, extraire_boite, zone_vers_source


MOTIF_MODELE = r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$'
SYSTEME = (
    "Tu es l'assistant de retouche d'image de VertIA. Tu proposes uniquement des changements locaux, "
    "réalisables en repeignant une zone précise de l'image (ajouter, retirer ou remplacer un élément, "
    "changer une matière ou une couleur locale), jamais des réglages globaux (luminosité, contraste, saturation). "
    'Réponds en JSON : {"reponse": "texte en français pour l\'utilisateur", "propositions": '
    '[{"titre": "titre court en français", "type": "objet" si l\'élément à modifier est visible, '
    '"emplacement" pour un ajout, "cible": "en anglais, l\'élément visible à repeindre ou l\'endroit visible '
    'où ajouter", "prompt": "en anglais, le résultat voulu dans la zone"}]}. Au plus 4 propositions.'
)


class MessageHistorique(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    role: Literal['user', 'assistant']
    contenu: str = Field(max_length=8000)


class ParametresAnalyse(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source: str
    prompt: str = Field(min_length=1, max_length=4000)
    historique: list[MessageHistorique] | None = Field(default=None, max_length=20)
    modele_dialogue: str = Field(default='gemma4:12b', pattern=MOTIF_MODELE)
    modele_reperage: str = Field(default='qwen2.5vl:latest', pattern=MOTIF_MODELE)
    reperer: bool = True

    @field_validator('prompt')
    @classmethod
    def non_vide(cls, valeur):
        if not valeur.strip():
            raise ValueError('Le prompt est vide.')
        return valeur


def encoder_image(image):
    return base64.b64encode(png(image)).decode('ascii')


class OutilAnalyse:
    capacite = 'image.analyser'
    moteur = 'ollama'
    parameters = {
        'source': 'nom obligatoire d’une image PNG, JPEG ou WebP dans inbox',
        'prompt': 'question, 1..4000 caractères',
        'historique': 'au plus 20 objets {role: user|assistant, contenu: texte de 8000 caractères maximum}',
        'modele_dialogue': 'nom Ollama, défaut gemma4:12b',
        'modele_reperage': 'nom Ollama, défaut qwen2.5vl:latest',
        'reperer': 'booléen, défaut true',
    }

    def __init__(self, settings, chemins, moteurs):
        self.client = getattr(moteurs[self.moteur], 'client', None)
        self.inbox = chemins.inbox_dir

    def _preparer(self, params):
        try:
            params = ParametresAnalyse.model_validate(params).model_dump()
        except ValueError as exc:
            raise ParameterError(str(exc)) from exc
        return params, ouvrir_image_inbox(self.inbox, params['source'])

    def valider(self, params):
        params, _ = self._preparer(params)
        return params

    async def _chat(self, modele, messages, options, *, preparer=False, **parametres):
        try:
            if preparer:
                await self.client.prepare_model(modele)
            response = await self.client.client.post('/api/chat', json=dict(
                model=modele, messages=messages, stream=False, keep_alive=300,
                options=options, **parametres))
            response.raise_for_status()
            resultat = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EngineError(f'La requête Ollama a échoué pour {modele}.') from exc
        if not isinstance(resultat, dict) or resultat.get('error'):
            raise EngineError(f'Réponse Ollama invalide pour {modele}.')
        message = resultat.get('message')
        texte = message.get('content') if isinstance(message, dict) else None
        if not isinstance(texte, str) or not texte.strip():
            raise EngineError(f'Réponse Ollama vide pour {modele}.')
        return texte

    async def executer(self, params, dossier: Path) -> list[Path]:
        params, source = self._preparer(params)
        if self.client is None:
            raise EngineError('Client Ollama partagé indisponible.')

        dialogue = source.copy()
        dialogue.thumbnail((896, 896), Image.Resampling.LANCZOS)
        messages = [dict(role='system', content=SYSTEME)]
        messages.extend(dict(role=m['role'], content=m['contenu']) for m in params['historique'] or [])
        messages.append(dict(role='user', content=params['prompt'], images=[encoder_image(dialogue)]))
        modeles = dict(dialogue=params['modele_dialogue'], reperage=params['modele_reperage'])

        debut = time.monotonic()
        texte = await self._chat(modeles['dialogue'], messages, dict(num_ctx=8192, temperature=0.2),
                                 preparer=True, format='json')
        reponse, propositions = analyser_dialogue(texte)
        durees = dict(dialogue=time.monotonic() - debut, reperage=0.0)

        if params['reperer'] and propositions:
            debut = time.monotonic()
            cadre = cadre_reperage(*source.size)
            image = encoder_image(source.resize(cadre, Image.Resampling.LANCZOS))
            for index, proposition in enumerate(propositions):
                invite = f"Locate {proposition['cible']} in the image, output its bbox coordinates using JSON format."
                texte = await self._chat(modeles['reperage'], [dict(role='user', content=invite, images=[image])],
                                         dict(temperature=0), preparer=index == 0)
                proposition['zone'] = zone_vers_source(extraire_boite(texte), cadre, source.size)
            durees['reperage'] = time.monotonic() - debut

        resultat = dict(reponse=reponse, propositions=propositions, taille=source.size,
                        modeles=modeles, durees_s=durees)
        fichier = dossier / 'analyse_1.json'
        fichier.write_text(json.dumps(resultat, ensure_ascii=False, indent=2), encoding='utf-8')
        return [fichier]
