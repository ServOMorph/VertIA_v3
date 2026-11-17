import json
from pathlib import Path
import sys

print(json.dumps({'pret': True}), flush=True)
for ligne in sys.stdin:
    params = json.loads(ligne)
    sortie = Path(params['sortie'])
    (sortie / 'requete.json').write_text(json.dumps(params), encoding='utf-8')
    (sortie / 'musique_1.wav').write_bytes(b'RIFFfactice')
    (sortie / 'musique_1.json').write_text(json.dumps({'params': params}), encoding='utf-8')
    print(json.dumps({'ok': True, 'fichiers': ['musique_1.wav', 'musique_1.json']}), flush=True)
