from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from vertia.engines.comfy_qwen import ComfyQwenEngine, build_graph
from vertia.tools.image import ImageTool
from test_chat import drain as drain_chat
from test_jobs import drain
from test_tools import make_app, request_card


def generate(client, app, ephemeral=False):
    path, conv = request_card(client, app, ephemeral)
    card = conv['actions'][0]
    validated = client.post('/api/actions/' + card['id'] + '/valider', json={'parameters': card['parameters']}).json()
    client.portal.call(drain, app.state.services.jobs)
    files = client.get(path + '/fichiers').json()
    assert len(files) == 1
    return path, validated, files[0]


def test_generated_file_metadata_download_range_restart_without_engine(settings):
    app, _, _ = make_app(settings)
    with TestClient(app) as client:
        path, action, file = generate(client, app)
        assert file['type'] == 'image' and file['mime'] == 'image/png'
        assert file['job_id'] == action['job_id'] and file['action_id'] == action['id']
        assert file['parameters'] == action['parameters'] and file['prompt'] == 'Un chat sur Mars'
        stored = settings.outputs_dir / file['conversation_id'] / file['name']
        assert stored.read_bytes() == b'fake-png'
        result = client.get('/api/actions/' + action['id'] + '/images/0')
        assert result.content == b'fake-png'
    reopened, _, qwen = make_app(settings)
    qwen.preview = AsyncMock(side_effect=AssertionError('Aucun accès moteur pour un fichier local'))
    with TestClient(reopened) as client:
        assert client.get(path + '/fichiers').json()[0]['id'] == file['id']
        route = '/api/fichiers/' + file['id'] + '/contenu'
        response = client.get(route + '?telecharger=true')
        assert response.content == b'fake-png'
        assert response.headers['content-disposition'].startswith('attachment;')
        assert response.headers['x-content-type-options'] == 'nosniff'
        partial = client.get(route, headers={'Range': 'bytes=0-3'})
        assert partial.status_code == 206 and partial.content == b'fake'
        assert client.get('/api/actions/' + action['id'] + '/images/0').content == b'fake-png'


def test_ephemeral_file_never_writes_disk_or_catalog_and_clears(settings):
    app, _, _ = make_app(settings)
    with TestClient(app) as client:
        path, _, file = generate(client, app, True)
        assert list(settings.outputs_dir.iterdir()) == []
        with app.state.services.db.session() as conn:
            assert conn.execute('SELECT COUNT(*) FROM fichiers').fetchone()[0] == 0
        assert client.get('/api/fichiers/' + file['id'] + '/contenu').content == b'fake-png'
        assert client.post('/api/fichiers/' + file['id'] + '/dossier').status_code == 422
        assert client.delete(path).status_code == 200
        assert client.get('/api/fichiers/' + file['id'] + '/contenu').status_code == 404
        generate(client, app, True)
    assert app.state.services.files.ephemeral == {}


def test_missing_local_result_returns_404_from_both_preview_routes(settings):
    app, _, qwen = make_app(settings)
    with TestClient(app) as client:
        _, action, file = generate(client, app)
        stored = settings.outputs_dir / file['conversation_id'] / file['name']
        stored.unlink()
        qwen.preview = AsyncMock(side_effect=AssertionError('Un fichier local absent ne relance pas le moteur'))
        for kind in ['images', 'medias']:
            response = client.get(f'/api/actions/{action["id"]}/{kind}/0')
            assert response.status_code == 404
            assert response.json() == {'detail': 'Média introuvable.'}
        assert client.get('/api/fichiers/' + file['id'] + '/contenu').status_code == 404


