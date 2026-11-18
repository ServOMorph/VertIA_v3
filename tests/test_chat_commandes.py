from __future__ import annotations

import base64
import json
import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from vertia.app import create_app
from vertia.chat.commandes import MAX_CAPTURE, MAX_TEXT, PNG_MAGIC, last_deliverable, read_inbox, save_capture
from vertia.chemins import resoudre_chemins
from test_chat import FakeOllama, make_service


@pytest.fixture
def command_client(settings, tmp_path):
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    fake = FakeOllama()
    app = create_app(replace(settings, preload_ollama=False), overrides={
        'ollama': fake, 'chemins': resoudre_chemins(inbox_dir=inbox),
    })
    svc = app.state.services
    with TestClient(app) as client:
        conv = client.post('/api/conversations', json={'modele': 'fake'}).json()
        path = '/api/conversations/' + conv['id']
        yield client, svc, fake, conv['id'], path, inbox


def send(client, path, text):
    return client.post(path + '/messages', json={'contenu': text})


def deliverable(svc, conv_id, text='```livrable html\n<h1>Bonjour</h1>\n```'):
    svc.chat.repository.append(conv_id, 'user', 'Un livrable', 'termine')
    svc.chat.repository.append(conv_id, 'assistant', text, 'termine')


def test_help_and_unknown_never_use_ollama_or_jobs(command_client, monkeypatch):
    client, svc, fake, conv_id, path, _ = command_client
    monkeypatch.setattr(svc.chat, 'submit', Mock(side_effect=AssertionError('Ollama interdit')))
    monkeypatch.setattr(svc.jobs, 'submit', Mock(side_effect=AssertionError('GPU interdit')))
    monkeypatch.setattr(svc.jobs, 'run', Mock(side_effect=AssertionError('GPU interdit')))
    response = send(client, path, '/help')
    assert response.status_code == 202
    assert response.json()['local']
    assert all(command in response.json()['contenu'] for command in ('/help', '/write', '/rgpd'))
    assert client.get('/api/chat/aide').json() == response.json()
    response = send(client, path, '/inconnue')
    assert response.status_code == 422
    assert all(command in response.json()['detail'] for command in ('/help', '/write', '/rgpd'))
    assert svc.chat.messages(conv_id) == []
    assert fake.calls == []


def test_rgpd_original_never_persisted_and_no_generation(command_client, monkeypatch):
    client, svc, fake, conv_id, path, _ = command_client
    monkeypatch.setattr(svc.jobs, 'run', Mock(side_effect=AssertionError('GPU interdit')))
    original = 'Mme Alice Martin : alice@example.fr, 06 12 34 56 78'
    response = send(client, path, '/rgpd ' + original)
    assert response.status_code == 202
    messages = client.get(path).json()['messages']
    assert messages[0]['contenu'] == f'/rgpd [texte non conservé, {len(original)} caractères]'
    assert all(m['statut'] == 'termine' for m in messages)
    assert '[DONNÉE_SENSIBLE]' in messages[1]['contenu']
    assert 'email : 1' in messages[1]['contenu'] and 'nom : 1' in messages[1]['contenu']
    assert original not in json.dumps(messages)
    with svc.db.session() as conn:
        assert 'alice@example.fr' not in str([tuple(r) for r in conn.execute('SELECT * FROM messages')])
        assert conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
    assert fake.calls == [] and not svc.chat.pending


@pytest.mark.asyncio
async def test_local_reply_sse(tmp_path):
    service, repo, fake = make_service(tmp_path)
    conv_id = repo.create_conversation('fake', None, False)['id']
    stream = service.events.subscribe()
    await anext(stream)
    result = service.local_reply(conv_id, '/rgpd [texte non conservé, 1 caractères]', 'Résultat')
    delta, end = await anext(stream), await anext(stream)
    assert delta.startswith('event: chat.delta') and end.startswith('event: chat.fin')
    assert json.loads(delta.split('data: ')[1]) == {**result, 'contenu': 'Résultat', 'offset': 0}
    assert json.loads(end.split('data: ')[1])['statut'] == 'termine'
    assert not fake.calls and not service.pending
    await stream.aclose()
    await service.close()


@pytest.mark.parametrize('filename', [
    '../secret.md', r'..\secret.md', '/absolute.md', r'C:\absolute.md',
    'CON.txt', 'nul.md', 'LPT1.py', 'COM9.json', 'CON .txt',
    'bad.exe', 'file..md', 'file.md/other.md', 'a' * 118 + '.md', 'a.txt:stream',
])
def test_write_invalid_filename(command_client, filename):
    client, svc, fake, conv_id, path, _ = command_client
    deliverable(svc, conv_id)
    assert send(client, path, '/write ' + filename).status_code == 422
    assert not svc.files.list(conv_id) and not fake.calls


