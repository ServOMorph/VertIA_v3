import os

from . import tracer


class AceStepHandler:
    def initialize_service(self, **kwargs):
        tracer('dit', kwargs=kwargs, cwd=os.getcwd(),
               proxies={cle: os.environ[cle] for cle in
                        ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY')
                        if cle in os.environ})
        return 'initialisation factice', not os.environ.get('VERTIA_FAUX_ACE_INIT_ECHEC')