def test_attachment_is_short_reference_and_other_conversation_is_rejected(settings):
    app, planner, _ = make_app(settings)
    with TestClient(app) as client:
        path, _, file = generate(client, app)
        other = client.post('/api/conversations', json={'modele': 'fake'}).json()
        body = {'contenu': 'Décris le fichier', 'fichiers': [file['id']]}
        assert client.post('/api/conversations/' + other['id'] + '/messages', json=body).status_code == 422
        assert client.post(path + '/messages', json=dict(body, fichiers=['inconnu'])).status_code == 404
        assert client.post(path + '/messages', json=dict(body, fichiers=[file['id']] * 2)).status_code == 422
        planner.output = {'response': 'Je dispose uniquement de la référence, sans analyse visuelle.'}
        assert client.post(path + '/messages', json=body).status_code == 202
        client.portal.call(drain_chat, app.state.services.chat)
        content = client.get(path).json()['messages'][-2]['contenu']
        assert file['id'] in content and file['prompt'] in content
        assert 'fake-png' not in json.dumps(planner.calls)
        assert len(content) < 300


def test_reuse_image_for_edit_uploads_only_in_confirmed_job(settings):
    app, planner, qwen = make_app(settings)
    qwen.upload_image = AsyncMock(return_value='uploaded.png')
    with TestClient(app) as client:
        path, _, file = generate(client, app)
        planner.output = {'tool': 'image_qwen', 'parameters': {'prompt': 'Ajoute des étoiles', 'mode': 'edit', 'references': [file['id']]}}
        assert client.post(path + '/messages', json={'contenu': 'Modifie cette image', 'fichiers': [file['id']]}).status_code == 202
        client.portal.call(drain_chat, app.state.services.chat)
        card = client.get(path).json()['actions'][-1]
        assert card['parameters']['references'] == [file['id']]
        assert len(qwen.calls) == 1 and qwen.upload_image.await_count == 0
        route = '/api/actions/' + card['id'] + '/valider'
        assert client.post(route, json={'parameters': card['parameters']}).status_code == 202
        client.portal.call(drain, app.state.services.jobs)
        qwen.upload_image.assert_awaited_once_with(b'fake-png', 'image/png')
        params = qwen.calls[-1]
        assert params['mode'] == 'edit' and params['references'] == ['uploaded.png']
        graph = build_graph(params)
        assert graph['20']['inputs']['image'] == 'uploaded.png'
        assert graph['4']['inputs']['images.image_1'] == ['20', 0]
        assert graph['9']['inputs']['latent_image'] == ['4', 2] and '5' not in graph
        files = client.get(path + '/fichiers').json()
        assert len(files) == 2 and files[-1]['parameters']['references'] == [file['id']]


def test_foreign_reference_cannot_be_saved_in_action(settings):
    app, _, _ = make_app(settings)
    with TestClient(app) as client:
        _, _, file = generate(client, app)
        _, conv = request_card(client, app)
        card = conv['actions'][0]
        params = dict(card['parameters'], mode='edit', references=[file['id']])
        assert client.patch('/api/actions/' + card['id'], json={'parameters': params}).status_code == 422


@pytest.mark.parametrize('mime,kind', [('audio/mpeg', 'audio'), ('video/mp4', 'video')])
def test_store_accepts_future_media_and_delete_cleans_only_catalogued_files(settings, mime, kind):
    app, _, _ = make_app(settings)
    with TestClient(app) as client:
        path, _, file = generate(client, app)
        svc = app.state.services
        action = svc.actions.get(file['action_id'])
        ids = svc.files.save(action, file['job_id'], [(b'fake-media', mime)])
        assert svc.files.get(ids[0])['type'] == kind
        assert client.get('/api/fichiers/' + ids[0] + '/contenu').headers['content-type'] == mime
        folder = svc.files.directory(file['conversation_id'])
        # Un fichier inconnu du catalogue ne doit jamais être supprimé.
        extra = folder / 'conserver.txt'
        extra.write_text('indépendant', encoding='utf-8')
        assert client.delete(path).status_code == 200
        assert extra.read_text(encoding='utf-8') == 'indépendant'
        assert [p.name for p in folder.iterdir()] == ['conserver.txt']
        assert client.get('/api/fichiers/' + file['id'] + '/contenu').status_code == 404


