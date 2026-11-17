from __future__ import annotations

import os
import subprocess

from vertia.chemins import ROOT
from vertia.engines.base import MemoryNeeds
from vertia.engines.travailleurs import MoteurTravailleurs

TRAVAILLEURS = ('chatterbox', 'kokoro', 'whisper')


def python_travailleur(chemins, nom):
    venv = chemins.engines_dir / 'voix' / nom / '.venv'
    return venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


class VoixEngine(MoteurTravailleurs):
    memory = MemoryNeeds(vram_mb=None, note='Besoins VRAM des travailleurs voix à mesurer.')

    def __init__(self, chemins, *, pythons=None, scripts=None, delai_pret=600,
                 delai_requete=1800, launcher=subprocess.Popen):
        interpretes = {nom: python_travailleur(chemins, nom) for nom in TRAVAILLEURS}
        interpretes.update(pythons or {})
        fichiers = {nom: ROOT / 'modules/voix/travailleurs' / f'travailleur_{nom}.py'
                    for nom in TRAVAILLEURS}
        fichiers.update(scripts or {})
        super().__init__(chemins, 'Voix', {nom: (interpretes[nom], fichiers[nom]) for nom in TRAVAILLEURS},
                         environnement=dict(HF_HOME=str(chemins.models_dir / 'hf'),
                                            HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                                            VERTIA_WHISPER_DIR=str(chemins.models_dir / 'whisper'),
                                            PYTHONIOENCODING='utf-8'),
                         delai_pret=delai_pret, delai_requete=delai_requete, launcher=launcher)
