import os

from vertia.chemins import ROOT, resoudre_chemins
from vertia.engines.base import MemoryNeeds
from vertia.engines.travailleurs import MoteurTravailleurs
from vertia.modules.contrat import Module

from .outil import OutilMusique

POIDS = ['acestep/acestep-v15-turbo', 'acestep/vae', 'acestep/acestep-5Hz-lm-0.6B']


def python_travailleur(chemins):
    return chemins.engines_dir / 'acestep/.venv' / (
        'Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def fabrique(settings, chemins):
    environnement = dict(VERTIA_ACESTEP_DIR=str(chemins.acestep_dir), PYTHONIOENCODING='utf-8')
    environnement.update({nom: None for nom in
                          ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY')})
    moteur = MoteurTravailleurs(chemins, 'Musique', {
        'acestep': (python_travailleur(chemins), ROOT / 'modules/musique/travailleurs/travailleur_acestep.py'),
    }, environnement=environnement)
    moteur.memory = MemoryNeeds(vram_mb=None, note='Besoins VRAM ACE-Step à mesurer.')
    return moteur


def sante():
    chemins = resoudre_chemins()
    venvs = [] if python_travailleur(chemins).is_file() else ['acestep']
    poids = [nom for nom in POIDS if not (chemins.models_dir / nom).exists()]
    installation = (chemins.acestep_dir / 'acestep').is_dir()
    return dict(pret=not venvs and not poids and installation,
                venvs_manquants=venvs, poids_manquants=poids, installation_presente=installation)


MODULE = Module(nom='musique', activite='musique', titre='Musique', version='0.1.0',
                capacites=['musique.generer'], outils={'generer': OutilMusique},
                moteurs={'musique': fabrique}, besoins={}, poids=POIDS, sante=sante, lien='/musique')
