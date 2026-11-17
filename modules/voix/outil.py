import os
from pathlib import Path
import re
import stat
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vertia.engines.base import EngineError
from vertia.tools.base import ParameterError

EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg', '.m4a'}


class ParametresSynthese(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    prompt: str = Field(min_length=1, max_length=2000)
    moteur: Literal['chatterbox', 'kokoro'] = 'chatterbox'
    langue: Literal['fr', 'en'] = 'fr'
    voix: str = Field(default='ff_siwis', pattern=r'^[a-z]{2}_[a-z0-9]{1,30}$')
    reference: str | None = None
    exageration: float = Field(default=0.5, ge=0.25, le=2)
    cfg: float = Field(default=0.3, ge=0, le=1)
    temperature: float = Field(default=0.7, ge=0.05, le=2)
    vitesse: float = Field(default=1.0, ge=0.5, le=2)
    seed: int = Field(default=0, ge=0)

    @field_validator('prompt')
    @classmethod
    def non_vide(cls, value):
        if not value.strip():
            raise ValueError('Le texte est vide.')
        return value.strip()

    @model_validator(mode='after')
    def reference_chatterbox(self):
        if self.moteur == 'kokoro' and self.reference is not None:
            raise ValueError('La référence audio est réservée à Chatterbox.')
        return self


class ParametresTranscription(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source: str
    modele: Literal['tiny', 'base', 'small', 'medium', 'large-v3', 'large-v3-turbo'] = 'large-v3-turbo'
    langue: Literal['fr', 'en', 'auto'] = 'fr'


class OutilAudio:
    moteur = 'voix'

    def __init__(self, settings, chemins, moteurs):
        self.adapter = moteurs[self.moteur]
        self.inbox = chemins.inbox_dir
        self.reference = chemins.models_dir / 'voix/references/kokoro_ff_siwis.wav'

    def _ouvrir(self, nom, extensions, limite):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', nom) or '..' in nom:
            raise ParameterError('Nom de fichier inbox invalide.')
        if Path(nom).suffix.lower() not in extensions:
            raise ParameterError('Extension audio non prise en charge.')
        try:
            racine = self.inbox.resolve(strict=True)
            chemin = self.inbox / nom
            infos = chemin.lstat()
            if (not stat.S_ISREG(infos.st_mode) or infos.st_nlink != 1
                    or getattr(infos, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    or chemin.resolve(strict=True).parent != racine):
                raise ParameterError('Le fichier doit être dans inbox, sans lien.')
            if infos.st_size > limite:
                raise ParameterError('Audio trop volumineux.')
            with chemin.open('rb') as fichier:
                actuel = os.fstat(fichier.fileno())
                if (actuel.st_ino, actuel.st_dev) != (infos.st_ino, infos.st_dev):
                    raise ParameterError('Le fichier inbox a changé pendant la lecture.')
                contenu = fichier.read(limite + 1)
            if len(contenu) > limite:
                raise ParameterError('Audio trop volumineux.')
            return contenu
        except OSError as exc:
            raise ParameterError('Audio inbox inaccessible.') from exc

    def _preparer(self, params, modele):
        try:
            return modele.model_validate(params).model_dump()
        except ValueError as exc:
            raise ParameterError(str(exc)) from exc

    @staticmethod
    def _resultats(dossier, noms):
        fichiers = [dossier / nom for nom in noms]
        if any(not p.is_file() or p.is_symlink() or p.resolve().parent != dossier.resolve()
               for p in fichiers):
            raise EngineError('Le travailleur voix n’a pas produit les fichiers attendus.')
        return fichiers


class OutilSynthese(OutilAudio):
    capacite = 'voix.generer'
    parameters = {
        'prompt': 'texte à dire, 1..2000 caractères',
        'moteur': 'chatterbox (défaut) ou kokoro', 'langue': 'fr (défaut) ou en',
        'voix': 'voix Kokoro, défaut ff_siwis', 'reference': 'nom WAV/FLAC/MP3 optionnel dans inbox',
        'exageration': '0.25..2, défaut 0.5', 'cfg': '0..1, défaut 0.3',
        'temperature': '0.05..2, défaut 0.7', 'vitesse': '0.5..2, défaut 1.0',
        'seed': 'entier positif ou nul, défaut 0',
    }

    def valider(self, params):
        params = self._preparer(params, ParametresSynthese)
        if params['reference'] is not None:
            self._ouvrir(params['reference'], {'.wav', '.flac', '.mp3'}, 64 * 1024**2)
        return params

    async def executer(self, params, dossier: Path):
        params = self.valider(params)
        nom = params['moteur']
        requete = dict(action='synthese', texte=params['prompt'], langue=params['langue'], seed=params['seed'])
        if nom == 'chatterbox':
            reference = self.reference
            if params['reference'] is not None:
                reference = dossier / ('reference' + Path(params['reference']).suffix.lower())
                reference.write_bytes(self._ouvrir(params['reference'], {'.wav', '.flac', '.mp3'}, 64 * 1024**2))
            requete.update(reference=str(reference.resolve()), exageration=params['exageration'],
                           cfg=params['cfg'], temperature=params['temperature'])
        else:
            requete.update(voix=params['voix'], vitesse=params['vitesse'])
        await self.adapter.requete(nom, requete, dossier)
        fichiers = self._resultats(dossier, ['voix_1.wav'])
        with fichiers[0].open('rb') as audio:
            if audio.read(4) != b'RIFF':
                raise EngineError('Le travailleur doit produire un WAV non vide (RIFF).')
        return fichiers


class OutilTranscription(OutilAudio):
    capacite = 'voix.transcrire'
    parameters = {
        'source': 'nom WAV/MP3/FLAC/OGG/M4A obligatoire dans inbox, maximum 200 Mio',
        'modele': 'tiny, base, small, medium, large-v3 ou large-v3-turbo (défaut)',
        'langue': 'fr (défaut), en ou auto',
    }

    def valider(self, params):
        params = self._preparer(params, ParametresTranscription)
        self._ouvrir(params['source'], EXTENSIONS, 200 * 1024**2)
        return params

    async def executer(self, params, dossier: Path):
        params = self.valider(params)
        source = dossier / ('source' + Path(params['source']).suffix.lower())
        source.write_bytes(self._ouvrir(params['source'], EXTENSIONS, 200 * 1024**2))
        await self.adapter.requete('whisper', dict(
            action='transcription', chemin_audio=str(source.resolve()), modele=params['modele'],
            langue=None if params['langue'] == 'auto' else params['langue']), dossier)
        return self._resultats(dossier, ['transcription.txt', 'transcription.json'])
