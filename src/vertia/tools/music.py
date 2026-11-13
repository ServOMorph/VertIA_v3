from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from vertia.tools.base import ParameterError


def music_candidate(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))
    if re.search(r'\b(?:sans generer|ne .*pas|don.t|do not)\b', text):
        return False
    noun = re.search(r'\b(?:musique|chanson|morceau|instrumental|music|song|track)\b', text)
    verb = re.search(r'\b(?:genere|generer|cree|creer|compose|composer|generate|create|produce|fais|produis|realise)\b|je (?:veux|voudrais|souhaite)|j.aimerais', text)
    return bool(noun and verb)


def syllables(line):
    total = 0
    for word in re.findall(r'[a-zàâäéèêëîïôöùûüÿœæç]+', line.lower()):
        word = re.sub('qu', 'q', word)
        count = len(re.findall(r'[aeiouyàâäéèêëîïôöùûüÿœæ]+', word))
        if count > 1 and word.endswith(('e', 'es')):
            count -= 1
        total += count
    return total


def validate_lyrics(text, duration, language):
    sections = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.fullmatch(r'\[(intro|verse|pre-chorus|chorus|bridge|outro)(?: \d+)?(?: - [a-z]+)?\]', line)
        if match:
            sections.append((match[1], []))
        elif not sections or '[' in line or ']' in line:
            raise ParameterError('Chaque section commence par une balise seule sur sa ligne.')
        else:
            if language == 'fr' and syllables(line) > 12:
                raise ParameterError('Ligne de plus de 12 syllabes estimées : raccourcissez les paroles.')
            sections[-1][1].append(line)
    if not {'verse', 'chorus'} <= {tag for tag, _ in sections} or any(not lines for _, lines in sections):
        raise ParameterError('Un couplet [verse], un refrain [chorus] et des sections non vides sont requis.')
    choruses = [lines for tag, lines in sections if tag == 'chorus']
    if any(lines != choruses[0] for lines in choruses):
        raise ParameterError('Les refrains doivent être identiques.')
    if sum(len(lines) for _, lines in sections) * 2.5 + len(sections) * 3 > duration:
        raise ParameterError('Paroles trop longues pour la durée : raccourcissez ou augmentez la durée (135 s maximum).')


class MusicParameters(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    prompt: str = Field(min_length=1, max_length=1000)
    titre: str = Field(min_length=1, max_length=120)
    caption: str = Field(min_length=1, max_length=400)
    bpm: int = Field(default=100, ge=30, le=240)
    duree: int = Field(default=60, ge=20, le=135)
    paroles: str = Field(default='', max_length=6000)
    langue: Literal['fr', 'en'] = 'fr'
    instrumental: bool = False
    seed: int = Field(default=0, ge=0, le=2**32 - 1)

    @field_validator('prompt', 'titre', 'caption')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Texte vide.')
        return value.strip()


class MusicTool:
    name = 'musique_ace'
    description = 'Composer une musique originale chantée ou instrumentale. Cover audio indisponible.'
    engine = 'ace'
    matches = staticmethod(music_candidate)
    parameters = {
        'prompt': 'résumé fidèle de la demande, max 1000 caractères',
        'titre': 'titre original, max 120 caractères',
        'caption': '5 à 8 termes anglais séparés par virgules : genre, voix ou instrumental, instruments précis, production, ambiance ; sans tempo ni tonalité',
        'bpm': 'entier 30..240, défaut 100', 'duree': 'secondes 20..135, défaut 60',
        'instrumental': 'booléen ; true impose paroles vides et caption avec instrumental',
        'langue': 'fr ou en, fidèle à la demande ; défaut fr',
        'paroles': 'texte original, tags seuls [verse]/[chorus]/[bridge]/[outro] ; aucun tag vide, refrains identiques. Lignes de 6..10 syllabes, maximum estimé 12 en français. Budget : 2,5 s par ligne + 3 s par section. <=60 s : 1 couplet, 1 refrain, outro court ; <=100 s : 2 couplets, 2 refrains ; au-delà ajouter un pont si le budget le permet. Ne pas citer d’artiste ni recopier de paroles.',
        'seed': 'entier 0..4294967295, défaut 0',
    }

    def __init__(self, engine):
        self.adapter = engine

    def validate(self, params):
        result = MusicParameters.model_validate(params).model_dump()
        caption = result['caption'].lower()
        if not 5 <= len([term for term in caption.split(',') if term.strip()]) <= 8:
            raise ParameterError('Le caption exige 5 à 8 termes séparés par des virgules.')
        if re.search(r'\b\d+\s*bpm\b|\b[a-g][#b]?\s*(?:major|minor)\b', caption):
            raise ParameterError('Le tempo et la tonalité ne doivent pas figurer dans le caption.')
        no_vocals = bool(re.search(r'\binstrumental\b|\bno vocals\b', caption))
        if result['instrumental']:
            if result['paroles'].strip() or not no_vocals:
                raise ParameterError('Instrumental : paroles vides et caption sans voix requis.')
            result['paroles'] = ''
        else:
            if no_vocals:
                raise ParameterError('Un morceau chanté exige un caption avec voix.')
            validate_lyrics(result['paroles'], result['duree'], result['langue'])
        return result

    async def run(self, params, progress):
        return await self.adapter.generate(self.validate(params), progress)

    async def artifacts(self, result):
        return [await self.adapter.preview(audio) for audio in result['audios']]

    async def preview(self, result, index):
        return await self.adapter.preview(result['audios'][index])
