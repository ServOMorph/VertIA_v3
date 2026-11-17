import base64
from io import BytesIO
import json
import time

from fastapi.testclient import TestClient
from PIL import Image
import psutil
import pytest

from modules.atelier import serveur


def png(taille=(4, 3)):
    flux = BytesIO()
    Image.new('RGB', taille, 'white').save(flux, format='PNG')
    return flux.getvalue()


@pytest.fixture
def retouche(tmp_path, monkeypatch):
    script = tmp_path / 'faux_vertia_gen.py'
    inbox = tmp_path / 'inbox'
    monkeypatch.setenv('ATELIER_INBOX', str(inbox))
    monkeypatch.setenv('ATELIER_VERTIA_GEN', str(script))
    script.write_text(
        'import pathlib, sys, json\n'
        'p = pathlib.Path(__file__).parent\n'
        '(p / "arguments.json").write_text(json.dumps(sys.argv[1:]))\n'
        '(p / "outbox").mkdir(exist_ok=True)\n'
        f'(p / "outbox/resultat.png").write_bytes({png()!r})\n'
        'print(p / "outbox/resultat.png")\n', encoding='utf-8')
    with TestClient(serveur.creer_app(tmp_path / 'projets', racine_retouche=tmp_path)) as client:
        yield client, script, inbox


def donnees():
    image = base64.b64encode(png()).decode()
    return dict(image=image, masque=image, prompt='Retoucher le ciel', force=.85, etapes=20, seed=-1)


def attendre(client, identifiant):
    limite = time.monotonic() + 10
    while time.monotonic() < limite:
        etat = client.get('/api/retouche/' + identifiant).json()
        if etat['etat'] not in {'attente', 'en_cours'}:
            return etat
        time.sleep(.01)
    pytest.fail('Retouche non terminée')


def demarrer(client):
    reponse = client.post('/api/retouche', json=donnees())
    assert reponse.status_code == 200, reponse.text
    return reponse.json()['id']


def test_succes_arguments_nettoyage(retouche, tmp_path):
    client, _, inbox = retouche
    identifiant = demarrer(client)
    assert attendre(client, identifiant) == {'etat': 'termine', 'message': 'Terminé'}
    resultat = client.get(f'/api/retouche/{identifiant}/resultat')
    assert resultat.content == png()
    assert resultat.headers['content-type'] == 'image/png'
    assert list(inbox.iterdir()) == []
    args = json.loads((tmp_path / 'arguments.json').read_text())
    assert args[:5] == ['image.retoucher', '--session', 'vertia', '--prompt', 'Retoucher le ciel']
    assert args[5:14] == ['--param', f'source=atelier_{identifiant}_source.png', '--param',
                          f'masque=atelier_{identifiant}_masque.png', '--param', 'force=0.85',
                          '--param', 'etapes=20', '--param']
    assert args[14].startswith('seed=') and int(args[14][5:]) >= 0
    assert args[15:] == ['--timeout', '1700']
    assert client.delete(f'/api/retouche/{identifiant}').json()['etat'] == 'termine'
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*') if p.is_file()} == {
        'faux_vertia_gen.py', 'arguments.json', 'outbox/resultat.png'}


@pytest.mark.parametrize('code,message', [*serveur.ERREURS_RETOUCHE.items(), (1, 'erreur interne'), (2, 'erreur interne'), (42, 'erreur interne')])
def test_codes_echec(retouche, code, message):
    client, script, inbox = retouche
    script.write_text(f'import sys\nsys.exit({code})\n')
    identifiant = demarrer(client)
    assert attendre(client, identifiant) == {'etat': 'echec', 'message': message}
    assert client.get(f'/api/retouche/{identifiant}/resultat').status_code == 409
    assert list(inbox.iterdir()) == []


@pytest.mark.parametrize('champ,valeur', [
    ('image', 'invalid!'), ('image', 12), ('masque', ''), ('masque', base64.b64encode(b'\x89PNG\r\n\x1a\n').decode()),
    ('prompt', ''), ('prompt', ' '), ('prompt', 'a' * 4001), ('prompt', None),
    ('force', .29), ('force', 1.01), ('force', True), ('force', '0.8'),
    ('etapes', 0), ('etapes', 31), ('etapes', 1.5), ('etapes', True), ('seed', []), ('seed', -2),
    ('masque', base64.b64encode(png((1, 1))).decode())])
def test_entrees_invalides(retouche, champ, valeur):
    client, _, inbox = retouche
    params = donnees(); params[champ] = valeur
    assert client.post('/api/retouche', json=params).status_code == 400
    assert not inbox.exists()


