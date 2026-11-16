from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import Mock

import pytest
import uvicorn

from test_api_v1 import app_factice
from test_module_image import image_api

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vertia_gen', ROOT / 'vertia_gen.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


@contextmanager
def faux_serveur(etat='livre', motif_code='', status=202):
    appels = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.repondre()

        def do_POST(self):
            self.repondre()

        def repondre(self):
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else None
            appels.append((self.command, self.path, body))
            if self.path.endswith('/sante'):
                code, result = 200, dict(version_api='1', pret=True)
            elif self.path.endswith('/capacites'):
                code, result = 200, [{'capacite': 'test.echo'}]
            elif self.path.endswith('/demandes'):
                code = status
                result = {'id': 'abc123'} if status == 202 else {'detail': {'motif_code': 'session_inconnue'}}
            else:
                code, result = 200, dict(id='abc123', etat=etat, motif_code=motif_code,
                                         chemins=['/outbox/essai_1.txt'] if etat == 'livre' else [])
            data = json.dumps(result).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, appels
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


def appeler(monkeypatch, port, *args):
    monkeypatch.setenv('VERTIA_PORT', str(port))
    return cli.main(list(args), lanceur=Mock(side_effect=AssertionError('Lancement réel interdit')))


@pytest.mark.parametrize('etat,motif,code', [
    ('livre', '', 0), ('echec', 'gpu_occupe', 4), ('echec', 'moteur', 6),
    ('echec', 'pause', 7), ('plafond', '', 11), ('annule', '', 1),
])
def test_codes_et_sorties(monkeypatch, capsys, etat, motif, code):
    with faux_serveur(etat, motif) as (port, appels):
        assert appeler(monkeypatch, port, 'test.echo', '--session', 'vertia',
                       '--param', 'texte=oui', 'n=2', '--prompt', 'bonjour') == code
    output = capsys.readouterr()
    assert output.err.splitlines()[0] == 'id=abc123'
    assert output.out == ('/outbox/essai_1.txt\n' if code == 0 else '')
    assert appels[1][2]['params'] == {'texte': 'oui', 'n': 2, 'prompt': 'bonjour'}


@pytest.mark.parametrize('sans_attente,code', [(False, 5), (True, 2)])
def test_timeout_et_sans_attente(monkeypatch, capsys, sans_attente, code):
    with faux_serveur('actif') as (port, _):
        args = ['test.echo', '--session', 'vertia', '--timeout', '.05']
        if sans_attente:
            args.append('--sans-attente')
        assert appeler(monkeypatch, port, *args) == code
    assert not capsys.readouterr().out


def test_absence_serveur_demarrage_simule_puis_code_9(monkeypatch, capsys):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    monkeypatch.setenv('VERTIA_PORT', str(port))
    monkeypatch.setenv('VERTIA_START_TIMEOUT', '.01')
    lanceur = Mock()
    assert cli.main(['test.echo', '--session', 'vertia'], lanceur=lanceur) == 9
    lanceur.assert_called_once_with()
    output = capsys.readouterr()
    assert output.err.startswith('id=\n') and not output.out


def test_demarrage_simule_puis_disponible(monkeypatch, capsys):
    with faux_serveur() as (port, _):
        monkeypatch.setenv('VERTIA_PORT', str(port))
        requete = cli.Client.requete
        compteur = 0

        def initialement_absent(self, *args, **kwargs):
            nonlocal compteur
            compteur += 1
            if compteur == 1:
                raise OSError('absent')
            return requete(self, *args, **kwargs)

        monkeypatch.setattr(cli.Client, 'requete', initialement_absent)
        lanceur = Mock()
        assert cli.main(['test.echo', '--session', 'vertia'], lanceur=lanceur) == 0
        lanceur.assert_called_once_with()
    assert capsys.readouterr().out == '/outbox/essai_1.txt\n'


def test_commande_lancement_detachee(monkeypatch):
    popen = Mock()
    monkeypatch.setattr(cli.subprocess, 'Popen', popen)
    cli.lancer_serveur()
    command = popen.call_args.args[0]
    assert command[0].startswith(str(ROOT / '.venv'))
    assert command[1:] == [str(ROOT / 'run.py'), '--headless']
    assert popen.call_args.kwargs['stdout'] == subprocess.DEVNULL
    if os.name == 'nt':
        assert popen.call_args.kwargs['creationflags'] & subprocess.CREATE_NO_WINDOW


@pytest.mark.parametrize('args', [
    [], ['test.echo'], ['test.echo', '--session', 'vertia', '--param', 'invalide'],
    ['test.echo', '--session', 'vertia', '--essais', '6'],
    ['test.echo', '--session', 'vertia', '--timeout', 'nan'],
    ['retour', 'abc'], ['retour', 'abc', 'non'], ['etat'],
])
def test_parametres_cli_invalides(args, capsys):
    lanceur = Mock()
    assert cli.main(args, lanceur=lanceur) == 10
    lanceur.assert_not_called()
    assert not capsys.readouterr().out


