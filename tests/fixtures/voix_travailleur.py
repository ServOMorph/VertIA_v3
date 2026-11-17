import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave


def ecrire(message):
    print(json.dumps(message), flush=True)


mode = os.environ.get('VERTIA_FAUX_VOIX_MODE', '')
if mode == 'sans_pret':
    time.sleep(60)
elif mode == 'faux_pret':
    ecrire({'pret': False})
else:
    ecrire({'pret': True})

for ligne in sys.stdin:
    p = json.loads(ligne)
    sortie = Path(p['sortie'])
    action = p['action']
    if action == 'mort':
        sys.exit(3)
    if action == 'illisible':
        print('pas du JSON', flush=True)
        continue
    if action == 'structure':
        ecrire({'ok': True, 'fichiers': 'invalide'})
        continue
    if action == 'refus':
        ecrire({'ok': False, 'erreur': 'Refus factice.'})
        continue
    if action == 'attendre':
        (sortie / 'entree.marker').touch()
        time.sleep(60)
    if action == 'arbre':
        enfant = subprocess.Popen(
            [sys.executable, '-B', '-c', 'import time; time.sleep(60)'],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        (sortie / 'arbre.pid').write_text(str(enfant.pid))
        ecrire({'ok': True, 'fichiers': ['arbre.pid']})
        continue
    (sortie / 'requete.json').write_text(json.dumps(p), encoding='utf-8')
    if action == 'transcription':
        assert Path(p['chemin_audio']).parent == sortie
        assert Path(p['chemin_audio']).is_file()
        (sortie / 'transcription.txt').write_text('Bonjour été', encoding='utf-8')
        (sortie / 'transcription.json').write_text(
            json.dumps(dict(texte='Bonjour été', langue='fr', segments=[])), encoding='utf-8')
        fichiers = ['transcription.txt', 'transcription.json']
    else:
        with wave.open(str(sortie / 'voix_1.wav'), 'wb') as audio:
            audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b'\x00\x00' * 32)
        fichiers = ['voix_1.wav']
    ecrire({'ok': True, 'fichiers': fichiers})
