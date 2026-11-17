"""Non-régression musique : travailleur CreaZik (venv d'origine) contre travailleur VertIA (venv recréé), même graine, GPU.

Le jeton GPU doit être détenu par l'appelant (vram_lock.py acquire vertia).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import soundfile

ROOT = Path(__file__).resolve().parents[1]
ACE = ROOT / 'engines/acestep'
CAS = [
    dict(id=1, name='instrumental', type='instrumental', prompt='lofi hip hop, warm piano, soft drums, vinyl crackle',
         duration=30, seed=1234, language='en'),
    dict(id=2, name='chant', type='song', prompt='french pop, female vocal, acoustic guitar, light percussion',
         duration=30, seed=4321, language='fr',
         lyrics='[verse]\nUne radio dans la nuit\nqui chante tout bas\n[chorus]\nla musique est ici\n'),
]


def venv_python(dossier: Path) -> Path:
    return dossier / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def reference(python: Path, worker: Path, dossier: Path) -> dict[int, Path]:
    dossier.mkdir(parents=True)
    shutil.copy(worker, dossier / 'ace_worker.py')
    cfg = dict(ace_step_path=str(ACE), output_dir='sortie', playlist_name='non_regression',
               test_cases=[dict(c, fit_lyrics=True) for c in CAS])
    (dossier / 'config.json').write_text(json.dumps(cfg, ensure_ascii=False), encoding='utf-8')
    subprocess.run([str(python), str(dossier / 'ace_worker.py'), '--config', str(dossier / 'config.json')],
                   check=True, timeout=3600)
    resultats = json.loads((dossier / 'sortie/playlist_results.json').read_text(encoding='utf-8'))
    return {g['test_case_id']: dossier / g['output_file'] for g in resultats['generations']
            if g['status'] == 'generated'}


def vertia(dossier: Path) -> dict[int, Path]:
    env = dict(os.environ, VERTIA_ACESTEP_DIR=str(ACE), PYTHONIOENCODING='utf-8')
    lignes = []
    for cas in CAS:
        sortie = dossier / str(cas['id'])
        sortie.mkdir(parents=True)
        instrumental = cas['type'] == 'instrumental'
        lignes.append(json.dumps(dict(
            action='generation', caption=cas['prompt'], paroles=cas.get('lyrics', ''), instrumental=instrumental,
            vocal_language=cas['language'], duration=cas['duration'], seed=cas['seed'], inference_steps=8,
            lm=False, ajuster_paroles=True, sortie=str(sortie)), ensure_ascii=False))
    script = ROOT / 'modules/musique/travailleurs/travailleur_acestep.py'
    resultat = subprocess.run([str(venv_python(ACE)), '-u', '-B', str(script)], input='\n'.join(lignes) + '\n',
                              capture_output=True, text=True, encoding='utf-8', env=env, timeout=3600)
    reponses = [json.loads(l) for l in resultat.stdout.splitlines() if l.strip()]
    if not reponses or reponses[0] != {'pret': True} or any(r.get('ok') is not True for r in reponses[1:]):
        raise SystemExit(f'Travailleur VertIA en échec : {resultat.stdout}\n{resultat.stderr[-3000:]}')
    return {cas['id']: dossier / str(cas['id']) / 'musique_1.wav' for cas in CAS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origine-ace', type=Path, required=True, help='dossier ACE-Step d’origine (son venv)')
    parser.add_argument('--worker-reference', type=Path, required=True, help='ace_worker.py de CreaZik (copié, non modifié)')
    parser.add_argument('--controle', action='store_true', help='référence contre elle-même (déterminisme GPU)')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporaire:
        a = reference(venv_python(args.origine_ace), args.worker_reference, Path(temporaire, 'reference'))
        if args.controle:
            b = reference(venv_python(args.origine_ace), args.worker_reference, Path(temporaire, 'reference_2'))
        else:
            b = vertia(Path(temporaire, 'vertia'))
        for cas in CAS:
            if cas['id'] not in a:
                print(f"{cas['name']} : référence en échec")
                continue
            x, sx = soundfile.read(a[cas['id']])
            y, sy = soundfile.read(b[cas['id']])
            if sx != sy or x.shape != y.shape:
                print(f"{cas['name']} : DIFFERENT (sr {sx}/{sy}, forme {x.shape}/{y.shape})")
                continue
            ecart = float(np.max(np.abs(x - y)))
            bruit = float(np.sum((x - y) ** 2))
            snr = float('inf') if bruit == 0 else 10 * np.log10(float(np.sum(x ** 2)) / bruit)
            print(f"{cas['name']} : {'IDENTIQUE' if ecart == 0 else 'ECART'} (écart max {ecart:.2e}, "
                  f"signal/écart {snr:.1f} dB, {len(x) / sx:.1f} s)", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
