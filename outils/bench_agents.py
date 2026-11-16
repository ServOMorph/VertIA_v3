"""Benchmark des agents de délégation sur trois tâches VertIA (revue, code simple, code délicat).

python outils/bench_agents.py --agents codex:medium oc:opencode/glm-5.3-flash-free --tasks t1 t2 t3 [--parallele 3]

Chaque exécution tourne dans une copie propre du dépôt (git worktree dans .tmp_bench/), est chronométrée,
notée par des tests cachés (t2, t3) ou par mots-clés (t1), puis la copie est supprimée.
Résultats ajoutés à _docs/bench_agents/resultats.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / '.venv' / 'Scripts' / 'python.exe'
BENCH = ROOT / '_docs' / 'bench_agents'
TMP = ROOT / '.tmp_bench'
RESULTATS = BENCH / 'resultats.jsonl'
VERROU = threading.Lock()

BUGS_T1 = [
    ('repository.py', 'nouvelle = not conn.execute(', 'nouvelle = bool(conn.execute(',
     ' (session, capacite)).fetchone()', ' (session, capacite)).fetchone())',
     r'nouvelle|analyse_requise|inverse|not '),
    ('livraison.py', 'if any(not path.is_relative_to', 'if all(not path.is_relative_to', None, None,
     r'\ball\b|\bany\b|hors du dossier|is_relative_to|travail'),
    ('livraison.py', ".open('a', encoding='utf-8')", ".open('w', encoding='utf-8')", None, None,
     r"'w'|\"w\"|ecras|écras|append|ajout|tronqu|mode"),
    ('v1.py', 'ge=1, le=5)', 'ge=1, le=50)', None, None, r'\b50\b|le=|essais_max|maximum|borne'),
]
CHEMINS_T1 = {'repository.py': 'src/vertia/demandes/repository.py', 'livraison.py': 'src/vertia/demandes/livraison.py',
              'v1.py': 'src/vertia/api/v1.py'}
TACHES = {
    't1': dict(brief='t1_revue.md', lecture_seule=True, cache=None, tests=None, delai=900,
               autorises=set()),
    't2': dict(brief='t2_liste_demandes.md', lecture_seule=False, cache='hidden_t2.py',
               tests=['tests/test_api_v1.py', 'tests/test_demandes.py'], delai=1500,
               autorises={'src/vertia/api/v1.py', 'src/vertia/demandes/service.py',
                          'src/vertia/demandes/repository.py', 'tests/test_api_v1.py'}),
    't3': dict(brief='t3_rotation_journal.md', lecture_seule=False, cache='hidden_t3.py',
               tests=['tests/test_demandes.py', 'tests/test_api_v1.py'], delai=1800,
               autorises={'src/vertia/demandes/livraison.py', 'tests/test_demandes.py'}),
}
IGNORES = ('_codex/runs', '.tmp_pt', '__pycache__', '.pytest_cache', 'hidden_t')


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', **kw)


def planter_t1(wt):
    for fichier, ancien, nouveau, ancien2, nouveau2, _ in BUGS_T1:
        chemin = wt / CHEMINS_T1[fichier]
        texte = chemin.read_text(encoding='utf-8')
        if ancien not in texte:
            raise RuntimeError(f'bug non plantable : {fichier} {ancien}')
        texte = texte.replace(ancien, nouveau, 1)
        if ancien2:
            if ancien2 not in texte:
                raise RuntimeError(f'bug non plantable (2) : {fichier} {ancien2}')
            texte = texte.replace(ancien2, nouveau2, 1)
        chemin.write_text(texte, encoding='utf-8')


def commande_agent(agent, brief, wt, lecture_seule):
    genre, _, option = agent.partition(':')
    base = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File']
    if genre == 'codex':
        return base + [str(ROOT / '_codex' / 'run_codex.ps1'), '-Brief', str(brief), '-Name', 'bench', '-Root', str(wt),
                       '-Sandbox', 'read-only' if lecture_seule else 'workspace-write',
                       '-Effort', option or 'medium']
    if genre == 'oc':
        return base + [str(ROOT / '_codex' / 'run_opencode.ps1'), '-Brief', str(brief), '-Name', 'bench',
                       '-Root', str(wt), '-Model', option]
    raise ValueError(f'agent inconnu : {agent}')


def tuer(proc):
    sh(['taskkill', '/PID', str(proc.pid), '/T', '/F'])


def lancer(agent, brief, wt, lecture_seule, delai):
    if agent == 'noop':
        return 0, False, ''
    proc = subprocess.Popen(commande_agent(agent, brief, wt, lecture_seule), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    try:
        sortie, _ = proc.communicate(timeout=delai)
        return proc.returncode, False, sortie or ''
    except subprocess.TimeoutExpired:
        tuer(proc)
        try:
            sortie, _ = proc.communicate(timeout=30)
        except Exception:
            sortie = ''
        return -1, True, sortie or ''


def pytest(wt, cibles):
    r = sh([str(PY), '-m', 'pytest', '-q', '-p', 'no:cacheprovider', f'--basetemp={wt / ".tmp_pt"}', *cibles],
           cwd=wt, timeout=600)
    texte = (r.stdout or '') + (r.stderr or '')
    passes = sum(int(m) for m in re.findall(r'(\d+) passed', texte))
    echecs = sum(int(m) for m in re.findall(r'(\d+) (?:failed|error)', texte))
    return passes, echecs, texte[-400:]


def modifications(wt):
    statut = sh(['git', '-C', str(wt), 'status', '--porcelain', '-uall']).stdout.splitlines()
    fichiers = [l[3:].strip().strip('"').replace('\\', '/') for l in statut]
    fichiers = [f for f in fichiers if not any(i in f for i in IGNORES)]
    lignes = 0
    for f in fichiers:
        p = wt / f
        if p.is_file():
            diff = sh(['git', '-C', str(wt), 'diff', '--numstat', '--', f]).stdout.split()
            lignes += int(diff[0]) + int(diff[1]) if len(diff) >= 2 and diff[0].isdigit() else \
                len(p.read_text(encoding='utf-8', errors='replace').splitlines())
    return fichiers, lignes


def noter_t1(wt, rapport):
    trouves = []
    segments = [s for s in re.split(r'\s;\s|\n', rapport) if s.strip()]
    for fichier, *_rest, motif in BUGS_T1:
        trouves.append(any(fichier in s and re.search(motif, s, re.I) for s in segments))
    return trouves


def executer(agent, tache):
    t = TACHES[tache]
    identifiant = f'{agent.replace(":", "_").replace("/", "_")}_{tache}_{uuid.uuid4().hex[:6]}'
    wt = TMP / identifiant
    TMP.mkdir(exist_ok=True)
    resultat = dict(agent=agent, tache=tache, date=time.strftime('%Y-%m-%d %H:%M:%S'))
    try:
        sh(['git', '-C', str(ROOT), 'worktree', 'add', '--detach', str(wt), 'HEAD'], check=True)
        if tache == 't1':
            planter_t1(wt)
            sh(['git', '-C', str(wt), '-c', 'user.name=bench', '-c', 'user.email=bench@local', 'commit', '-a',
                '-q', '-m', 'bugs plantes'], check=True)
        debut = time.perf_counter()
        code, delai_depasse, sortie = lancer(agent, BENCH / t['brief'], wt, t['lecture_seule'], t['delai'])
        resultat.update(duree_s=round(time.perf_counter() - debut), code=code, delai_depasse=delai_depasse)
        fichiers, lignes = modifications(wt)
        hors = [f for f in fichiers if f not in t['autorises']]
        resultat.update(fichiers=fichiers, lignes=lignes, hors_perimetre=hors)
        rapports = sorted((wt / '_codex' / 'runs').glob('*/rapport.md'))
        rapport = rapports[-1].read_text(encoding='utf-8', errors='replace') if rapports else sortie
        resultat['rapport'] = rapport[:1500]
        if tache == 't1':
            resultat['bugs_trouves'] = noter_t1(wt, rapport)
            resultat['score'] = sum(resultat['bugs_trouves']) / len(BUGS_T1)
            resultat['modifie_malgre_lecture_seule'] = [f for f in fichiers if f.startswith(('src/', 'tests/', 'modules/'))
                                                          and not f.startswith('tests/bench_cache')]
        else:
            shutil.copyfile(BENCH / t['cache'], wt / 'tests' / t['cache'].replace('hidden_', 'test_bench_'))
            cible = 'tests/' + t['cache'].replace('hidden_', 'test_bench_')
            p, e, fin = pytest(wt, [cible])
            rp, re_, rfin = pytest(wt, t['tests'])
            resultat.update(cache_passes=p, cache_echecs=e, regression_passes=rp, regression_echecs=re_,
                            score=round(p / (p + e), 2) if p + e else 0.0, fin_tests=fin[-200:])
    except Exception as exc:
        resultat['erreur'] = f'{type(exc).__name__}: {exc}'
    finally:
        sh(['git', '-C', str(ROOT), 'worktree', 'remove', '--force', str(wt)])
        shutil.rmtree(wt, ignore_errors=True)
    with VERROU:
        with RESULTATS.open('a', encoding='utf-8') as f:
            f.write(json.dumps(resultat, ensure_ascii=False) + '\n')
    print(agent, tache, resultat.get('score'), resultat.get('duree_s'), 's', resultat.get('erreur', ''), flush=True)
    return resultat


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--agents', nargs='+', required=True)
    p.add_argument('--tasks', nargs='+', default=['t1', 't2', 't3'])
    p.add_argument('--parallele', type=int, default=2)
    a = p.parse_args()
    travaux = [(agent, tache) for agent in a.agents for tache in a.tasks]
    with ThreadPoolExecutor(max_workers=max(1, a.parallele)) as pool:
        list(pool.map(lambda x: executer(*x), travaux))
    sh(['git', '-C', str(ROOT), 'worktree', 'prune'])


if __name__ == '__main__':
    main()
