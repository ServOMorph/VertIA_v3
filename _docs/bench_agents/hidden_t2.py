import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from vertia.app import create_app
from vertia.chemins import resoudre_chemins
from vertia.modules.registry import RegistreModules

FIXTURES = Path(__file__).parent / 'fixtures/modules'


def app_factice(settings, tmp_path):
    engines = {name: SimpleNamespace(start=AsyncMock(), free=AsyncMock()) for name in ('ollama', 'comfy', 'ace')}
    state = dict(gpus=[], ram=dict(percent=1, total_mb=48000, used_mb=100), models=[], processes=[], warnings=[])
    return create_app(settings, overrides=dict(
        modules=RegistreModules(FIXTURES), chemins=resoudre_chemins(tmp_path, environ={}), engines=engines,
        monitor=SimpleNamespace(latest=state, sample=AsyncMock(return_value=state))))


def attendre(client, demande_id):
    for _ in range(300):
        d = client.get('/api/v1/demandes/' + demande_id).json()
        if d['etat'] in {'livre', 'echec', 'annule', 'plafond', 'valide'}:
            return d
        time.sleep(.01)
    raise AssertionError('non terminee')


@pytest.fixture
def client(settings, tmp_path):
    with TestClient(app_factice(settings, tmp_path)) as c:
        yield c


def creer(client, session, texte):
    r = client.post('/api/v1/demandes', json=dict(session=session, capacite='test.echo', params={'texte': texte}))
    assert r.status_code == 202
    attendre(client, r.json()['id'])
    return r.json()['id']


def test_liste_vide(client):
    r = client.get('/api/v1/demandes')
    assert r.status_code == 200 and r.json() == []


def test_liste_tri_et_cles(client):
    ids = [creer(client, 'vertia', 'a'), creer(client, 'vertia', 'b'), creer(client, 'creation_3d', 'c')]
    donnees = client.get('/api/v1/demandes').json()
    assert [d['id'] for d in donnees] == list(reversed(ids))
    for d in donnees:
        assert set(d) == {'id', 'session', 'capacite', 'etat', 'created'}
    assert donnees[0]['session'] == 'creation_3d' and donnees[0]['capacite'] == 'test.echo'


def test_filtre_session_et_etat(client):
    creer(client, 'vertia', 'a')
    creer(client, 'vertia', 'b')
    creer(client, 'creation_3d', 'c')
    assert len(client.get('/api/v1/demandes?session=vertia').json()) == 2
    assert len(client.get('/api/v1/demandes?session=creation_3d').json()) == 1
    assert client.get('/api/v1/demandes?session=absente').json() == []
    assert len(client.get('/api/v1/demandes?etat=livre').json()) == 3
    assert client.get('/api/v1/demandes?etat=echec').json() == []
    assert len(client.get('/api/v1/demandes?session=vertia&etat=livre').json()) == 2


def test_limite(client):
    ids = [creer(client, 'vertia', str(i)) for i in range(4)]
    assert [d['id'] for d in client.get('/api/v1/demandes?limite=2').json()] == [ids[3], ids[2]]
    assert len(client.get('/api/v1/demandes?limite=200').json()) == 4
    assert len(client.get('/api/v1/demandes?limite=1').json()) == 1


@pytest.mark.parametrize('query', ['limite=0', 'limite=201', 'limite=-1', 'limite=abc', 'limite=1.5',
                                   'etat=inconnu', 'etat='])
def test_parametres_invalides(client, query):
    assert client.get('/api/v1/demandes?' + query).status_code == 422


def test_parametres_inconnus_ignores_et_route_detail_intacte(client):
    d = creer(client, 'vertia', 'x')
    assert len(client.get('/api/v1/demandes?truc=1').json()) == 1
    detail = client.get('/api/v1/demandes/' + d)
    assert detail.status_code == 200 and detail.json()['id'] == d
    assert client.get('/api/v1/demandes/absent').status_code == 404


def test_injection_sql_inoffensive(client):
    creer(client, 'vertia', 'x')
    r = client.get("/api/v1/demandes", params={'session': "vertia' OR '1'='1"})
    assert r.status_code == 200 and r.json() == []
