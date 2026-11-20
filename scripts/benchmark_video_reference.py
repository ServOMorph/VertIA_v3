import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / 'benchmarks' / 'veille'
sys.path.insert(0, str(RACINE / 'scripts'))

CAS = [
    ('tasse', "Une tasse de café fumante posée sur une table en bois près d'une fenêtre, lumière du matin, plan fixe."),
    ('foret', "Travelling avant lent dans une forêt de sapins couverte de brume, lumière douce traversant les branches."),
    ('personnage', "Une femme en manteau rouge marche dans une rue pavée sous la pluie, elle ouvre un parapluie, plan moyen."),
]


def vram():
    sortie = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
    return int(sortie[0])


class Sonde(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.pic = 0
        self.actif = True

    def run(self):
        while self.actif:
            try:
                self.pic = max(self.pic, vram())
            except Exception:
                pass
            time.sleep(0.4)


def main():
    dossier = SORTIE / 'video'
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = SORTIE / 'resultats_video_reference.json'
    resultats = []
    base = vram()
    for identifiant, prompt in CAS:
        sonde = Sonde()
        sonde.start()
        debut = time.time()
        processus = subprocess.run(
            [sys.executable, str(RACINE / 'vertia_gen.py'), 'video.generer', '--session', 'vertia', '--prompt', prompt,
             '--param', 'images=17', '--param', 'resolution=832x480', '--param', 'seed=0',
             '--timeout', '1500'],
            capture_output=True, text=True, cwd=RACINE)
        duree = time.time() - debut
        sonde.actif = False
        chemin = processus.stdout.strip().splitlines()[-1] if processus.stdout.strip() else ''
        copie = ''
        if processus.returncode == 0 and chemin and Path(chemin).is_file():
            cible = dossier / f'wan2.1-14b-portail_{identifiant}{Path(chemin).suffix}'
            shutil.copy2(chemin, cible)
            copie = str(cible)
        demande = [ligne for ligne in processus.stderr.splitlines() if ligne.startswith('id=')]
        resultats.append({'cas': identifiant, 'code': processus.returncode, 'duree_s': round(duree, 1),
                          'pic_vram_mib': sonde.pic, 'base_mib': base, 'fichier': copie,
                          'demande': demande[-1] if demande else '', 'erreur': processus.stderr[-500:] if processus.returncode else ''})
        print(identifiant, processus.returncode, round(duree, 1), 's', sonde.pic, 'MiB', flush=True)
        fichier.write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding='utf-8')


main()
