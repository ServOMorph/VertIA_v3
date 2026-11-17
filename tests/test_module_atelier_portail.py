import base64
from dataclasses import replace
from io import BytesIO
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
import httpx
from PIL import Image
import pytest

from modules.atelier import serveur
import vertia.app as portail
from vertia.modules.contrat import Module


@pytest.fixture
def atelier_portail(settings, tmp_path, monkeypatch):
    def reseau_interdit(*args, **kwargs):
        raise AssertionError('Accès réseau réel interdit')

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', reseau_interdit)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', reseau_interdit)
    monkeypatch.setenv('ATELIER_INBOX', str(tmp_path / 'inbox'))
    monkeypatch.setenv('ATELIER_VERTIA_GEN', str(tmp_path / 'vertia_gen.py'))
    atelier = serveur.creer_app(tmp_path / 'projets', racine_retouche=tmp_path)
    monkeypatch.setattr(portail, 'creer_atelier', lambda: atelier)
    moteurs = {nom: SimpleNamespace(start=AsyncMock(), free=AsyncMock(), close=AsyncMock())
               for nom in ('ollama', 'comfy', 'ace')}
    manager = SimpleNamespace(start_background=Mock(), close=AsyncMock())
    etat = dict(gpus=[], ram=dict(percent=1), models=[], processes=[], warnings=[])
    app = portail.create_app(replace(settings, preload_ollama=False), overrides=dict(
        engines=moteurs, ollama_service=manager,
        monitor=SimpleNamespace(latest=etat, sample=AsyncMock(return_value=etat))))
    return app, manager


def test_redirection_page_et_ressources(atelier_portail):
    app, _ = atelier_portail
    with TestClient(app) as client:
        reponse = client.get('/atelier', follow_redirects=False)
        assert reponse.status_code == 307
        assert reponse.headers['location'] == 'http://testserver/atelier/'
        page = client.get('/atelier/')
        assert page.status_code == 200
        assert 'text/html' in page.headers['content-type']
        assert 'Atelier' in page.text
        for chemin in ('css/atelier.css', 'js/app.js', 'js/outils/retouche.js', 'js/calcul-worker.js'):
            assert client.get('/atelier/' + chemin).status_code == 200
        assert client.get('/atelier/api/inconnue').status_code == 404


def test_projet_sous_prefixe(atelier_portail, tmp_path):
    app, _ = atelier_portail
    projet = dict(format='atelier', version=1, largeur=1200, hauteur=800, calques=[])
    with TestClient(app) as client:
        assert client.get('/atelier/api/projets').json() == []
        assert not (tmp_path / 'projets').exists()
        reponse = client.post('/atelier/api/projets/Mandala 1', json=projet)
        assert reponse.status_code == 200
        assert reponse.json() == {'nom': 'Mandala 1'}
        assert client.get('/atelier/api/projets/Mandala 1').json() == projet
        assert client.get('/atelier/api/projets').json() == ['Mandala 1']
    assert (tmp_path / 'projets/Mandala 1.json').is_file()
    assert not list((tmp_path / 'projets').glob('*.tmp'))


def test_module_et_catalogue(atelier_portail):
    app, _ = atelier_portail
    registre = app.state.services.modules
    module = registre.capacites()['image.editer']
    assert isinstance(module, Module)
    assert module in registre.modules()
    assert (module.nom, module.titre, module.lien) == ('atelier', 'Atelier', '/atelier/')
    assert module.capacites == ['image.editer']
    assert module.moteurs == module.outils == {}
    assert module.sante() == dict(pret=True, message='Éditeur local sans moteur')
    with TestClient(app) as client:
        catalogue = client.get('/api/v1/modules').json()
        atelier, = [module for activite in catalogue['activites'] for module in activite['modules']
                    if module['nom'] == 'atelier']
        assert atelier['lien'] == '/atelier/'
        assert atelier['capacites'] == ['image.editer']


