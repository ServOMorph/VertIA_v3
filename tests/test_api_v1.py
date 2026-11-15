from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest

from vertia.app import create_app
from vertia.chemins import resoudre_chemins
from vertia.modules.registry import RegistreModules


def app_factice(settings, tmp_path):
    engines = {name: SimpleNamespace(start=AsyncMock(), free=AsyncMock()) for name in ('ollama', 'comfy', 'ace')}
    state = dict(gpus=[], ram=dict(percent=1, total_mb=48000, used_mb=100), models=[], processes=[], warnings=[])
    return create_app(settings, overrides=dict(
        modules=RegistreModules(Path(__file__).parent / 'fixtures/modules'),
        chemins=resoudre_chemins(tmp_path, environ={}), engines=engines,
        monitor=SimpleNamespace(latest=state, sample=AsyncMock(return_value=state))))


def attendre(client, demande_id):
    for _ in range(300):
        demande = client.get('/api/v1/demandes/' + demande_id).json()
        if demande['etat'] in {'livre', 'echec', 'annule', 'plafond', 'valide'}:
            return demande
        time.sleep(.01)
    raise AssertionError('Demande non terminée')


def test_api_cycle_et_sante(settings, tmp_path):
    app = app_factice(settings, tmp_path)
    with TestClient(app) as client:
        sante = client.get('/api/v1/sante').json()
        assert sante['version_api'] == '1' and sante['pret']
        assert client.get('/api/v1/capacites').json()[0]['capacite'] == 'test.echo'
        response = client.post('/api/v1/demandes', json=dict(session='vertia', capacite='test.echo', params={'texte': 'ok'}))
        assert response.status_code == 202
        demande_id = response.json()['id']
        assert attendre(client, demande_id)['etat'] == 'livre'
        retour = client.post(f'/api/v1/demandes/{demande_id}/retour', json={'verdict': 'valide'})
        assert retour.json()['etat'] == 'valide'
        assert client.post(f'/api/v1/demandes/{demande_id}/retour', json={'verdict': 'a_refaire'}).status_code == 409
        assert client.get('/api/v1/demandes/inconnu').status_code == 404
        assert client.post('/api/v1/demandes/inconnu/annuler').status_code == 404
        assert client.post('/api/v1/demandes/inconnu/retour', json={'verdict': 'valide'}).status_code == 404
        app.state.services.modules.erreurs.append('module cassé')
        assert client.get('/api/v1/sante').json()['erreurs'] == ['module cassé']
        assert not client.get('/api/v1/sante').json()['pret']


@pytest.mark.parametrize('overrides,code', [
    ({'session': 'inconnue'}, 404), ({'session': '../vertia'}, 422),
    ({'essais_max': 0}, 422), ({'essais_max': 6}, 422), ({'essais_max': True}, 422),
    ({'params': {}}, 422), ({'params': {'texte': 1}}, 422),
    ({'capacite': 'image.generer'}, 422),
])
def test_api_validation(settings, tmp_path, overrides, code):
    with TestClient(app_factice(settings, tmp_path)) as client:
        body = dict(session='vertia', capacite='test.echo', params={'texte': 'ok'})
        body.update(overrides)
        assert client.post('/api/v1/demandes', json=body).status_code == code


def test_api_annulation(settings, tmp_path):
    with TestClient(app_factice(settings, tmp_path)) as client:
        demande_id = client.post('/api/v1/demandes', json=dict(session='vertia', capacite='test.echo',
                                params={'texte': 'ok', 'delai': 30})).json()['id']
        assert client.post(f'/api/v1/demandes/{demande_id}/annuler').json()['etat'] == 'annule'
        assert attendre(client, demande_id)['chemins'] == []


def test_api_refuse_client_distant(settings, tmp_path):
    with TestClient(app_factice(settings, tmp_path), client=('192.0.2.1', 1234)) as client:
        assert client.get('/api/v1/sante').status_code == 403
