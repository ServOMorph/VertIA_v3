import os
import platform
import subprocess
from types import SimpleNamespace

from shared import tracer

__version__ = 'torch-factice'
version = SimpleNamespace(cuda='cuda-factice')
cuda = SimpleNamespace(is_available=lambda: False, empty_cache=lambda: tracer('empty_cache'))


def commande(args, **kwargs):
    if args[0] == 'nvidia-smi':
        if os.environ.get('VERTIA_FAUX_WANGP_SONDE_ECHEC'):
            raise OSError('Sonde factice indisponible')
        return SimpleNamespace(stdout='1234\n2345\n' if '--query-gpu=memory.used' in args else '50, 100\n')
    if args[0] == 'git':
        if os.environ.get('VERTIA_FAUX_WANGP_REVISION_ECHEC'):
            raise OSError('git factice indisponible')
        return SimpleNamespace(stdout='revision-factice\n')
    raise AssertionError('Commande externe interdite : ' + repr(args))


subprocess.run = commande
platform.platform = lambda: 'os-factice'
