"""Non-régression du module voix : même travailleur, même graine, venv d'origine contre venv VertIA, sur CPU."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import soundfile

ROOT = Path(__file__).resolve().parents[1]
TRAVAILLEURS = ROOT / 'modules/voix/travailleurs'
TEXTE = 'Bienvenue sur la radio locale.'


def venv_python(dossier: Path) -> Path:
    return dossier / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def executer(python: Path, script: str, hf_home: Path, requete: dict, sortie: Path) -> list[str]:
    env = dict(os.environ, HF_HOME=str(hf_home), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               VERTIA_WHISPER_DIR=str(ROOT / 'models/whisper'), PYTHONIOENCODING='utf-8')
    sortie.mkdir(parents=True, exist_ok=True)
    message = json.dumps(dict(requete, sortie=str(sortie)), ensure_ascii=False) + '\n'
    resultat = subprocess.run([str(python), '-u', '-B', str(TRAVAILLEURS / script), '--device', 'cpu'],
                              input=message, capture_output=True, text=True, encoding='utf-8',
                              env=env, cwd=TRAVAILLEURS, timeout=3600)
    lignes = [json.loads(ligne) for ligne in resultat.stdout.splitlines() if ligne.strip()]
    if len(lignes) < 2 or lignes[0] != {'pret': True} or lignes[1].get('ok') is not True:
        raise SystemExit(f'{script} via {python} : échec\n{resultat.stdout}\n{resultat.stderr[-2000:]}')
    return lignes[1]['fichiers']


def comparer_wav(a: Path, b: Path) -> str:
    x, sr_x = soundfile.read(a)
    y, sr_y = soundfile.read(b)
    if sr_x != sr_y or x.shape != y.shape:
        return f'DIFFERENT (sr {sr_x}/{sr_y}, forme {x.shape}/{y.shape})'
    ecart = float(np.max(np.abs(x - y))) if x.size else 0.0
    return f'{"IDENTIQUE" if ecart == 0 else "ECART"} (écart max {ecart:.2e}, {len(x) / sr_x:.1f} s)'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origine-tts', type=Path, required=True, help='dossier TTS_Local d’origine')
    parser.add_argument('--origine-whisper', type=Path, required=True, help='dossier whisper d’origine')
    parser.add_argument('--audio', type=Path, required=True, help='audio de référence pour la transcription')
    parser.add_argument('--moteurs', default='kokoro,chatterbox,whisper')
    args = parser.parse_args()
    reference = ROOT / 'models/voix/references/kokoro_ff_siwis.wav'
    cas = {
        'kokoro': ('travailleur_kokoro.py', dict(action='synthese', texte=TEXTE, langue='fr', seed=0, voix='ff_siwis', vitesse=1.0)),
        'chatterbox': ('travailleur_chatterbox.py', dict(action='synthese', texte=TEXTE, langue='fr', seed=0,
                                             reference=str(reference), exageration=0.5, cfg=0.3, temperature=0.7)),
        'whisper': ('travailleur_whisper.py', dict(action='transcription', chemin_audio=str(args.audio.resolve()),
                                       modele='small', langue='fr')),
    }
    with tempfile.TemporaryDirectory() as temporaire:
        for nom in args.moteurs.split(','):
            script, requete = cas[nom]
            if nom == 'whisper':
                origine = (venv_python(args.origine_whisper), ROOT / 'models/hf')
            else:
                origine = (venv_python(args.origine_tts / nom), args.origine_tts / 'hf_cache')
            vertia = (venv_python(ROOT / 'engines/voix' / nom), ROOT / 'models/hf')
            a, b = Path(temporaire, nom, 'origine'), Path(temporaire, nom, 'vertia')
            fichiers = executer(origine[0], script, origine[1], requete, a)
            executer(vertia[0], script, vertia[1], requete, b)
            if nom == 'whisper':
                ta, tb = (Path(d, 'transcription.txt').read_text(encoding='utf-8') for d in (a, b))
                print(f'whisper : {"IDENTIQUE" if ta == tb else "DIFFERENT"} : {tb!r}', flush=True)
            else:
                print(f'{nom} : {comparer_wav(a / fichiers[0], b / fichiers[0])}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