def test_write_exclusive_registered_and_downloadable(command_client):
    client, svc, fake, conv_id, path, _ = command_client
    deliverable(svc, conv_id)
    assert send(client, path, '/write page.html').status_code == 202
    files = client.get(path + '/fichiers').json()
    assert len(files) == 1 and files[0]['type'] == 'texte'
    target = svc.files.root / conv_id / 'page.html'
    assert target.read_text(encoding='utf-8') == '<h1>Bonjour</h1>'
    assert files[0]['name'] == target.name
    response = client.get('/api/fichiers/' + files[0]['id'] + '/contenu?telecharger=true')
    assert response.status_code == 200 and response.text == '<h1>Bonjour</h1>'
    assert 'attachment;' in response.headers['content-disposition']
    inline = client.get('/api/fichiers/' + files[0]['id'] + '/contenu')
    assert inline.headers['content-type'].startswith('text/plain')
    assert send(client, path, '/write page.html').status_code == 422
    assert len(svc.files.list(conv_id)) == 1 and not fake.calls
    assert target.read_text(encoding='utf-8') == '<h1>Bonjour</h1>'


def test_write_no_deliverable(command_client):
    client, svc, _, conv_id, path, _ = command_client
    assert send(client, path, '/write test.txt').status_code == 422
    assert svc.chat.messages(conv_id) == []


def test_last_deliverable_ignores_other_code_and_unfinished():
    def message(text, status='termine'):
        return dict(role='assistant', statut=status, contenu=text)
    messages = [message('```livrable html\npremier\n```\n\n~~~~livrable json\n{}\n~~~~'),
                message('```python\nprint(1)\n```'), message('```livrable\nincomplet')]
    assert last_deliverable(messages) == '{}'
    assert last_deliverable([*messages, message('```livrable\nactif\n```', 'actif')]) == '{}'


def test_rgpd_inbox_file_registered_and_original_unchanged(command_client):
    client, svc, fake, conv_id, path, inbox = command_client
    original = 'alice@example.fr'
    (inbox / 'source.txt').write_text(original, encoding='utf-8')
    assert send(client, path, '/rgpd fichier:source.txt').status_code == 202
    assert (inbox / 'source.txt').read_text(encoding='utf-8') == original
    assert list(inbox.iterdir()) == [inbox / 'source.txt']
    target = svc.files.root / conv_id / 'source_anonymise.md'
    assert target.read_text(encoding='utf-8') == '[DONNÉE_SENSIBLE]'
    assert svc.files.list(conv_id)[0]['name'] == target.name
    assert send(client, path, '/rgpd fichier:source.txt').status_code == 422
    assert original not in json.dumps(svc.chat.messages(conv_id)) and not fake.calls


@pytest.mark.parametrize('filename,data', [
    ('source.json', b'{}'), ('source.txt', b'\xff'), ('source.md', b'x' * (MAX_TEXT + 1)),
])
def test_rgpd_invalid_inbox_file(command_client, filename, data):
    client, svc, _, conv_id, path, inbox = command_client
    (inbox / filename).write_bytes(data)
    assert send(client, path, '/rgpd fichier:' + filename).status_code == 422
    assert svc.chat.messages(conv_id) == [] and svc.files.list(conv_id) == []


@pytest.mark.parametrize('source', ['../source.txt', r'C:\source.txt', 'missing.txt', '.'])
def test_rgpd_inbox_path_rejected(command_client, source):
    client, _, _, _, path, _ = command_client
    assert send(client, path, '/rgpd fichier:' + source).status_code == 422


def test_rgpd_hardlink_and_directory_rejected(command_client, tmp_path):
    client, _, _, _, path, inbox = command_client
    source = tmp_path / 'original.txt'
    source.write_text('alice@example.fr', encoding='utf-8')
    os.link(source, inbox / 'linked.txt')
    (inbox / 'folder.txt').mkdir()
    for name in ('linked.txt', 'folder.txt'):
        assert send(client, path, '/rgpd fichier:' + name).status_code == 422


def test_inbox_symlink_rejected(tmp_path):
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    source = tmp_path / 'source.txt'
    source.write_text('alice@example.fr', encoding='utf-8')
    try:
        (inbox / 'link.txt').symlink_to(source)
    except OSError:
        pytest.skip('Création de liens symboliques indisponible.')
    with pytest.raises(ValueError, match='sans lien'):
        read_inbox(inbox, 'link.txt')


