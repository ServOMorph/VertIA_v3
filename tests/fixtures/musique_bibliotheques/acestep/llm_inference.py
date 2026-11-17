import os

from . import tracer


class LLMHandler:
    def __init__(self):
        tracer('llm_vide')

    def initialize(self, **kwargs):
        tracer('lm', kwargs=kwargs)
        return 'initialisation LM factice', not os.environ.get('VERTIA_FAUX_ACE_LM_ECHEC')
