import argparse
import base64
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / 'src'))

from modules.image.outil_analyse import SYSTEME  # noqa: E402
from modules.image.vision import analyser_dialogue, cadre_reperage, extraire_boite, zone_vers_source  # noqa: E402

DOSSIER = RACINE / 'benchmarks' / 'retouche_gate'
OLLAMA = 'http://127.0.0.1:11434'
COMFY = 'http://127.0.0.1:8189'
VERROU = RACINE / '_orchestration' / 'vram_lock.py'
QUESTION = "Propose des améliorations locales pour cette image."


def encoder(image):
    tampon = io.BytesIO()
    image.save(tampon, format='PNG')
    return base64.b64encode(tampon.getvalue()).decode('ascii')


def iou(a, b):
    if a is None:
        return 0.0
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def chat(client, modele, messages, options, **extra):
    r = client.post(f'{OLLAMA}/api/chat', json=dict(model=modele, messages=messages, stream=False,
                                                   keep_alive=300, options=options, **extra))
    r.raise_for_status()
    return r.json()['message']['content']


def decharger(client, modele):
    try:
        client.post(f'{OLLAMA}/api/generate', json=dict(model=modele, keep_alive=0))
    except httpx.HTTPError:
        pass


def liberer_comfy(client):
    try:
        client.post(f'{COMFY}/free', json=dict(unload_models=True, free_memory=True))
    except httpx.HTTPError:
        pass


def verrou(*args):
    return subprocess.run([sys.executable, str(VERROU), *args], cwd=RACINE)


def mesurer(client, references, dialogue, reperage):
    resultats = {}
    for nom, ref in references.items():
        source = Image.open(DOSSIER / 'images' / f'{nom}.png').convert('RGB')
        entree = dict(json_strict=False, propositions=0, zones=[])

        apercu = source.copy()
        apercu.thumbnail((896, 896), Image.Resampling.LANCZOS)
        debut = time.monotonic()
        texte = chat(client, dialogue, [dict(role='system', content=SYSTEME),
                                        dict(role='user', content=QUESTION, images=[encoder(apercu)])],
                     dict(num_ctx=8192, temperature=0.2), format='json', think=False)
        entree['duree_dialogue_s'] = round(time.monotonic() - debut, 1)
        try:
            json.loads(texte)
            entree['json_strict'] = True
        except ValueError:
            pass
        try:
            entree['propositions'] = len(analyser_dialogue(texte)[1])
        except Exception as exc:
            entree['erreur_dialogue'] = str(exc)
        entree['reponse_brute'] = texte

        cadre = cadre_reperage(*source.size)
        image = encoder(source.resize(cadre, Image.Resampling.LANCZOS))
        for zone in ref['zones']:
            invite = f"Locate {zone['cible']} in the image, output its bbox coordinates using JSON format."
            texte = chat(client, reperage, [dict(role='user', content=invite, images=[image])], dict(temperature=0))
            boite = zone_vers_source(extraire_boite(texte), cadre, source.size)
            entree['zones'].append(dict(cible=zone['cible'], reference=zone['boite'], modele=boite,
                                        iou=round(iou(boite, zone['boite']), 3)))
        resultats[nom] = entree
        print(nom, entree['json_strict'], entree['propositions'], [z['iou'] for z in entree['zones']], flush=True)
    return resultats


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dialogue', default='gemma4:12b')
    p.add_argument('--reperage', default='qwen2.5vl:latest')
    args = p.parse_args()
    references = json.loads((DOSSIER / 'references.json').read_text(encoding='utf-8'))

    limite = time.monotonic() + 1800
    while True:
        r = subprocess.run([sys.executable, str(VERROU), 'acquire', 'vertia', '--gb', '8', '--minutes', '45',
                            '--wait', '--timeout', '1800', '--note', 'gate benchmark retouche dialoguee'],
                           cwd=RACINE, capture_output=True, text=True)
        print(r.stdout.strip(), flush=True)
        if r.returncode != 0:
            sys.exit('Jeton GPU non obtenu.')
        if 'DEJA_DETENU' not in r.stdout:
            break
        if time.monotonic() > limite:
            sys.exit('Jeton vertia tenu par le portail trop longtemps.')
        time.sleep(30)
    try:
        with httpx.Client(timeout=600) as client:
            liberer_comfy(client)
            resultats = mesurer(client, references, args.dialogue, args.reperage)
            decharger(client, args.dialogue)
            decharger(client, args.reperage)
    finally:
        verrou('release', 'vertia')

    zones = [z['iou'] for r in resultats.values() for z in r['zones']]
    reussies = sum(v >= 0.5 for v in zones)
    json_ok = sum(r['json_strict'] and r['propositions'] > 0 for r in resultats.values())
    synthese = dict(
        date=time.strftime('%Y-%m-%d %H:%M'), modeles=dict(dialogue=args.dialogue, reperage=args.reperage),
        zones=len(zones), zones_iou_05=reussies, taux_iou=round(reussies / len(zones), 3),
        json_valides=json_ok, images=len(resultats),
        gate=reussies / len(zones) >= 0.7 and json_ok == len(resultats))
    (DOSSIER / 'resultats.json').write_text(json.dumps(dict(synthese=synthese, details=resultats),
                                                       ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(synthese, ensure_ascii=False))


if __name__ == '__main__':
    main()
