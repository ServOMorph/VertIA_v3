import json
import threading
from pathlib import Path

from vertia.demandes.livraison import Livraison


def lignes(dossier):
    out = {}
    for f in sorted(Path(dossier).glob('journal*.jsonl')):
        out[f.name] = f.read_text(encoding='utf-8').splitlines()
    return out


def tout(dossier):
    return [json.loads(l) for ls in lignes(dossier).values() for l in ls]


def test_defauts_et_appel_existant(tmp_path):
    l = Livraison(tmp_path)
    l.journal('a', 'creation')
    assert [json.loads(x)['id'] for x in lignes(tmp_path)['journal.jsonl']] == ['a']


def test_rotation_simple_et_ordre(tmp_path):
    l = Livraison(tmp_path, max_octets=300, conservation=3)
    for i in range(30):
        l.journal(f'id{i:03d}', 'evt', pad='x' * 20)
    fichiers = lignes(tmp_path)
    assert set(fichiers) <= {'journal.jsonl', 'journal.1.jsonl', 'journal.2.jsonl', 'journal.3.jsonl'}
    assert 'journal.1.jsonl' in fichiers
    for nom, ls in fichiers.items():
        assert sum(len(x.encode()) + 1 for x in ls) <= 300 or len(ls) == 1
    ordre = []
    for nom in ('journal.3.jsonl', 'journal.2.jsonl', 'journal.1.jsonl', 'journal.jsonl'):
        ordre += [json.loads(x)['id'] for x in fichiers.get(nom, [])]
    assert ordre == sorted(ordre) and ordre[-1] == 'id029'


def test_conservation_limite_les_fichiers(tmp_path):
    l = Livraison(tmp_path, max_octets=200, conservation=2)
    for i in range(60):
        l.journal(f'id{i}', 'evt', pad='y' * 30)
    assert set(lignes(tmp_path)) <= {'journal.jsonl', 'journal.1.jsonl', 'journal.2.jsonl'}
    assert not (tmp_path / 'journal.3.jsonl').exists()


def test_ligne_geante_sans_boucle(tmp_path):
    l = Livraison(tmp_path, max_octets=100, conservation=3)
    l.journal('petit', 'evt')
    l.journal('geant', 'evt', pad='z' * 500)
    l.journal('apres', 'evt')
    ids = [d['id'] for d in tout(tmp_path)]
    assert sorted(ids) == ['apres', 'geant', 'petit']
    geante = [ls for ls in lignes(tmp_path).values() if any('geant' in x for x in ls)][0]
    assert len(geante) == 1


def test_concurrence_aucune_perte_ni_ligne_coupee(tmp_path):
    l = Livraison(tmp_path, max_octets=2000, conservation=60)
    erreurs = []

    def travail(n):
        try:
            for i in range(100):
                l.journal(f'{n}-{i}', 'evt', pad='p' * 15)
        except Exception as exc:
            erreurs.append(repr(exc))

    fils = [threading.Thread(target=travail, args=(n,)) for n in range(8)]
    [f.start() for f in fils]
    [f.join() for f in fils]
    assert not erreurs
    ids = [d['id'] for d in tout(tmp_path)]
    assert len(ids) == 800 and len(set(ids)) == 800


def test_concurrence_plusieurs_instances(tmp_path):
    erreurs = []

    def travail(n):
        l = Livraison(tmp_path, max_octets=1500, conservation=80)
        try:
            for i in range(80):
                l.journal(f'{n}-{i}', 'evt', pad='q' * 10)
        except Exception as exc:
            erreurs.append(repr(exc))

    fils = [threading.Thread(target=travail, args=(n,)) for n in range(6)]
    [f.start() for f in fils]
    [f.join() for f in fils]
    assert not erreurs
    ids = [d['id'] for d in tout(tmp_path)]
    assert len(ids) == 480 and len(set(ids)) == 480


def test_pas_de_fichier_ouvert_entre_deux_appels(tmp_path):
    l = Livraison(tmp_path, max_octets=10_000, conservation=3)
    l.journal('a', 'evt')
    (tmp_path / 'journal.jsonl').rename(tmp_path / 'autre.jsonl')
    (tmp_path / 'autre.jsonl').rename(tmp_path / 'journal.jsonl')
    l.journal('b', 'evt')
    assert [d['id'] for d in tout(tmp_path)] == ['a', 'b']
