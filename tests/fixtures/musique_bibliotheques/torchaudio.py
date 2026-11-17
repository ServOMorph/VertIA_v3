import os
from types import SimpleNamespace


def info(path):
    if os.environ.get('VERTIA_FAUX_ACE_SONDE_ECHEC'):
        raise RuntimeError('Sonde factice indisponible')
    return SimpleNamespace(sample_rate=24000, num_channels=1, num_frames=32)
