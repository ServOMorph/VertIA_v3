from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from vertia.app import create_app
from vertia.engines.base import MemoryNeeds
from vertia.engines.comfy_qwen import ComfyQwenEngine, build_graph
from vertia.resources.monitor import MemoryGuard, MemoryRefused
from vertia.tools.image import ImageTool, image_candidate
from vertia.tools.registry import ToolRegistry
from test_chat import FakeOllama, drain as drain_chat
from test_jobs import FakeMonitor, drain

REAL_HEALTH = ComfyQwenEngine.health


class FakeQwen:
    memory = MemoryNeeds(ram_mb=17000)

    def __init__(self):
        self.calls = []
        self.block = False

    async def start(self):
        pass

    async def health(self):
        return True

    async def free(self):
        pass

    async def stop(self):
        pass

    async def generate(self, params, progress):
        self.calls.append(params)
        progress(50)
        if self.block:
            await asyncio.Event().wait()
        return {'prompt_id': 'fake', 'images': [{'filename': 'test.png', 'subfolder': '', 'type': 'output'}]}

    async def preview(self, image):
        return b'fake-png', 'image/png'


class Planner(FakeOllama):
    output = {'tool': 'image_qwen', 'parameters': {'prompt': 'Un chat sur Mars'}}

    async def chat_stream(self, model, messages, num_predict):
        self.calls.append(messages)
        text = json.dumps(self.output, ensure_ascii=False)
        yield {'message': {'content': text[:10]}}
        yield {'message': {'content': text[10:]}}
        yield {'done': True}


def make_app(settings):
    fake, qwen = Planner(), FakeQwen()
    app = create_app(settings, {'ollama': fake, 'monitor': FakeMonitor(), 'engines': {'comfy': qwen}})
    return app, fake, qwen


def request_card(client, app, ephemeral=False):
    conv = client.post('/api/conversations', json={'modele': 'fake', 'ephemere': ephemeral}).json()
    path = '/api/conversations/' + conv['id']
    assert client.post(path + '/messages', json={'contenu': 'Dessine une image de chat sur Mars'}).status_code == 202
    client.portal.call(drain_chat, app.state.services.chat)
    return path, client.get(path).json()


@pytest.mark.parametrize('text,expected', [
    ('Bonjour', False), ('Explique la diffusion des images', False),
    ('Ne génère pas une image', False), ('Sans générer une image, explique le modèle', False),
    ('Génère une image de chat', True), ('Crée un logo bleu', True),
    ('Dessine un chat sur Mars', True), ('Draw a cat', True),
    ('Create a picture of the sea', True), ('Je voudrais une affiche vintage', True),
    ('Fais-moi une photo de montagne', True), ('Modifie cette image', True),
    ('Écris du code pour créer une image', True),
])
def test_intention_routing_locked_cases(text, expected):
    assert image_candidate(text) is expected


def test_card_edit_validate_once_preview_and_persistence(settings):
    app, planner, qwen = make_app(settings)
    with TestClient(app) as client:
        path, conv = request_card(client, app)
        card = conv['actions'][0]
        assert not qwen.calls
        assert conv['messages'][1]['statut'] == 'termine'
        assert 'image_qwen' in planner.calls[0][0]['content']
        assert len(client.get('/api/jobs').json()) == 1  # préparation LLM uniquement
        params = dict(card['parameters'], prompt='Une mer rouge', largeur=768)
        route = '/api/actions/' + card['id']
        assert client.patch(route, json={'parameters': dict(params, largeur=777)}).status_code == 422
        assert client.patch(route, json={'parameters': params}).status_code == 200
        assert client.post(route + '/valider', json={'parameters': params}).status_code == 202
        client.portal.call(drain, app.state.services.jobs)
        assert qwen.calls == [params]
        assert client.post(route + '/valider', json={'parameters': params}).status_code == 422
        assert client.post(route + '/annuler').status_code == 422
        card = client.get(path).json()['actions'][0]
        assert card['job']['status'] == 'termine' and card['result']['images']
        assert client.get(route + '/images/0').content == b'fake-png'
        assert client.get(route + '/images/-1').status_code == 404
        assert client.get(route + '/images/10').status_code == 404
        assert client.get('/api/outils').json()[0]['memory']['ram_mb'] == 17000
    reopened, _, _ = make_app(settings)
    with TestClient(reopened) as client:
        assert client.get(path).json()['actions'][0]['result']['images']


