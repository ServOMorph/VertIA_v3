import os
from pathlib import Path
import platform
import subprocess
from types import SimpleNamespace

from acestep import tracer

__version__ = 'torch-factice'
version = SimpleNamespace(cuda='cuda-factice')
cuda = SimpleNamespace(is_available=lambda: False, empty_cache=lambda: tracer('empty_cache'))


def commande(args, **kwargs):
    if args[0] == 'nvidia-smi':
        return SimpleNamespace(stdout='50, 100\n')
    if args[0] == 'git':
        if os.environ.get('VERTIA_FAUX_ACE_REVISION_ECHEC'):
            raise OSError('git factice indisponible')
        return SimpleNamespace(stdout='revision-factice\n')
    if args[0] == 'ffmpeg-factice':
        tracer('ffmpeg', args=args)
        Path(args[-1]).write_bytes(b'RIFFconverti')
        return SimpleNamespace(returncode=0)
    raise AssertionError('Commande externe interdite : ' + repr(args))


subprocess.run = commande
platform.platform = lambda: 'os-factice'