def test_corps_et_taille_png(retouche, monkeypatch):
    client, _, inbox = retouche
    for contenu in ['{', '[]', 'null']:
        assert client.post('/api/retouche', content=contenu).status_code == 400
    monkeypatch.setattr(serveur, 'MAX_PNG', 5)
    assert client.post('/api/retouche', json=donnees()).status_code == 400
    monkeypatch.setattr(serveur, 'MAX_CORPS_OCTETS', 5)
    assert client.post('/api/retouche', content='123456').status_code == 413
    assert not inbox.exists()


@pytest.mark.parametrize('mode', ['externe', 'absent', 'faux_png', 'vide', 'tronque'])
def test_resultat_refuse(retouche, tmp_path, mode):
    client, script, inbox = retouche
    cible = tmp_path / ('externe.png' if mode == 'externe' else 'outbox/resultat.png')
    cible.parent.mkdir(exist_ok=True)
    if mode not in {'absent', 'vide'}:
        cible.write_bytes(b'pas un png' if mode == 'faux_png' else png()[:40] if mode == 'tronque' else png())
    script.write_text(f'print({str(cible)!r})' if mode != 'vide' else '')
    identifiant = demarrer(client)
    assert attendre(client, identifiant)['etat'] == 'echec'
    assert list(inbox.iterdir()) == []


def test_annulation_arbre_et_conflit(retouche, tmp_path):
    client, script, inbox = retouche
    marqueur = tmp_path / 'enfant.pid'
    script.write_text('import subprocess, sys, time, pathlib\n'
                      'p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])\n'
                      f'marqueur = pathlib.Path({str(marqueur)!r})\n'
                      'temporaire = marqueur.with_suffix(".tmp")\n'
                      'temporaire.write_text(str(p.pid))\n'
                      'temporaire.replace(marqueur)\n'
                      'time.sleep(60)\n')
    identifiant = demarrer(client)
    assert client.post('/api/retouche', json=donnees()).status_code == 409
    assert client.get(f'/api/retouche/{identifiant}/resultat').status_code == 409
    limite = time.monotonic() + 5
    pid = None
    while pid is None and time.monotonic() < limite:
        try:
            pid = int(marqueur.read_text())
        except (FileNotFoundError, PermissionError, ValueError):
            time.sleep(.01)
    assert pid is not None
    assert client.delete(f'/api/retouche/{identifiant}').json()['etat'] == 'annule'
    assert not psutil.pid_exists(pid)
    assert attendre(client, identifiant)['etat'] == 'annule'
    assert list(inbox.iterdir()) == []


def test_inconnu(retouche):
    client, _, _ = retouche
    for methode, chemin in [('get', '/api/retouche/inconnu'), ('get', '/api/retouche/inconnu/resultat'), ('delete', '/api/retouche/inconnu')]:
        assert getattr(client, methode)(chemin).status_code == 404


def test_retention_et_resultat_disparu(retouche, tmp_path):
    client, _, _ = retouche
    ids = []
    for _ in range(21):
        identifiant = demarrer(client); ids.append(identifiant)
        assert attendre(client, identifiant)['etat'] == 'termine'
    assert client.get('/api/retouche/' + ids[0]).status_code == 404
    assert client.get('/api/retouche/' + ids[1]).status_code == 200
    (tmp_path / 'outbox/resultat.png').unlink()
    assert client.get(f'/api/retouche/{ids[-1]}/resultat').status_code == 404
    assert client.get('/api/retouche/' + ids[-1]).json()['etat'] == 'echec'


def test_echec_ecriture_nettoie_la_source(retouche, monkeypatch):
    client, _, inbox = retouche
    ouvrir = serveur.Path.open

    def refuser_masque(chemin, *args, **kwargs):
        if chemin.name.endswith('_masque.png'):
            raise OSError('Écriture refusée')
        return ouvrir(chemin, *args, **kwargs)

    monkeypatch.setattr(serveur.Path, 'open', refuser_masque)
    assert client.post('/api/retouche', json=donnees()).status_code == 500
    assert list(inbox.iterdir()) == []


def test_lien_resultat_hors_outbox(retouche, tmp_path):
    client, script, inbox = retouche
    externe = tmp_path / 'externe.png'; externe.write_bytes(png())
    outbox = tmp_path / 'outbox'; outbox.mkdir()
    lien = outbox / 'lien.png'
    try:
        lien.symlink_to(externe)
    except OSError:
        pytest.skip('Création de liens non autorisée')
    script.write_text(f'print({str(lien)!r})')
    identifiant = demarrer(client)
    assert attendre(client, identifiant)['etat'] == 'echec'
    assert list(inbox.iterdir()) == []
    assert externe.read_bytes() == png()


def test_arret_application_nettoie(retouche, tmp_path, monkeypatch):
    _, script, inbox = retouche
    script.write_text('import time\ntime.sleep(60)\n')
    app = serveur.creer_app(tmp_path / 'projets', racine_retouche=tmp_path)
    with TestClient(app) as client:
        demarrer(client)
    assert list(inbox.iterdir()) == []