def test_invalid_or_discussion_decision_never_enqueues_image(settings):
    app, planner, qwen = make_app(settings)
    with TestClient(app) as client:
        for output in [
            {'tool': 'shell', 'parameters': {}}, {'tool': 'image_qwen', 'parameters': {'prompt': ' ', 'largeur': 9999}},
            {'tool': 'image_qwen', 'parameters': {'prompt': 'Edit', 'mode': 'edit', 'references': ['secret.png']}},
            {'response': 'Voici du code pour créer une image.'},
        ]:
            planner.output = output
            _, conv = request_card(client, app)
            assert conv['actions'] == []
            assert conv['messages'][1]['statut'] == ('termine' if 'response' in output else 'erreur')
        assert not qwen.calls
        assert all(j['engine'] == 'ollama' for j in client.get('/api/jobs').json())


def test_ephemeral_cards_remain_in_memory_and_cancel_is_final(settings):
    app, _, qwen = make_app(settings)
    with TestClient(app) as client:
        path, conv = request_card(client, app, True)
        card = conv['actions'][0]
        route = '/api/actions/' + card['id']
        assert client.post(route + '/annuler').status_code == 200
        assert client.post(route + '/valider', json={'parameters': card['parameters']}).status_code == 422
        _, conv2 = request_card(client, app, True)
        second = conv2['actions'][0]
        assert client.post('/api/actions/' + second['id'] + '/valider', json={'parameters': second['parameters']}).status_code == 202
        client.portal.call(drain, app.state.services.jobs)
        with app.state.services.db.session() as conn:
            assert conn.execute('SELECT count(*) FROM actions').fetchone()[0] == 0
            assert 'Un chat sur Mars' not in str([tuple(row) for row in conn.execute('SELECT * FROM jobs')])
        assert qwen.calls
        assert client.delete(path).status_code == 200
        assert card['id'] not in app.state.services.actions.ephemeral
    assert app.state.services.actions.ephemeral == {}


def test_pending_image_blocks_delete_and_retry_tracks_latest_job(settings):
    app, _, qwen = make_app(settings)
    qwen.block = True
    with TestClient(app) as client:
        path, conv = request_card(client, app)
        card = conv['actions'][0]
        validated = client.post('/api/actions/' + card['id'] + '/valider', json={'parameters': card['parameters']}).json()
        assert client.delete(path).status_code == 409
        assert client.post('/api/jobs/' + validated['job_id'] + '/annuler').status_code == 200
        retry = client.post('/api/jobs/' + validated['job_id'] + '/reprendre').json()
        assert retry
        current = client.get(path).json()['actions'][0]
        assert current['job_id'] != validated['job_id']
        assert client.delete(path).status_code == 409
        client.post('/api/jobs/' + current['job_id'] + '/annuler')


def test_tool_validation_registry_and_compact_schemas():
    registry = ToolRegistry({'comfy': FakeQwen()})
    tool = ImageTool(registry.engines['comfy'])
    registry.register(tool)
    with pytest.raises(ValueError):
        registry.register(tool)
    for params in [{'prompt': 'x', 'unknown': 1}, {'prompt': 'x', 'largeur': True},
                   {'prompt': 'x', 'seed': 2**53}, {'prompt': 'x', 'largeur': 1536, 'hauteur': 1536}]:
        with pytest.raises(ValueError):
            tool.validate(params)
    graph = build_graph(tool.validate({'prompt': 'Un chat'}))
    assert graph['9']['inputs']['positive'] == ['4', 0]
    assert graph['9']['inputs']['cfg'] == 1 and graph['9']['inputs']['steps'] == 25
    assert graph['5']['inputs']['batch_size'] == 1
    assert graph['12']['inputs']['images'] == ['11', 0]
    assert len(registry.schemas(['image_qwen'])) < 900


@pytest.mark.asyncio
async def test_memory_needs_checked_before_launch():
    monitor = FakeMonitor()
    monitor.latest['ram']['used_mb'] = 30000
    guard = MemoryGuard(monitor, 92, 90)
    with pytest.raises(MemoryRefused, match='17000'):
        await guard.check(MemoryNeeds(ram_mb=17000))
    with pytest.raises(MemoryRefused, match='VRAM'):
        await guard.check(MemoryNeeds(vram_mb=8000))


