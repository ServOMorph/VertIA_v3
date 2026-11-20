from io import BytesIO
import math
import os
from pathlib import Path
import re
import stat

from PIL import Image, ImageFilter, ImageOps
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vertia.engines.comfy_qwen import build_graph_retouche
from vertia.tools.base import ParameterError


class ParametresRetouche(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source: str
    masque: str | None = None
    prompt: str = Field(min_length=1, max_length=4000)
    negatif: str = ''
    force: float = Field(default=0.85, ge=0.3, le=1)
    etapes: int = Field(default=25, ge=1, le=30)
    seed: int = 0

    @field_validator('prompt')
    @classmethod
    def non_vide(cls, value):
        if not value.strip():
            raise ValueError('Le prompt est vide.')
        return value.strip()


def taille_travail(taille):
    largeur, hauteur = taille
    surface_max = 1_500_000

    def arrondir(facteur):
        return tuple(max(256, 32 * math.floor(cote * facteur / 32 + 0.5)) for cote in taille)

    facteur = max(256 / min(taille), min(1, math.sqrt(surface_max / (largeur * hauteur))))
    resultat = arrondir(facteur)
    if math.prod(resultat) > surface_max:
        bas, haut = 0, facteur
        for _ in range(50):
            milieu = (bas + haut) / 2
            if math.prod(arrondir(milieu)) <= surface_max:
                bas = milieu
            else:
                haut = milieu
        resultat = arrondir(bas)
    return resultat


def png(image):
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def ouvrir_image_inbox(inbox, nom):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', nom) or '..' in nom:
        raise ParameterError('Nom de fichier inbox invalide.')
    limite = 64 * 1024**2
    try:
        racine = inbox.resolve(strict=True)
        chemin = inbox / nom
        infos = chemin.lstat()
        if (not stat.S_ISREG(infos.st_mode) or infos.st_nlink != 1
                or getattr(infos, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or chemin.resolve(strict=True).parent != racine):
            raise ParameterError('Le fichier doit être dans inbox, sans lien.')
        if infos.st_size > limite:
            raise ParameterError('Image supérieure à 64 Mio.')
        with chemin.open('rb') as fichier:
            actuel = os.fstat(fichier.fileno())
            if (actuel.st_ino, actuel.st_dev) != (infos.st_ino, infos.st_dev):
                raise ParameterError('Le fichier inbox a changé pendant la lecture.')
            contenu = fichier.read(limite + 1)
        if len(contenu) > limite:
            raise ParameterError('Image supérieure à 64 Mio.')
        with Image.open(BytesIO(contenu)) as image:
            if image.format not in {'PNG', 'JPEG', 'WEBP'}:
                raise ParameterError('Format attendu : PNG, JPEG ou WebP.')
            if max(image.size) > 8000:
                raise ParameterError('Image supérieure à 8000 pixels de côté.')
            image.verify()
        with Image.open(BytesIO(contenu)) as image:
            return ImageOps.exif_transpose(image).convert('RGB')
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ParameterError(f'Image inbox invalide : {exc}') from exc


class OutilRetouche:
    capacite = 'image.retoucher'
    moteur = 'comfy'
    parameters = {
        'source': 'nom obligatoire d’une image PNG, JPEG ou WebP dans inbox',
        'masque': 'nom optionnel dans inbox ; pixels clairs à retoucher, absent : toute l’image',
        'prompt': 'texte descriptif, 1..4000 caractères',
        'negatif': 'texte optionnel, défaut vide',
        'force': '0.3..1, défaut 0.85', 'etapes': '1..30, défaut 25',
        'seed': 'entier, défaut 0',
    }

    def __init__(self, settings, chemins, moteurs):
        self.adapter = moteurs[self.moteur]
        self.inbox = chemins.inbox_dir

    def _preparer(self, params):
        try:
            params = ParametresRetouche.model_validate(params).model_dump()
        except ValueError as exc:
            raise ParameterError(str(exc)) from exc
        source = ouvrir_image_inbox(self.inbox, params['source'])
        masque = None
        if params['masque'] is not None:
            masque = ouvrir_image_inbox(self.inbox, params['masque']).convert('L')
            rapport = source.width / source.height
            if abs(masque.width / masque.height / rapport - 1) >= 0.02:
                raise ParameterError('Le masque doit avoir les mêmes proportions que la source (écart < 2 %).')
            masque = masque.point(lambda valeur: 255 if valeur > 127 else 0)
            masque = masque.resize(source.size, Image.Resampling.NEAREST)
            if not masque.getbbox():
                raise ParameterError('Le masque ne contient aucune zone à retoucher.')
        return params, source, masque

    def valider(self, params):
        params, _, _ = self._preparer(params)
        return params

    async def executer(self, params, dossier: Path) -> list[Path]:
        params, source, masque = self._preparer(params)
        taille = taille_travail(source.size)
        entree = await self.adapter.upload_image(png(source.resize(taille, Image.Resampling.LANCZOS)), 'image/png')
        masque_envoye = None
        if masque is not None:
            masque_envoye = await self.adapter.upload_image(
                png(masque.resize(taille, Image.Resampling.NEAREST)), 'image/png')
        graphe = build_graph_retouche(dict(params, source=entree, masque=masque_envoye))
        resultat = await self.adapter.generate_graph(graphe, lambda progression: None)
        images = resultat.get('images', [])
        if not images:
            raise ValueError('Le moteur n’a produit aucune image.')
        contenu, mime = await self.adapter.preview(images[0], formats={'.png': 'image/png'})
        if mime != 'image/png' or not contenu:
            raise ValueError('Le moteur doit produire une image PNG non vide.')
        with Image.open(BytesIO(contenu)) as image:
            if image.format != 'PNG':
                raise ValueError('Le moteur doit produire une image PNG.')
            genere = image.convert('RGB').resize(source.size, Image.Resampling.LANCZOS)
        if masque is not None:
            rayon = max(2, 0.004 * max(source.size))
            masque = masque.filter(ImageFilter.GaussianBlur(rayon))
            genere = Image.composite(genere, source, masque)
        fichier = dossier / 'retouche_1.png'
        genere.save(fichier, format='PNG')
        return [fichier]
