import json
import os
from pathlib import Path


def tracer(action, **valeurs):
    with Path(os.environ['VERTIA_FAUX_WANGP_TRACE']).open('a', encoding='utf-8') as fichier:
        fichier.write(json.dumps(dict(action=action, **valeurs), default=str) + '\n')
    print('Bibliothèque factice : ' + action)