class ComfyApi:
    def __init__(self, completed=True):
        self.calls = []
        self.prompt_id = None
        self.completed = completed
        self.submitted = asyncio.Event()

    def handle(self, request):
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.url.path, body))
        if request.url.path == '/prompt':
            self.prompt_id = body['prompt_id']
            self.submitted.set()
            data = {'prompt_id': self.prompt_id}
        elif request.url.path.startswith('/history/'):
            data = {self.prompt_id: {'status': {'status_str': 'success'}, 'outputs': {'12': {'images': [{'filename': 'x.png', 'subfolder': '', 'type': 'output'}]}}}} if self.completed else {}
        elif request.url.path == '/system_stats':
            data = {'system': {}, 'devices': [{'type': 'cuda', 'torch_vram_total': 0}]}
        elif request.url.path == '/queue':
            data = {'queue_running': [], 'queue_pending': []}
        else:
            data = {}
        return httpx.Response(200, json=data)

    @asynccontextmanager
    async def websocket(self, url, **kwargs):
        assert 'clientId=' in url
        api = self
        class Socket:
            async def recv(self):
                if not api.completed:
                    await asyncio.Event().wait()
                return json.dumps({'type': 'progress', 'data': {'prompt_id': api.prompt_id, 'value': 5, 'max': 10}})
        yield Socket()


@pytest.mark.asyncio
async def test_comfy_graph_ws_history_and_cancel_are_scoped(tmp_path):
    api = ComfyApi()
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(api.handle))
    engine = ComfyQwenEngine(tmp_path, 8189, client=client, websocket=api.websocket)
    engine.health = REAL_HEALTH.__get__(engine)
    assert await engine.health()
    progress = []
    params = ImageTool(engine).validate({'prompt': 'chat'})
    result = await engine.generate(params, progress.append)
    assert result['images'][0]['filename'] == 'x.png' and progress == [50, 100]
    assert not any(path in {'/interrupt', '/queue'} for path, _ in api.calls)
    api.completed = False
    api.submitted.clear()
    task = asyncio.create_task(engine.generate(params, progress.append))
    await api.submitted.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ('/interrupt', {'prompt_id': api.prompt_id}) in api.calls
    assert ('/queue', {'delete': [api.prompt_id]}) in api.calls
    assert not any(body and body.get('clear') for _, body in api.calls)
    assert engine.prompt_id is None
    await engine.close()


@pytest.mark.asyncio
async def test_comfy_preview_rejects_paths_and_start_missing_install(tmp_path):
    api = ComfyApi()
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(api.handle))
    engine = ComfyQwenEngine(tmp_path, 8189, client=client, launcher=lambda *a, **k: pytest.fail('Aucun lancement attendu'))
    for image in [{'filename': '../x.png', 'type': 'output'}, {'filename': 'x.png', 'subfolder': '../private', 'type': 'output'}, {'filename': 'x.png', 'type': 'input'}]:
        with pytest.raises(ValueError):
            await engine.preview(image)
    with pytest.raises(RuntimeError, match='introuvable'):
        await engine.start()
    await engine.close()


@pytest.mark.asyncio
async def test_comfy_lazy_start_checks_patch_and_external_free_does_not_kill(tmp_path, monkeypatch):
    api = ComfyApi()
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(api.handle))
    launch = []
    process = SimpleNamespace(poll=lambda: None)
    engine = ComfyQwenEngine(tmp_path, 8189, client=client, launcher=lambda *a, **k: (launch.append((a, k)) or process))
    python = tmp_path / '.venv' / 'Scripts' / 'python.exe'
    python.parent.mkdir(parents=True)
    python.touch()
    (tmp_path / 'main.py').touch()
    checks = []
    monkeypatch.setattr(engine, 'check_patch', lambda: checks.append('checked'))
    engine.health = AsyncMock(side_effect=[False, True])
    await engine.start()
    assert checks == ['checked'] and len(launch) == 1
    assert launch[0][0][0] == [str(python), '-B', 'main.py', '--port', '8189', '--lowvram', '--reserve-vram', '1']
    assert launch[0][1]['cwd'] == tmp_path
    # Simule un serveur déjà présent, dont VertIA ne possède pas le processus.
    engine.process = None
    engine.health = REAL_HEALTH.__get__(engine)
    await engine.start()
    assert len(launch) == 1
    await engine.free()
    assert ('/free', {'unload_models': True, 'free_memory': True}) in api.calls
    assert engine.process is None
    await engine.close()


