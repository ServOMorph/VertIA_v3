import json
import os
from pathlib import Path


def tracer(action, **valeurs):
    with Path(os.environ['VERTIA_FAUX_ACE_TRACE']).open('a', encoding='utf-8') as fichier:
        fichier.write(json.dumps(dict(action=action, **valeurs)) + '\n')
    print('Bibliothèque factice : ' + action)
