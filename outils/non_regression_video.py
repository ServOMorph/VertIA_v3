"""Non-régression vidéo : appel WanGP de creation_videos (venv d'origine) contre travailleur VertIA (venv recréé).

Même code WanGP (engines/wangp, même commit), mêmes poids, même graine, clip court. Le jeton GPU doit être
détenu par l'appelant (vram_lock.py acquire vertia). Aucune écriture hors du dépôt VertIA et du dossier temporaire.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
WANGP = ROOT / 'engines/wangp'
NEGATIF = 'slow motion, static image, distorted, blurry'
CAS = [
    dict(nom='t2v', mode='t2v', seed=1, image=None,
         prompt='A fishing boat sails across a calm bay at sunrise, gentle waves, seagulls flying, '
                'real-time speed, natural motion, steady camera.'),
    dict(nom='i2v', mode='i2v', seed=1, image='image',
         prompt='The scene comes to life with natural motion at normal speed, steady camera.'),
]


def python_venv(dossier: Path, nom: str) -> Path:
    return dossier / nom / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def reference(python: Path, script: Path, dossier: Path, images: int, image: Path) -> dict[str, Path]:
    dossier.mkdir(parents=True)
    source = script.read_text(encoding='utf-8')
    source, n1 = re.subn(r'(?m)^WANGP = .*$', f'WANGP = Path({str(WANGP)!r})', source)
    source, n2 = re.subn(r'(?m)^FRAMES = .*$', f'FRAMES = {images}', source)
    if (n1, n2) != (1, 1):
        raise SystemExit('Script de référence inattendu : WANGP ou FRAMES introuvable.')
    copie = dossier / 'run_reference.py'
    copie.write_text(source, encoding='utf-8')
    sorties = {}
    for cas in CAS:
        commande = [str(python), '-I', str(copie), cas['mode'], '--prompt', cas['prompt'],
                    '--seed', str(cas['seed']), '--negative', NEGATIF]
        if cas['image']:
            commande += ['--image', str(image)]
        debut = time.time()
        res = subprocess.run(commande, cwd=WANGP, capture_output=True, text=True, encoding='utf-8',
                             errors='replace', timeout=7200)
        fichiers = [l.strip() for l in res.stdout.splitlines() if l.strip().lower().endswith('.mp4')]
        if res.returncode != 0 or not fichiers:
            print(f"{cas['nom']} : référence en échec ({res.returncode})\n{res.stderr[-2000:]}", flush=True)
            continue
        cible = dossier / f"{cas['nom']}.mp4"
        shutil.move(WANGP / fichiers[-1], cible)
        sorties[cas['nom']] = cible
        print(f"{cas['nom']} : référence {time.time() - debut:.0f} s", flush=True)
    return sorties


def vertia(dossier: Path, images: int, image: Path) -> dict[str, Path]:
    env = dict(os.environ, VERTIA_WANGP_DIR=str(WANGP), PYTHONIOENCODING='utf-8')
    lignes = []
    for cas in CAS:
        sortie = dossier / cas['nom']
        sortie.mkdir(parents=True)
        requete = dict(action='generation', mode=cas['mode'], prompt=cas['prompt'], negative_prompt=NEGATIF,
                       seed=cas['seed'], video_length=images, resolution='832x480', sortie=str(sortie))
        if cas['image']:
            copie = sortie / ('image' + image.suffix.lower())
            shutil.copyfile(image, copie)
            requete['image_start'] = str(copie.resolve())
        lignes.append(json.dumps(requete, ensure_ascii=False))
    script = ROOT / 'modules/video/travailleurs/travailleur_wangp.py'
    debut = time.time()
    res = subprocess.run([str(python_venv(WANGP, 'env')), '-u', '-B', str(script)], input='\n'.join(lignes) + '\n',
                         capture_output=True, text=True, encoding='utf-8', errors='replace', env=env,
                         timeout=4 * 7200)
    reponses = [json.loads(l) for l in res.stdout.splitlines() if l.strip().startswith('{')]
    if not reponses or reponses[0] != {'pret': True} or any(r.get('ok') is not True for r in reponses[1:]):
        raise SystemExit(f'Travailleur VertIA en échec : {res.stdout[-3000:]}\n{res.stderr[-3000:]}')
    print(f'vertia : {time.time() - debut:.0f} s', flush=True)
    return {cas['nom']: dossier / cas['nom'] / 'video_1.mp4' for cas in CAS}


def comparer(a: Path, b: Path) -> str:
    ffmpeg = os.environ.get('VERTIA_FFMPEG') or shutil.which('ffmpeg')
    if not ffmpeg:
        raise SystemExit('ffmpeg introuvable.')
    res = subprocess.run([ffmpeg, '-hide_banner', '-i', str(a), '-i', str(b), '-lavfi', 'psnr', '-f', 'null', '-'],
                         capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
    ligne = [l for l in res.stderr.splitlines() if 'PSNR' in l]
    return ligne[-1].split('PSNR', 1)[1].strip() if ligne else 'comparaison impossible : ' + res.stderr[-500:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origine-wangp', type=Path, required=True, help='dossier WanGP d’origine (son venv env_uv)')
    parser.add_argument('--script-reference', type=Path, default=ROOT / '_codex/reference/wangp_run_reference.py')
    parser.add_argument('--image', type=Path, required=True, help='image de départ du cas i2v')
    parser.add_argument('--images', type=int, default=17, help='nombre d’images, forme 4n+1')
    parser.add_argument('--controle', action='store_true', help='référence contre elle-même (déterminisme GPU)')
    parser.add_argument('--garder', type=Path, help='dossier où conserver les vidéos produites')
    args = parser.parse_args()
    if args.images < 17 or args.images % 4 != 1:
        parser.error('--images doit valoir 17, 21, 25...')
    with tempfile.TemporaryDirectory() as temporaire:
        python = python_venv(args.origine_wangp, 'env_uv')
        a = reference(python, args.script_reference, Path(temporaire, 'reference'), args.images, args.image)
        if args.controle:
            b = reference(python, args.script_reference, Path(temporaire, 'reference_2'), args.images, args.image)
        else:
            b = vertia(Path(temporaire, 'vertia'), args.images, args.image)
        for cas in CAS:
            if cas['nom'] in a and cas['nom'] in b:
                print(f"{cas['nom']} : PSNR {comparer(a[cas['nom']], b[cas['nom']])}", flush=True)
        if args.garder:
            args.garder.mkdir(parents=True, exist_ok=True)
            for prefixe, sorties in (('reference', a), ('comparee', b)):
                for nom, chemin in sorties.items():
                    shutil.copyfile(chemin, args.garder / f'{prefixe}_{nom}.mp4')
    return 0


if __name__ == '__main__':
    sys.exit(main())
