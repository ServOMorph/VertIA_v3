import json
import os
from pathlib import Path
import re
import stat

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vertia.engines.base import EngineError
from vertia.tools.base import ParameterError

EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg', '.m4a'}
LIMITE_AUDIO = 200 * 1024**2


class ParametresMusique(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    prompt: str = Field(min_length=1, max_length=1000)
    paroles: str = Field(default='', max_length=8000)
    instrumental: bool = Field(default_factory=lambda donnees: not donnees.get('paroles', '').strip())
    langue: str = Field(default='en', pattern=r'^(?:[a-z]{2}|unknown)$')
    duree: float = Field(default=60, ge=10, le=600)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    etapes: int = Field(default=8, ge=1, le=100)
    lm: bool = False
    ajuster_paroles: bool = True
    tache: str | None = Field(default=None, pattern=r'^[a-z0-9_]{1,40}$')
    reference: str | None = None
    source: str | None = None
    force_cover: float | None = Field(default=None, ge=0, le=1)
    force_audio: float | None = Field(default=None, ge=0, le=1)
    bpm: int | None = Field(default=None, ge=30, le=300)
    tonalite: str | None = Field(default=None, max_length=20)
    mesure: str | None = Field(default=None, pattern=r'^(?:[1-9]/[1-9][0-9]?|[1-9])$')

    @field_validator('prompt')
    @classmethod
    def non_vide(cls, valeur):
        if not valeur.strip():
            raise ValueError('La description est vide.')
        return valeur.strip()

    @model_validator(mode='after')
    def coherence_paroles(self):
        if self.instrumental and self.paroles.strip():
            raise ValueError('Un instrumental ne peut pas contenir de paroles.')
        return self


class OutilMusique:
    capacite = 'musique.generer'
    moteur = 'musique'
    parameters = {
        'prompt': 'description, 1..1000 caractères', 'paroles': '0..8000 caractères, défaut vide',
        'instrumental': 'booléen, vrai par défaut sans paroles',
        'langue': 'code de deux lettres minuscules ou unknown, défaut en',
        'duree': '10..600 secondes, défaut 60', 'seed': '0..4294967295, défaut 0',
        'etapes': '1..100, défaut 8', 'lm': 'booléen, défaut faux',
        'ajuster_paroles': 'booléen, défaut vrai', 'tache': 'identifiant optionnel de tâche ACE-Step',
        'reference': 'nom WAV/MP3/FLAC/OGG/M4A dans inbox, maximum 200 Mio',
        'source': 'nom WAV/MP3/FLAC/OGG/M4A dans inbox, maximum 200 Mio',
        'force_cover': '0..1, optionnel', 'force_audio': '0..1, optionnel',
        'bpm': '30..300, optionnel', 'tonalite': '20 caractères maximum, optionnel',
        'mesure': '1..9 ou fraction telle que 4/4, optionnel',
    }

    def __init__(self, settings, chemins, moteurs):
        self.adapter = moteurs[self.moteur]
        self.inbox = chemins.inbox_dir

    def _ouvrir(self, nom):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', nom) or '..' in nom:
            raise ParameterError('Nom de fichier inbox invalide.')
        if Path(nom).suffix.lower() not in EXTENSIONS:
            raise ParameterError('Extension audio non prise en charge.')
        try:
            racine = self.inbox.resolve(strict=True)
            chemin = self.inbox / nom
            infos = chemin.lstat()
            if (not stat.S_ISREG(infos.st_mode) or infos.st_nlink != 1
                    or getattr(infos, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    or chemin.resolve(strict=True).parent != racine):
                raise ParameterError('Le fichier doit être dans inbox, sans lien.')
            if infos.st_size > LIMITE_AUDIO:
                raise ParameterError('Audio trop volumineux.')
            with chemin.open('rb') as fichier:
                actuel = os.fstat(fichier.fileno())
                if (actuel.st_ino, actuel.st_dev) != (infos.st_ino, infos.st_dev):
                    raise ParameterError('Le fichier inbox a changé pendant la lecture.')
                contenu = fichier.read(LIMITE_AUDIO + 1)
            if len(contenu) > LIMITE_AUDIO:
                raise ParameterError('Audio trop volumineux.')
            return contenu
        except OSError as exc:
            raise ParameterError('Audio inbox inaccessible.') from exc

    def valider(self, params):
        try:
            params = ParametresMusique.model_validate(params).model_dump()
        except ValueError as exc:
            raise ParameterError(str(exc)) from exc
        for cle in ('reference', 'source'):
            if params[cle] is not None:
                self._ouvrir(params[cle])
        return params

    async def executer(self, params, dossier: Path):
        params = self.valider(params)
        correspondances = dict(prompt='caption', langue='vocal_language', duree='duration',
                               etapes='inference_steps', tache='task_type',
                               force_cover='cover_noise_strength', force_audio='audio_cover_strength',
                               tonalite='keyscale', mesure='timesignature')
        requete = {correspondances.get(cle, cle): valeur for cle, valeur in params.items()
                   if cle not in {'reference', 'source'} and valeur is not None}
        requete['action'] = 'generation'
        for cle, cible in [('reference', 'reference_audio'), ('source', 'src_audio')]:
            if params[cle] is not None:
                copie = dossier / (cle + Path(params[cle]).suffix.lower())
                copie.write_bytes(self._ouvrir(params[cle]))
                requete[cible] = str(copie.resolve())
        await self.adapter.requete('acestep', requete, dossier)
        fichiers = [dossier / nom for nom in ('musique_1.wav', 'musique_1.json')]
        if any(not p.is_file() or p.is_symlink() or p.resolve().parent != dossier.resolve()
               for p in fichiers):
            raise EngineError('Le travailleur musique n’a pas produit les fichiers attendus.')
        try:
            with fichiers[0].open('rb') as audio:
                if audio.read(4) != b'RIFF':
                    raise ValueError('WAV invalide.')
            if not isinstance(json.loads(fichiers[1].read_text(encoding='utf-8')), dict):
                raise ValueError('Métadonnées invalides.')
        except (OSError, ValueError, UnicodeError) as exc:
            raise EngineError('Le travailleur doit produire un WAV RIFF et des métadonnées JSON objet.') from exc
        return fichiers