def test_invalid_artifacts_and_paths_do_not_expose_files(settings, monkeypatch):
    app, _, _ = make_app(settings)
    with TestClient(app) as client:
        _, _, file = generate(client, app)
        svc = app.state.services
        action = svc.actions.get(file['action_id'])
        with pytest.raises(ValueError):
            svc.files.save(action, file['job_id'], [(b'ok', 'image/png'), (b'html', 'text/html')])
        assert len(svc.files.list(file['conversation_id'])) == 1
        with pytest.raises(ValueError):
            svc.files.directory('../private')
        opened = []
        monkeypatch.setattr('vertia.web.files.os.startfile', opened.append, raising=False)
        assert client.post('/api/fichiers/' + file['id'] + '/dossier').status_code == 200
        assert opened == [str(svc.files.directory(file['conversation_id']))]
        with svc.db.session() as conn:
            conn.execute('UPDATE fichiers SET name=? WHERE id=?', ('../private.png', file['id']))
        assert client.get('/api/fichiers/' + file['id'] + '/contenu').status_code == 404
        assert client.post('/api/fichiers/' + file['id'] + '/dossier').status_code == 422


@pytest.mark.asyncio
async def test_comfy_reference_upload_is_multipart_and_validated(tmp_path):
    seen = []
    def handle(request):
        seen.append(request)
        assert request.url.path == '/upload/image'
        content = request.content.decode()
        name = content.split('filename="')[1].split('"')[0]
        return httpx.Response(200, json={'name': name, 'subfolder': '', 'type': 'input'})
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(handle))
    engine = ComfyQwenEngine(tmp_path, 8189, client=client)
    name = await engine.upload_image(b'fake-image', 'image/png')
    assert name.startswith('VertIA_') and name.endswith('.png')
    assert 'multipart/form-data' in seen[0].headers['content-type']
    with pytest.raises(RuntimeError):
        await engine.upload_image(b'x', 'text/html')
    await engine.close()


def test_image_edit_requires_real_images_and_rejects_mask():
    tool = ImageTool(object())
    for params in [{'prompt': 'x', 'mode': 'edit'}, {'prompt': 'x', 'references': ['x']}, {'prompt': 'x', 'mode': 'inpaint'}]:
        with pytest.raises(ValueError):
            tool.validate(params)


def test_failed_copy_keeps_engine_result_and_reports_storage_error(settings, monkeypatch):
    app, _, _ = make_app(settings)
    with TestClient(app) as client:
        path, conv = request_card(client, app)
        card = conv['actions'][0]
        def full_disk(*args):
            raise OSError('disque plein simulé')
        monkeypatch.setattr(app.state.services.files, 'save', full_disk)
        client.post('/api/actions/' + card['id'] + '/valider', json={'parameters': card['parameters']})
        client.portal.call(drain, app.state.services.jobs)
        card = client.get(path).json()['actions'][0]
        assert card['job']['status'] == 'erreur' and 'copie locale impossible' in card['job']['error']
        assert card['result']['images']
        assert client.get('/api/actions/' + card['id'] + '/images/0').content == b'fake-png'


def test_partial_disk_write_rolls_back_catalog_and_new_files(settings, monkeypatch):
    app, _, _ = make_app(settings)
    with TestClient(app) as client:
        _, _, file = generate(client, app)
        svc = app.state.services
        folder = svc.files.directory(file['conversation_id'])
        original = Path.open
        count = 0
        def open_file(path, mode='r', *args, **kwargs):
            nonlocal count
            if path.parent == folder and mode == 'xb':
                count += 1
                if count == 2:
                    raise OSError('disque plein simulé')
            return original(path, mode, *args, **kwargs)
        monkeypatch.setattr(Path, 'open', open_file)
        with pytest.raises(OSError):
            svc.files.save(svc.actions.get(file['action_id']), file['job_id'], [(b'a', 'image/png'), (b'b', 'image/png')])
        assert [p.name for p in folder.iterdir()] == [file['name']]
        assert len(svc.files.list(file['conversation_id'])) == 1