def test_chemins_client_relatifs():
    statique = Path(serveur.__file__).parent / 'static'
    for fichier in [statique / 'index.html', *statique.glob('js/**/*.js')]:
        contenu = fichier.read_text(encoding='utf-8')
        for prefixe in ('/api/', '/css/', '/js/'):
            assert prefixe not in contenu, fichier


def test_retouche_sous_prefixe(atelier_portail, tmp_path, monkeypatch):
    app, _ = atelier_portail
    flux = BytesIO()
    Image.new('RGB', (4, 3), 'white').save(flux, format='PNG')
    png = flux.getvalue()
    resultat = tmp_path / 'outbox/resultat.png'
    resultat.parent.mkdir()
    resultat.write_bytes(png)
    processus = SimpleNamespace(returncode=0, communicate=Mock(return_value=(
        str(resultat).encode('utf-8'), b'')))
    lanceur = Mock(return_value=processus)
    monkeypatch.setattr(serveur.subprocess, 'Popen', lanceur)
    image = base64.b64encode(png).decode()
    with TestClient(app) as client:
        reponse = client.post('/atelier/api/retouche', json=dict(
            image=image, masque=image, prompt='Retoucher le ciel', seed=42))
        assert reponse.status_code == 200
        identifiant = reponse.json()['id']
        limite = time.monotonic() + 5
        while True:
            etat = client.get(f'/atelier/api/retouche/{identifiant}').json()
            if etat['etat'] not in {'attente', 'en_cours'}:
                break
            assert time.monotonic() < limite, etat
            time.sleep(.01)
        assert etat['etat'] == 'termine'
        reponse = client.get(f'/atelier/api/retouche/{identifiant}/resultat')
        assert reponse.status_code == 200 and reponse.content == png
        assert client.delete(f'/atelier/api/retouche/{identifiant}').json()['etat'] == 'termine'
    commande = lanceur.call_args.args[0]
    assert commande[1] == str(tmp_path / 'vertia_gen.py')
    assert commande[2:7] == ['image.retoucher', '--session', 'vertia', '--prompt', 'Retoucher le ciel']
    assert 'seed=42' in commande
    assert list((tmp_path / 'inbox').iterdir()) == []


@pytest.mark.parametrize('erreur_arret', [False, True])
def test_lifespan_annule_retouche_et_ferme_portail(atelier_portail, tmp_path, monkeypatch, erreur_arret):
    app, manager = atelier_portail
    demarre, arrete = threading.Event(), threading.Event()

    class Processus:
        pid = 123
        returncode = 0

        def __init__(self, *args, **kwargs):
            demarre.set()

        def communicate(self, timeout=None):
            assert arrete.wait(5), 'Le faux travail doit être arrêté par le lifespan'
            return b'', b''

    def arreter(processus):
        assert processus.pid == 123
        arrete.set()

    monkeypatch.setattr(serveur.subprocess, 'Popen', Processus)
    monkeypatch.setattr(serveur, 'arreter_arbre', arreter)
    if erreur_arret:
        app.state.services.demandes.close = AsyncMock(side_effect=RuntimeError('Arrêt factice'))
    flux = BytesIO()
    Image.new('RGB', (4, 3), 'white').save(flux, format='PNG')
    image = base64.b64encode(flux.getvalue()).decode()

    def utiliser():
        with TestClient(app) as client:
            manager.start_background.assert_called_once()
            reponse = client.post('/atelier/api/retouche', json=dict(
                image=image, masque=image, prompt='Retoucher le ciel'))
            assert reponse.status_code == 200
            identifiant = reponse.json()['id']
            assert demarre.wait(5)
            assert client.get(f'/atelier/api/retouche/{identifiant}').json()['etat'] == 'en_cours'
            assert len(list((tmp_path / 'inbox').glob('*.png'))) == 2
        return identifiant

    if erreur_arret:
        with pytest.raises(RuntimeError, match='Arrêt factice'):
            utiliser()
    else:
        identifiant = utiliser()
        assert TestClient(app).get(f'/atelier/api/retouche/{identifiant}').json()['etat'] == 'annule'
    assert arrete.is_set()
    assert list((tmp_path / 'inbox').iterdir()) == []
    manager.close.assert_awaited_once()
