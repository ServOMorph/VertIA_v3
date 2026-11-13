from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from vertia.app import create_app
from vertia.engines.comfy_qwen import ComfyQwenEngine
from vertia.engines.video_wan import WanVideoEngine, build_video_graph
from vertia.tools.video import VideoTool, video_candidate
from test_chat import drain as drain_chat
from test_jobs import FakeMonitor, drain
from test_tools import ComfyApi, FakeQwen, Planner


@pytest.mark.parametrize('text,expected', [
    ('Bonjour', False), ('Explique la vidéo locale', False),
    ('Ne génère pas de vidéo', False), ('Sans générer une vidéo, explique', False),
    ('Do not create a video', False), ('Crée une vidéo de mer', True),
    ('Génère un clip de forêt', True), ('Anime cette image', True),
    ('Animate this picture', True), ('Je voudrais une animation', True),
    ('Dessine une image', False), ('Compose une chanson', False),
])
def test_video_routing(text, expected):
    assert video_candidate(text) is expected


@pytest.mark.parametrize('invalid', [
    {'prompt': ' '}, {'largeur': 641}, {'hauteur': True}, {'largeur': 960, 'hauteur': 960},
    {'images': 48}, {'images': 77}, {'images': 13}, {'etapes': 31}, {'seed': 2**53},
    {'mode': 'i2v'}, {'references': ['unknown']}, {'references': ['x', 'y']},
    {'audio': True}, {'fps': 30}, {'duree': 10},
])
def test_video_invalid_parameters(invalid):
    with pytest.raises(ValueError):
        VideoTool(object()).validate({'prompt': 'La mer', **invalid})


def test_video_native_graph_text_and_image():
    params = VideoTool(object()).validate({'prompt': 'La mer'})
    graph = build_video_graph(params)
    assert graph['1']['inputs']['unet_name'] == 'Wan2.2-TI2V-5B-Q4_K_M.gguf'
    assert graph['2']['inputs']['type'] == 'wan'
    assert graph['6']['inputs'] == dict(vae=['3', 0], width=640, height=384, length=49, batch_size=1)
    assert graph['7']['inputs'] == dict(model=['1', 0], shift=8)
    assert graph['8']['inputs']['latent_image'] == ['6', 0]
    assert graph['8']['inputs']['model'] == ['7', 0]
    assert graph['8']['inputs']['sampler_name'] == 'uni_pc'
    assert graph['9']['class_type'] == 'VAEDecodeTiled'
    assert graph['10']['inputs'] == {'images': ['9', 0], 'fps': 24}
    # L’API ComfyUI reçoit des clés aplaties ; elle construit les dictionnaires à l’exécution.
    assert graph['11']['inputs']['format'] == 'mp4'
    assert graph['11']['inputs']['format.codec'] == 'h264'
    image = build_video_graph(dict(params, mode='i2v', references=['uploaded.png']))
    assert image['6']['inputs']['start_image'] == ['20', 0]
    assert image['20']['inputs']['image'] == 'uploaded.png'
    assert '20' not in graph


class FakeVideoComfy(FakeQwen):
    def __init__(self):
        super().__init__()
        self.upload_image = AsyncMock(return_value='uploaded.png')

    async def generate_graph(self, graph, progress, output_node, result_key):
        assert output_node == '11' and result_key == 'videos'
        self.calls.append(graph)
        progress(100)
        return {'prompt_id': 'fake', 'videos': [{'filename': 'result.mp4', 'subfolder': '', 'type': 'output'}]}

    async def preview(self, media, **kwargs):
        return (b'fake-mp4', 'video/mp4') if kwargs else (b'fake-png', 'image/png')


def video_app(settings):
    planner, comfy = Planner(), FakeVideoComfy()
    planner.output = {'tool': 'video_wan', 'parameters': {'prompt': 'La mer en mouvement'}}
    app = create_app(settings, {'ollama': planner, 'monitor': FakeMonitor(), 'engines': {'comfy': comfy}})
    assert app.state.services.tools.get('video_wan').adapter.comfy is comfy
    assert set(app.state.services.arbiter.engines) == {'ollama', 'comfy', 'ace'}
    return app, planner, comfy


def video_card(client, app, ephemeral=False):
    conv = client.post('/api/conversations', json={'modele': 'fake', 'ephemere': ephemeral}).json()
    path = '/api/conversations/' + conv['id']
    assert client.post(path + '/messages', json={'contenu': 'Crée une vidéo de la mer'}).status_code == 202
    client.portal.call(drain_chat, app.state.services.chat)
    return path, client.get(path).json()['actions'][0]


