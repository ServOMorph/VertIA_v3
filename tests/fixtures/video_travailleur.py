import json
from pathlib import Path
import sys

print(json.dumps({'pret': True}), flush=True)
for ligne in sys.stdin:
    params = json.loads(ligne)
    sortie = Path(params['sortie'])
    (sortie / 'requete.json').write_text(json.dumps(params), encoding='utf-8')
    (sortie / 'video_1.mp4').write_bytes(b'\x00\x00\x00\x18ftypmp42factice')
    (sortie / 'video_1.json').write_text(json.dumps({'params': params}), encoding='utf-8')
    print(json.dumps({'ok': True, 'fichiers': ['video_1.mp4', 'video_1.json']}), flush=True)
