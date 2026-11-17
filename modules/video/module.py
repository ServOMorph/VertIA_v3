import os

from vertia.chemins import ROOT, resoudre_chemins
from vertia.engines.base import MemoryNeeds
from vertia.engines.travailleurs import MoteurTravailleurs
from vertia.modules.contrat import Module

from .outil import OutilVideo

POIDS = ['wangp/ckpts']


def python_travailleur(chemins):
    return chemins.engines_dir / 'wangp/env' / (
        'Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def fabrique(settings, chemins):
    moteur = MoteurTravailleurs(chemins, 'Vidéo', {
        'wangp': (python_travailleur(chemins), ROOT / 'modules/video/travailleurs/travailleur_wangp.py'),
    }, environnement=dict(VERTIA_WANGP_DIR=str(chemins.engines_dir / 'wangp'),
                          PYTHONIOENCODING='utf-8'), delai_pret=1200, delai_requete=7200)
    moteur.memory = MemoryNeeds(
        vram_mb=None, note='Wan 2.1 14B int8 : pic mesuré 5,5 Go dans le projet d’origine.')
    return moteur


def sante():
    chemins = resoudre_chemins()
    venvs = [] if python_travailleur(chemins).is_file() else ['wangp']
    poids = [nom for nom in POIDS if not (chemins.models_dir / nom).exists()]
    installation = (chemins.engines_dir / 'wangp/shared/api.py').is_file()
    return dict(pret=not venvs and not poids and installation,
                venvs_manquants=venvs, poids_manquants=poids, installation_presente=installation)


MODULE = Module(nom='video', activite='video', titre='Vidéo', version='0.1.0',
                capacites=['video.generer'], outils={'generer': OutilVideo},
                moteurs={'video': fabrique}, besoins={}, poids=POIDS, sante=sante, lien='/video')