@pytest.mark.parametrize('ephemeral', [False, True])
def test_video_card_confirmation_copy_preview_and_restart(settings, ephemeral):
    app, _, comfy = video_app(settings)
    with TestClient(app) as client:
        path, card = video_card(client, app, ephemeral)
        assert not comfy.calls and not comfy.upload_image.called
        route = '/api/actions/' + card['id']
        invalid = dict(card['parameters'], images=50)
        assert client.post(route + '/valider', json={'parameters': invalid}).status_code == 422
        assert not comfy.calls
        params = dict(card['parameters'], images=53, largeur=768)
        assert client.patch(route, json={'parameters': params}).status_code == 200
        assert client.post(route + '/valider', json={'parameters': params}).status_code == 202
        client.portal.call(drain, app.state.services.jobs)
        action = client.get(path).json()['actions'][0]
        assert action['job']['status'] == 'termine'
        assert action['job']['engine'] == 'comfy'
        assert len(comfy.calls) == 1 and comfy.calls[0]['6']['inputs']['length'] == 53
        file = client.get(path + '/fichiers').json()[0]
        assert file['type'] == 'video' and file['mime'] == 'video/mp4'
        assert client.get(route + '/medias/0').content == b'fake-mp4'
        content = '/api/fichiers/' + file['id'] + '/contenu'
        response = client.get(content + '?telecharger=true')
        assert response.content == b'fake-mp4' and '.mp4' in response.headers['content-disposition']
        response = client.get(content, headers={'Range': 'bytes=0-3'})
        assert response.status_code == (200 if ephemeral else 206)
        assert response.content == (b'fake-mp4' if ephemeral else b'fake')
        assert client.post(route + '/valider', json={'parameters': params}).status_code == 422
        with app.state.services.db.session() as conn:
            if ephemeral:
                assert conn.execute('SELECT count(*) FROM fichiers').fetchone()[0] == 0
                assert not list(settings.outputs_dir.iterdir())
    reopened, _, engine = video_app(settings)
    engine.preview = AsyncMock(side_effect=AssertionError('Aucun moteur pour une copie locale'))
    with TestClient(reopened) as client:
        assert client.get(route + '/medias/0').status_code == (404 if ephemeral else 200)
        if not ephemeral:
            assert client.get(content).content == b'fake-mp4'


def test_video_reference_upload_only_after_confirm_and_scoped(settings):
    app, planner, comfy = video_app(settings)
    svc = app.state.services
    with TestClient(app) as client:
        path, card = video_card(client, app)
        conv_id = card['conversation_id']
        source = dict(card, tool='image_qwen', parameters={'prompt': 'Image source'})
        job_id = client.get('/api/jobs').json()[0]['id']
        file_id = svc.files.save(source, job_id, [(b'image', 'image/png')])[0]
        other = client.post('/api/conversations', json={'modele': 'fake'}).json()
        foreign = dict(source, conversation_id=other['id'])
        foreign_id = svc.files.save(foreign, job_id, [(b'foreign', 'image/png')])[0]
        route = '/api/actions/' + card['id']
        params = dict(card['parameters'], mode='i2v', references=[foreign_id])
        assert client.patch(route, json={'parameters': params}).status_code == 422
        params['references'] = [file_id]
        assert client.patch(route, json={'parameters': params}).status_code == 200
        assert not comfy.upload_image.called
        assert client.post(route + '/valider', json={'parameters': params}).status_code == 202
        client.portal.call(drain, svc.jobs)
        comfy.upload_image.assert_awaited_once_with(b'image', 'image/png')
        assert comfy.calls[0]['20']['inputs']['image'] == 'uploaded.png'
        assert client.get(path).json()['actions'][0]['parameters']['references'] == [file_id]


@pytest.mark.asyncio
async def test_wan_history_progress_and_scoped_cancellation(tmp_path):
    api = ComfyApi()
    def handle(request):
        if request.url.path.startswith('/history/') and api.completed:
            return httpx.Response(200, json={api.prompt_id: {'outputs': {'11': {'images': [
                {'filename': 'video.mp4', 'subfolder': '', 'type': 'output'}]}}}})
        return api.handle(request)
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(handle))
    shared = ComfyQwenEngine(tmp_path, 8189, client=client, websocket=api.websocket)
    engine = WanVideoEngine(shared)
    progress = []
    params = VideoTool(engine).validate({'prompt': 'La mer'})
    result = await engine.generate(params, progress.append)
    assert result['videos'][0]['filename'] == 'video.mp4' and progress == [50, 100]
    submitted = next(body for path, body in api.calls if path == '/prompt')
    assert submitted['prompt']['11']['class_type'] == 'SaveVideo'
    api.completed = False
    api.submitted.clear()
    task = asyncio.create_task(engine.generate(params, progress.append))
    await api.submitted.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ('/interrupt', {'prompt_id': api.prompt_id}) in api.calls
    assert ('/queue', {'delete': [api.prompt_id]}) in api.calls
    assert shared.prompt_id is None
    await shared.close()


@pytest.mark.asyncio
async def test_video_preview_formats_limit_and_offline(tmp_path):
    mode = ['online']
    def handle(request):
        if mode[0] == 'offline':
            raise httpx.ConnectError('Offline')
        return httpx.Response(200, content=b'video', headers={'content-type': mode[0] if '/' in mode[0] else 'video/mp4'})
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(handle))
    shared = ComfyQwenEngine(tmp_path, 8189, client=client)
    video = WanVideoEngine(shared)
    ref = {'filename': 'test.mp4', 'subfolder': '', 'type': 'output'}
    assert await video.preview(ref) == (b'video', 'video/mp4')
    with pytest.raises(ValueError, match='volumineux'):
        await shared.preview(ref, formats={'.mp4': 'video/mp4'}, max_bytes=4)
    mode[0] = 'text/html'
    with pytest.raises(ValueError, match='Format'):
        await video.preview(ref)
    mode[0] = 'offline'
    folder = tmp_path / 'output'
    folder.mkdir()
    (folder / 'test.mp4').write_bytes(b'local')
    assert await video.preview(ref) == (b'local', 'video/mp4')
    for bad in [dict(ref, filename='../test.mp4'), dict(ref, subfolder='../'), dict(ref, type='input')]:
        with pytest.raises(ValueError):
            await video.preview(bad)
    await shared.close()
