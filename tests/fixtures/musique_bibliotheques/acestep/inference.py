from pathlib import Path
from types import SimpleNamespace

from . import tracer


class GenerationParams:
    def __init__(self, **kwargs):
        self.instruction = 'instruction par défaut'
        self.__dict__.update(kwargs)


class GenerationConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def generate_music(dit, llm, *, params, config, save_dir):
    assert dit.__class__.__name__ == 'AceStepHandler'
    assert llm.__class__.__name__ == 'LLMHandler'
    tracer('generation', params=vars(params), config=vars(config), save_dir=save_dir)
    audio = Path(save_dir) / 'factice.wav'
    if params.caption != 'absent':
        audio.write_bytes(b'RIFFfactice')
    return SimpleNamespace(success=params.caption != 'echec', audios=[{'path': str(audio)}],
                           status_message='Échec factice')