def test_patch_check_is_read_only_and_missing_patch_refuses_start(tmp_path, monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0 if len(calls) == 1 else 1)
    monkeypatch.setattr('vertia.engines.comfy_qwen.subprocess.run', run)
    # Aucun client réseau créé pour ce contrôle synchrone.
    engine = ComfyQwenEngine(tmp_path, 8189, client=object())
    engine.check_patch()
    with pytest.raises(RuntimeError, match='manuellement'):
        engine.check_patch()
    assert all('--reverse' in args and '--check' in args for args in calls)
    assert all('appliquer.bat' not in ' '.join(args) for args in calls)


@pytest.mark.asyncio
async def test_comfy_failed_cancellation_blocks_next_start(tmp_path):
    api = ComfyApi(completed=False)
    def fail_interrupt(request):
        if request.url.path == '/interrupt':
            return httpx.Response(503)
        return api.handle(request)
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(fail_interrupt))
    engine = ComfyQwenEngine(tmp_path, 8189, client=client, websocket=api.websocket)
    task = asyncio.create_task(engine.generate(ImageTool(engine).validate({'prompt': 'chat'}), lambda value: None))
    await api.submitted.wait()
    task.cancel()
    with pytest.raises(httpx.HTTPStatusError):
        await task
    assert engine.prompt_id
    with pytest.raises(RuntimeError, match='confirmer'):
        await engine.start()
    with pytest.raises(httpx.HTTPStatusError):
        await engine.free()
    await engine.close()


@pytest.mark.asyncio
async def test_lost_prompt_response_still_cancels_known_id(tmp_path):
    api = ComfyApi()
    def lost_response(request):
        response = api.handle(request)
        if request.url.path == '/prompt':
            raise httpx.ReadTimeout('Réponse perdue après soumission')
        return response
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(lost_response))
    engine = ComfyQwenEngine(tmp_path, 8189, client=client, websocket=api.websocket)
    with pytest.raises(httpx.ReadTimeout):
        await engine.generate(ImageTool(engine).validate({'prompt': 'chat'}), lambda value: None)
    assert ('/queue', {'delete': [api.prompt_id]}) in api.calls
    assert ('/interrupt', {'prompt_id': api.prompt_id}) in api.calls
    assert engine.prompt_id is None
    await engine.close()


@pytest.mark.asyncio
async def test_stop_targets_only_owned_process_tree(tmp_path, monkeypatch):
    trace = []
    def process(pid):
        trace.append(('lookup', pid))
        child = SimpleNamespace(terminate=lambda: trace.append(('terminate', 42)))
        parent = SimpleNamespace(children=lambda recursive: [child], terminate=lambda: trace.append(('terminate', pid)))
        return parent
    monkeypatch.setattr('vertia.engines.process.psutil.Process', process)
    monkeypatch.setattr('vertia.engines.process.psutil.wait_procs', lambda items, timeout: (items, []))
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(ComfyApi().handle))
    engine = ComfyQwenEngine(tmp_path, 8189, client=client)
    engine.process = SimpleNamespace(pid=41, poll=lambda: None)
    await engine.stop()
    assert trace == [('lookup', 41), ('terminate', 41), ('terminate', 42)]
    assert engine.process is None
    await engine.close()


@pytest.mark.asyncio
async def test_preview_can_read_existing_result_without_server(tmp_path):
    async def offline(request):
        raise httpx.ConnectError('Offline')
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(offline))
    engine = ComfyQwenEngine(tmp_path, 8189, client=client)
    folder = tmp_path / 'output' / 'album'
    folder.mkdir(parents=True)
    (folder / 'image.png').write_bytes(b'png-local')
    data, media_type = await engine.preview({'filename': 'image.png', 'subfolder': 'album', 'type': 'output'})
    assert data == b'png-local' and media_type == 'image/png'
    await engine.close()


def test_schema_selection_uses_module_routing(settings):
    app, _, _ = make_app(settings)
    svc = app.state.services
    class OtherTool:
        name = 'autre'
        description = 'Test de module'
        parameters = {'prompt': 'texte'}
        engine = 'comfy'
        matches = staticmethod(lambda text: text == 'autre demande')
    svc.tools.register(OtherTool())
    assert svc.actions.instruction('Bonjour') == ''
    instruction = svc.actions.instruction('autre demande')
    assert 'autre' in instruction and 'image_qwen' not in instruction
    assert '"name":"image_qwen"' in svc.actions.instruction('Crée une image de chat')