def image_body(data):
    return {'image': 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')}


def test_capture_png_destination_and_unique(command_client):
    client, svc, _, _, _, _ = command_client
    data = PNG_MAGIC + b'test'
    responses = [client.post('/api/captures', json=image_body(data)) for _ in range(2)]
    assert all(r.status_code == 201 for r in responses)
    names = [r.json()['fichier'] for r in responses]
    assert names[0] != names[1]
    assert all(n.startswith('capture_') and n.endswith('.png') for n in names)
    assert all((svc.files.root / 'captures' / n).read_bytes() == data for n in names)


@pytest.mark.parametrize('body', [image_body(b'not png'), {'image': 'data:image/png;base64,???'},
                                      {'image': 'data:text/plain;base64,dGVzdA=='}, {}, []])
def test_capture_invalid(command_client, body):
    client, svc, _, _, _, _ = command_client
    assert client.post('/api/captures', json=body).status_code == 422
    assert not (svc.files.root / 'captures').exists()


def test_capture_size_limit(command_client):
    client, svc, _, _, _, _ = command_client
    assert client.post('/api/captures', json=image_body(PNG_MAGIC + b'x' * MAX_CAPTURE)).status_code == 413
    assert not (svc.files.root / 'captures').exists()


def test_capture_collision_never_overwrites(tmp_path, monkeypatch):
    clock = Mock()
    clock.now.return_value.strftime.return_value = 'fixed'
    monkeypatch.setattr('vertia.chat.commandes.datetime', clock)
    folder = tmp_path / 'captures'
    folder.mkdir()
    original = folder / 'capture_fixed.png'
    original.write_bytes(b'original')
    assert save_capture(tmp_path, PNG_MAGIC) == 'capture_fixed_1.png'
    assert original.read_bytes() == b'original'
    assert save_capture(tmp_path, PNG_MAGIC + b'x' * (MAX_CAPTURE - len(PNG_MAGIC))) == 'capture_fixed_2.png'


def test_capture_linked_directory_rejected(tmp_path):
    target = tmp_path / 'elsewhere'
    target.mkdir()
    try:
        (tmp_path / 'captures').symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip('Création de liens symboliques indisponible.')
    with pytest.raises(ValueError, match='sans lien'):
        save_capture(tmp_path, PNG_MAGIC)
    assert list(target.iterdir()) == []


def test_capture_write_failure_removes_partial_file(tmp_path, monkeypatch):
    original_open = Path.open
    class BrokenWrite:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def write(self, data):
            self.stream.write(data[:2])
            raise OSError('disque plein')
    def failing_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return BrokenWrite(stream) if args == ('xb',) else stream
    monkeypatch.setattr(Path, 'open', failing_open)
    with pytest.raises(OSError, match='disque plein'):
        save_capture(tmp_path, PNG_MAGIC)
    assert list((tmp_path / 'captures').iterdir()) == []


def test_model_change_validation_and_failure(command_client, monkeypatch):
    client, svc, _, conv_id, path, _ = command_client
    svc.chat.repository.update_conversation(conv_id, modele='old')
    assert client.patch(path, json={'modele': 'fake'}).json()['modele'] == 'fake'
    for invalid in ('unknown', '', None, '   '):
        assert client.patch(path, json={'modele': invalid}).status_code == 422
    assert svc.chat.repository.conversation(conv_id)['modele'] == 'fake'
    async def unavailable():
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(svc.ollama, 'models', unavailable)
    assert client.patch(path, json={'modele': 'other'}).status_code == 503


def test_model_change_busy_active_and_pending(command_client):
    client, svc, fake, conv_id, path, _ = command_client
    fake.block = True
    assert send(client, path, 'Attendre').status_code == 202
    client.portal.call(fake.started.wait)
    assert client.patch(path, json={'modele': 'fake'}).status_code == 409
    assert send(client, path, '/rgpd alice@example.fr').status_code == 422
    assert send(client, path, '/help').status_code == 202
    second = client.post('/api/conversations', json={'modele': 'fake'}).json()
    second_path = '/api/conversations/' + second['id']
    assert send(client, second_path, 'En file').status_code == 202
    assert client.patch(second_path, json={'modele': 'fake'}).status_code == 409
    assert client.post(second_path + '/stop').status_code == 200
    assert client.post(path + '/stop').status_code == 200
    assert client.patch(path, json={'modele': 'fake'}).status_code == 200


def test_model_change_rechecks_busy_after_listing(command_client, monkeypatch):
    client, svc, _, conv_id, path, _ = command_client
    async def models():
        svc.chat.pending.append({'conversation_id': conv_id})
        return [{'name': 'fake'}]
    monkeypatch.setattr(svc.ollama, 'models', models)
    try:
        assert client.patch(path, json={'modele': 'fake'}).status_code == 409
    finally:
        svc.chat.pending.clear()
