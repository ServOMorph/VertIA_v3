from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vertia.engines.base import EngineError
from vertia.tools.base import ParameterError

EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
LIMITE_IMAGE = 50 * 1024**2


class ParametresVideo(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    prompt: str = Field(min_length=1, max_length=4000)
    mode: Literal['t2v', 'i2v'] = 't2v'
    image: str | None = None
    negatif: str = Field(default='', max_length=2000)
    seed: int = Field(default=0, ge=0, le=2**31 - 1)
    images: int = Field(default=81, ge=17, le=81)
    resolution: Literal['832x480', '480x832'] = '832x480'
    etapes: int | None = Field(default=None, ge=1, le=50)

    @field_validator('prompt')
    @classmethod
    def non_vide(cls, valeur):
        if not valeur.strip():
            raise ValueError('La description est vide.')
        return valeur.strip()

    @field_validator('images')
    @classmethod
    def nombre_images(cls, valeur):
        if valeur % 4 != 1:
            raise ValueError('Le nombre d’images doit être de la forme 4n+1.')
        return valeur

    @model_validator(mode='after')
    def coherence_image(self):
        if self.mode == 'i2v' and self.image is None:
            raise ValueError('Une image est requise en i2v.')
        if self.mode == 't2v' and self.image is not None:
            raise ValueError('Une image est interdite en t2v.')
        return self


class OutilVideo:
    capacite = 'video.generer'
    moteur = 'video'
    parameters = {
        'prompt': 'description, 1..4000 caractères', 'mode': 't2v ou i2v, défaut t2v',
        'image': 'nom PNG/JPEG/WebP dans inbox, maximum 50 Mio ; requis en i2v, interdit en t2v',
        'negatif': '0..2000 caractères, défaut vide', 'seed': '0..2147483647, défaut 0',
        'images': '17..81 de forme 4n+1, défaut 81',
        'resolution': '832x480 ou 480x832, défaut 832x480', 'etapes': '1..50, optionnel',
    }

    def __init__(self, settings, chemins, moteurs):
        self.adapter = moteurs[self.moteur]
        self.inbox = chemins.inbox_dir

    def _ouvrir(self, nom):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', nom) or '..' in nom:
            raise ParameterError('Nom de fichier inbox invalide.')
        if Path(nom).suffix.lower() not in EXTENSIONS:
            raise ParameterError('Extension image non prise en charge.')
        try:
            racine = self.inbox.resolve(strict=True)
            chemin = self.inbox / nom
            infos = chemin.lstat()
            if (not stat.S_ISREG(infos.st_mode) or infos.st_nlink != 1
                    or getattr(infos, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    or chemin.resolve(strict=True).parent != racine):
                raise ParameterError('Le fichier doit être dans inbox, sans lien.')
            if infos.st_size > LIMITE_IMAGE:
                raise ParameterError('Image supérieure à 50 Mio.')
            with chemin.open('rb') as fichier:
                actuel = os.fstat(fichier.fileno())
                if (actuel.st_ino, actuel.st_dev) != (infos.st_ino, infos.st_dev):
                    raise ParameterError('Le fichier inbox a changé pendant la lecture.')
                contenu = fichier.read(LIMITE_IMAGE + 1)
            if len(contenu) > LIMITE_IMAGE:
                raise ParameterError('Image supérieure à 50 Mio.')
            with Image.open(BytesIO(contenu)) as image:
                if image.format not in {'PNG', 'JPEG', 'WEBP'}:
                    raise ParameterError('Format attendu : PNG, JPEG ou WebP.')
                if max(image.size) > 8000:
                    raise ParameterError('Image supérieure à 8000 pixels de côté.')
                image.verify()
            return contenu
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            raise ParameterError(f'Image inbox invalide : {exc}') from exc

    def valider(self, params):
        try:
            params = ParametresVideo.model_validate(params).model_dump()
        except ValueError as exc:
            raise ParameterError(str(exc)) from exc
        if params['image'] is not None:
            self._ouvrir(params['image'])
        return params

    async def executer(self, params, dossier: Path):
        params = self.valider(params)
        correspondances = dict(negatif='negative_prompt', images='video_length', etapes='num_inference_steps')
        requete = {correspondances.get(cle, cle): valeur for cle, valeur in params.items()
                   if cle != 'image' and valeur is not None}
        requete['action'] = 'generation'
        if params['image'] is not None:
            copie = dossier / ('image' + Path(params['image']).suffix.lower())
            copie.write_bytes(self._ouvrir(params['image']))
            requete['image_start'] = str(copie.resolve())
        await self.adapter.requete('wangp', requete, dossier)
        fichiers = [dossier / nom for nom in ('video_1.mp4', 'video_1.json')]
        if any(not p.is_file() or p.is_symlink() or p.resolve().parent != dossier.resolve()
               for p in fichiers):
            raise EngineError('Le travailleur vidéo n’a pas produit les fichiers attendus.')
        try:
            with fichiers[0].open('rb') as video:
                if b'ftyp' not in video.read(12):
                    raise ValueError('MP4 invalide.')
            if not isinstance(json.loads(fichiers[1].read_text(encoding='utf-8')), dict):
                raise ValueError('Métadonnées invalides.')
        except (OSError, ValueError, UnicodeError) as exc:
            raise EngineError('Le travailleur doit produire un MP4 et des métadonnées JSON objet.') from exc
        return fichiers
