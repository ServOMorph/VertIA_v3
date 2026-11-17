import os
from pathlib import Path
from types import SimpleNamespace

from . import tracer


class Session:
    def get_default_settings(self, mode):
        tracer('defauts', mode=mode)
        return dict(model_type=mode, num_inference_steps=30, negative_prompt='négatif par défaut',
                    valeur_speciale=Path('chemin-factice'), imbrique={'chemin': Path('autre')})

    def run_task(self, settings):
        tracer('generation', settings=settings)
        if settings['prompt'] == 'echec':
            raise RuntimeError('Exception factice')
        if settings['prompt'] == 'absent':
            return SimpleNamespace(generated_files=[], errors=['Erreur une', 'Erreur deux'])
        sortie = Path('outputs')
        sortie.mkdir(exist_ok=True)
        video = sortie / 'origine.mp4'
        if settings['prompt'] != 'introuvable':
            video.write_bytes(b'\x00\x00\x00\x18ftypmp42factice')
        return SimpleNamespace(generated_files=[str(video)], errors=[])


def init(*, console_output):
    tracer('init', console_output=console_output, cwd=os.getcwd())
    if os.environ.get('VERTIA_FAUX_WANGP_INIT_ECHEC'):
        raise RuntimeError('Initialisation factice échouée')
    return Session()
