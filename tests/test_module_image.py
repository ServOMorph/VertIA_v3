from __future__ import annotations

import base64
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
import pytest

from test_api_v1 import attendre
from vertia.app import create_app
from vertia.chemins import resoudre_chemins
from vertia.demandes.service import construire
from vertia.modules.registry import RegistreModules

ROOT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


class FauxMoteurImage:
    def __init__(self):
        self.appels = []
        self.previews = []
        self.demarrages = 0

    async def generate(self, params, progress):
        self.appels.append(dict(params))
        progress(100)
        return {'images': [{'filename': 'factice.png', 'type': 'output'}]}

    async def preview(self, image, formats=None):
        self.previews.append(image)
        assert formats == {'.png': 'image/png'}
        return PNG, 'image/png'

    async def start(self):
        self.demarrages += 1

    async def free(self):
        pass

    async def stop(self):
        pass

    async def health(self):
        return True


@pytest.fixture
def image_api(settings, tmp_path):
    registre = RegistreModules(ROOT / 'modules')
    moteur = FauxMoteurImage()
    engines = {name: SimpleNamespace(start=AsyncMock(), free=AsyncMock())
               for name in ('ollama', 'ace')}
    engines['comfy'] = moteur
    state = dict(gpus=[], ram=dict(percent=1, total_mb=48000, used_mb=100),
                 models=[], processes=[], warnings=[])
    app = create_app(settings, overrides=dict(
        modules=registre, chemins=resoudre_chemins(tmp_path, environ={}), engines=engines,
        monitor=SimpleNamespace(latest=state, sample=AsyncMock(return_value=state))))
    assert not registre.erreurs
    assert app.state.services.demandes.outils['image.generer'][0].adapter is moteur
    assert app.state.services.arbiter.engines['comfy'] is moteur
    with TestClient(app) as client:
        yield client, moteur, app


def test_api_image_livraison_et_nouvel_essai(image_api, tmp_path):
    client, moteur, app = image_api
    capacites = client.get('/api/v1/capacites').json()
    assert any(c['capacite'] == 'image.generer' for c in capacites)
    params = dict(prompt='  paysage  ', seed=123, largeur=768, hauteur=512, etapes=12)
    response = client.post('/api/v1/demandes', json=dict(
        session='vertia', capacite='image.generer', params=params))
    assert response.status_code == 202
    demande_id = response.json()['id']
    demande = attendre(client, demande_id)
    cible = tmp_path / 'outbox' / 'vertia' / demande_id / 'essai_1.png'
    assert demande['etat'] == 'livre'
    assert demande['chemins'] == [str(cible.resolve())]
    assert cible.read_bytes() == PNG
    assert len(moteur.appels) == len(moteur.previews) == moteur.demarrages == 1
    assert moteur.appels[0] == dict(params, prompt='paysage', negatif='', mode='t2i', references=[], masque=None)
    assert app.state.services.jobs.list()[0]['engine'] == 'comfy'
    assert client.post(f'/api/v1/demandes/{demande_id}/retour',
                       json={'verdict': 'a_refaire'}).status_code == 200
    assert attendre(client, demande_id)['etat'] == 'livre'
    assert len(moteur.appels) == len(moteur.previews) == 2


@pytest.mark.parametrize('params', [
    {}, {'prompt': ' '}, {'prompt': 'x', 'largeur': '512'},
    {'prompt': 'x', 'largeur': 257}, {'prompt': 'x', 'seed': -1},
    {'prompt': 'x', 'largeur': 1536, 'hauteur': 1536},
    {'prompt': 'x', 'mode': 'edit'}, {'prompt': 'x', 'mode': 'inpaint'},
    {'prompt': 'x', 'references': ['fichier']}, {'prompt': 'x', 'masque': 'masque'},
    {'prompt': 'x', 'masque': ''}, {'prompt': 'x', 'inconnu': 1},
])
def test_api_image_parametres_refuses(image_api, params):
    client, moteur, _ = image_api
    response = client.post('/api/v1/demandes', json=dict(
        session='vertia', capacite='image.generer', params=params))
    assert response.status_code == 422
    assert not moteur.appels and not moteur.previews and not moteur.demarrages


def test_sante_image_passive(tmp_path, monkeypatch):
    module = RegistreModules(ROOT / 'modules').capacites()['image.generer']
    declaration = sys.modules[module.sante.__module__]
    chemins = resoudre_chemins(tmp_path, environ={})
    monkeypatch.setattr(declaration, 'resoudre_chemins', lambda: chemins)
    interdit = Mock(side_effect=AssertionError('Appel moteur interdit'))
    monkeypatch.setattr(FauxMoteurImage, 'start', interdit)
    monkeypatch.setattr(FauxMoteurImage, 'health', interdit)
    avant = set(tmp_path.rglob('*'))
    assert module.sante() == dict(pret=False, installation=False, poids_manquants=module.poids)
    assert set(tmp_path.rglob('*')) == avant
    chemins.comfy_dir.mkdir(parents=True)
    for poids in module.poids:
        fichier = chemins.models_dir / poids
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.touch()
    avant = set(tmp_path.rglob('*'))
    assert module.sante() == dict(pret=True, installation=True, poids_manquants=[])
    assert set(tmp_path.rglob('*')) == avant
    interdit.assert_not_called()
    assert module.moteurs == module.besoins == {}


def test_construire_fabriques_compatibles(tmp_path):
    settings, chemins, moteurs = object(), object(), {'comfy': FauxMoteurImage()}
    assert construire(lambda: 'zero', settings, chemins, moteurs) == 'zero'
    assert construire(lambda s, c: (s, c), settings, chemins, moteurs) == (settings, chemins)
    assert construire(lambda s, c, m: (s, c, m), settings, chemins, moteurs) == (settings, chemins, moteurs)
    factice = RegistreModules(Path(__file__).parent / 'fixtures/modules').capacites()['test.echo']
    outil = construire(factice.outils['echo'], settings, chemins, moteurs)
    assert outil.valider({'texte': 'ok'})['texte'] == 'ok'
    assert construire(outil, settings, chemins, moteurs) is outil

    def erreur_interne(s, c, m):
        raise TypeError('Erreur interne')

    with pytest.raises(TypeError, match='Erreur interne'):
        construire(erreur_interne, settings, chemins, moteurs)
