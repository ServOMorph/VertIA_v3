import argparse
import json
import re
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

OLLAMA = 'http://127.0.0.1:11434'
RACINE = Path(__file__).resolve().parent.parent / 'benchmarks' / 'veille'


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


def appel(modele, prompt):
    corps = {'model': modele, 'stream': False, 'think': False, 'keep_alive': 0,
             'messages': [{'role': 'user', 'content': prompt}],
             'options': {'num_ctx': 8192, 'temperature': 0, 'seed': 7, 'num_predict': 700}}
    requete = urllib.request.Request(OLLAMA + '/api/chat', json.dumps(corps).encode(),
                                     {'Content-Type': 'application/json'})
    with urllib.request.urlopen(requete, timeout=900) as reponse:
        return json.load(reponse)


def controle(cas, texte):
    attendu = cas.get('attendu')
    if cas['type'] != 'auto':
        return None
    if cas['id'] == 'extraction':
        trouve = re.search(r'\{.*\}', texte, re.S)
        if not trouve:
            return False
        try:
            donnees = json.loads(trouve.group(0))
        except ValueError:
            return False
        return (str(donnees.get('client', '')).strip() == attendu['client']
                and str(donnees.get('date', '')).strip() == attendu['date']
                and float(str(donnees.get('montant_ttc', 0)).replace(',', '.')) == attendu['montant_ttc'])
    if cas['id'] == 'raisonnement':
        return attendu in texte.replace('h', ':').replace('H', ':').replace('::', ':') or attendu in texte
    if cas['id'] == 'consigne':
        return texte.strip().strip('.').lower() == attendu.lower()
    return None


def main():
    analyse = argparse.ArgumentParser()
    analyse.add_argument('modeles', nargs='+')
    analyse.add_argument('--sortie', default=str(RACINE / 'resultats_chat.json'))
    options = analyse.parse_args()
    cas_liste = json.loads((RACINE / 'cas_chat.json').read_text(encoding='utf-8'))
    sortie = Path(options.sortie)
    resultats = json.loads(sortie.read_text(encoding='utf-8')) if sortie.exists() else {}
    for modele in options.modeles:
        base = vram()
        try:
            appel(modele, 'Réponds : ok')
        except Exception as erreur:
            resultats[modele] = {'erreur': str(erreur)}
            continue
        time.sleep(2)
        base = vram()
        lignes = []
        for cas in cas_liste:
            sonde = Sonde()
            sonde.start()
            debut = time.time()
            try:
                reponse = appel(modele, cas['prompt'])
            except Exception as erreur:
                sonde.actif = False
                lignes.append({'id': cas['id'], 'erreur': str(erreur)})
                continue
            duree = time.time() - debut
            sonde.actif = False
            texte = reponse['message']['content']
            jetons = reponse.get('eval_count', 0)
            duree_gen = reponse.get('eval_duration', 1) / 1e9
            lignes.append({'id': cas['id'], 'texte': texte, 'jetons': jetons,
                           'jetons_par_s': round(jetons / duree_gen, 1) if duree_gen else None,
                           'duree_s': round(duree, 1), 'chargement_s': round(reponse.get('load_duration', 0) / 1e9, 1),
                           'pic_vram_mib': sonde.pic, 'vram_ajoutee_mib': sonde.pic - base,
                           'controle_auto': controle(cas, texte)})
            time.sleep(1)
        resultats[modele] = {'base_mib': base, 'cas': lignes}
        sortie.write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding='utf-8')
        print(modele, 'fini', flush=True)


main()