@pytest.mark.parametrize('status,code', [(404, 8), (422, 10), (500, 1)])
def test_erreurs_http(monkeypatch, capsys, status, code):
    with faux_serveur(status=status) as (port, _):
        assert appeler(monkeypatch, port, 'test.echo', '--session', 'inconnue') == code
    assert capsys.readouterr().err.startswith('id=\n')


def test_etat_capacites_et_executable(monkeypatch, capsys):
    with faux_serveur() as (port, _):
        assert appeler(monkeypatch, port, 'etat', 'abc123') == 0
        assert capsys.readouterr().out == '/outbox/essai_1.txt\n'
        assert appeler(monkeypatch, port, 'capacites') == 0
        output = capsys.readouterr()
        assert not output.out and 'test.echo' in output.err
        result = subprocess.run([sys.executable, str(ROOT / 'vertia_gen.py'), 'test.echo',
                                 '--session', 'vertia'], capture_output=True, text=True, timeout=5)
        assert result.returncode == 0 and result.stdout == '/outbox/essai_1.txt\n'


@pytest.fixture
def serveur_api(settings, tmp_path):
    app = app_factice(settings, tmp_path)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        assert server.started
        yield port, app
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()
        assert not thread.is_alive()


def test_cli_api_succes_refus_puis_succes_et_plafond(serveur_api, monkeypatch, capsys):
    port, _ = serveur_api
    assert appeler(monkeypatch, port, 'test.echo', '--session', 'vertia', '--param', 'texte=ok') == 0
    output = capsys.readouterr()
    assert len(output.out.splitlines()) == 1
    assert Path(output.out.strip()).read_text() == 'ok'
    assert appeler(monkeypatch, port, 'test.echo', '--session', 'vertia', '--param',
                   'texte=bon', 'echec_jusqu_a=1') == 0
    output = capsys.readouterr()
    demande_id = output.err.splitlines()[0].removeprefix('id=')
    assert Path(output.out.strip()).read_text() == 'mauvais'
    assert appeler(monkeypatch, port, 'retour', demande_id, 'a_refaire', '--motif', 'mauvais résultat') == 0
    assert Path(capsys.readouterr().out.strip()).read_text() == 'bon'
    assert appeler(monkeypatch, port, 'retour', demande_id, 'valide') == 0
    capsys.readouterr()
    assert appeler(monkeypatch, port, 'test.echo', '--session', 'vertia', '--essais', '1',
                   '--param', 'texte=fin', 'echec_jusqu_a=5') == 0
    demande_id = capsys.readouterr().err.splitlines()[0].removeprefix('id=')
    assert appeler(monkeypatch, port, 'retour', demande_id, 'a_refaire') == 11
    assert not capsys.readouterr().out


def test_headless_sans_navigateur_ni_reload(monkeypatch):
    spec_run = importlib.util.spec_from_file_location('vertia_run', ROOT / 'run.py')
    run = importlib.util.module_from_spec(spec_run)
    spec_run.loader.exec_module(run)
    monkeypatch.setattr(run, 'port_in_use', lambda *args: False)
    monkeypatch.setattr(sys, 'argv', ['run.py', '--headless'])
    uvicorn_run, thread = Mock(), Mock()
    monkeypatch.setattr(run.uvicorn, 'run', uvicorn_run)
    monkeypatch.setattr(run.threading, 'Thread', thread)
    run.main()
    thread.assert_not_called()
    assert uvicorn_run.call_args.kwargs['reload'] is False


def brancher_cli_en_memoire(monkeypatch, client):
    def requete(self, chemin, body=None, timeout=5):
        response = (client.get('/api/v1' + chemin) if body is None else
                    client.post('/api/v1' + chemin, json=body))
        if response.status_code >= 400:
            raise cli.ErreurCLI(10 if response.status_code == 422 else 1, response.text)
        return response.json()

    monkeypatch.setattr(cli.Client, 'requete', requete)


@pytest.mark.parametrize('capacite', ['image', 'image.generer'])
def test_cli_image_livre_png(image_api, monkeypatch, capsys, capacite):
    client, moteur, _ = image_api
    brancher_cli_en_memoire(monkeypatch, client)
    lanceur = Mock(side_effect=AssertionError('Lancement interdit'))
    assert cli.main([capacite, '--session', 'vertia', '--prompt', 'paysage',
                     '--param', 'largeur=768', 'hauteur=512', 'seed=123'], lanceur=lanceur) == 0
    output = capsys.readouterr()
    fichier = Path(output.out.strip())
    assert fichier.name == 'essai_1.png' and 'outbox' in fichier.parts
    assert fichier.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert output.err.startswith('id=')
    assert len(moteur.appels) == 1
    assert moteur.appels[0]['largeur'] == 768 and moteur.appels[0]['seed'] == 123
    lanceur.assert_not_called()


@pytest.mark.parametrize('param', ['largeur=257', 'mode=edit', 'seed=-1'])
def test_cli_image_invalide_code_10(image_api, monkeypatch, capsys, param):
    client, moteur, _ = image_api
    brancher_cli_en_memoire(monkeypatch, client)
    assert cli.main(['image', '--session', 'vertia', '--prompt', 'x', '--param', param]) == 10
    assert not capsys.readouterr().out
    assert not moteur.appels
