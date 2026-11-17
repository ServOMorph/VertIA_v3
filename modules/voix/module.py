from vertia.chemins import resoudre_chemins
from vertia.engines.voix import TRAVAILLEURS, VoixEngine, python_travailleur
from vertia.modules.contrat import Module

from .outil import OutilSynthese, OutilTranscription

POIDS = [
    'hf/hub/models--ResembleAI--chatterbox',
    'hf/hub/models--hexgrad--Kokoro-82M',
    'whisper/large-v3-turbo.pt',
    'voix/references/kokoro_ff_siwis.wav',
]


def fabrique(settings, chemins):
    return VoixEngine(chemins)


def sante():
    chemins = resoudre_chemins()
    venvs = [nom for nom in TRAVAILLEURS if not python_travailleur(chemins, nom).is_file()]
    poids = [nom for nom in POIDS if not (chemins.models_dir / nom).exists()]
    return dict(pret=not venvs and not poids, venvs_manquants=venvs, poids_manquants=poids)


MODULE = Module(nom='voix', activite='voix', titre='Voix', version='0.1.0',
                capacites=['voix.generer', 'voix.transcrire'],
                outils={'generer': OutilSynthese, 'transcrire': OutilTranscription},
                moteurs={'voix': fabrique}, besoins={}, poids=POIDS, sante=sante, lien='/voix')
