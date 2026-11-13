from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from vertia.app import create_app
from vertia.engines.acestep import AceStepEngine
from vertia.engines.base import EngineError
from vertia.tools.music import MusicTool, music_candidate, syllables
from test_chat import drain as drain_chat
from test_jobs import FakeMonitor, drain
from test_tools import Planner, FakeQwen

REAL_HEALTH = AceStepEngine.health
VOCAL = dict(prompt='Une chanson douce sur la mer', titre='Le rivage',
             caption='folk pop, warm female vocals, acoustic guitar, brushed drums, intimate production, hopeful',
             paroles='[verse]\nLa mer nous porte au loin\nLe vent revient demain\n\n[chorus]\nNous marchons sur le sable\nLa nuit devient plus calme')
INSTRUMENTAL = dict(prompt='Un instrumental calme', titre='Horizon', instrumental=True,
                    caption='ambient, instrumental, soft piano, gentle percussion, warm production, peaceful')


@pytest.mark.parametrize('text,expected', [
    ('Bonjour', False), ('Explique la musique', False), ('Ne génère pas de musique', False),
    ('Sans générer une chanson, explique', False), ('Compose une chanson sur la mer', True),
    ('Crée un instrumental calme', True), ('Je voudrais une musique jazz', True),
    ('Generate a song about the sea', True), ('Do not create music', False),
])
def test_music_intentions(text, expected):
    assert music_candidate(text) is expected


def test_lyrics_and_caption_validation():
    tool = MusicTool(None)
    assert tool.validate(VOCAL)['duree'] == 60
    assert tool.validate(INSTRUMENTAL)['paroles'] == ''
    assert syllables('La mer nous porte au loin') <= 12
    invalid = [
        dict(VOCAL, paroles='Texte sans balise'),
        dict(VOCAL, paroles='[verse] La mer\n[chorus]\nUn vent'),
        dict(VOCAL, paroles='[verse]\nLa mer\n[chorus]'),
        dict(VOCAL, paroles='[unknown]\nLa mer\n[chorus]\nLe vent'),
        dict(VOCAL, paroles=VOCAL['paroles'] + '\n[chorus]\nUn autre refrain'),
        dict(VOCAL, paroles='[verse]\n' + 'la ' * 14 + '\n[chorus]\nLa mer'),
        dict(VOCAL, paroles='[verse]\n' + 'La mer\n' * 8 + '[chorus]\n' + 'Le vent\n' * 8, duree=20),
        dict(VOCAL, caption='pop, vocals'), dict(VOCAL, caption=VOCAL['caption'] + ', 120 bpm'),
        dict(VOCAL, caption=VOCAL['caption'] + ', C major'),
        dict(VOCAL, instrumental=True), dict(INSTRUMENTAL, paroles='Des paroles'),
        dict(VOCAL, caption=INSTRUMENTAL['caption']), dict(VOCAL, duree=136),
        dict(VOCAL, bpm='120'), dict(VOCAL, langue='xx'), dict(VOCAL, references=['audio-id']),
        dict(VOCAL, titre=' '), dict(VOCAL, seed=-1),
    ]
    for params in invalid:
        with pytest.raises(ValueError):
            tool.validate(params)


class FakeAce(FakeQwen):
    async def generate(self, params, progress):
        self.calls.append(params)
        progress(50)
        return {'task_id': 'music-task', 'audios': ['result.mp3']}

    async def preview(self, audio):
        return b'ID3-simulated-mp3', 'audio/mpeg'


@pytest.mark.parametrize('ephemeral', [False, True])
def test_chat_music_card_confirmation_gallery_privacy(settings, ephemeral):
    planner, ace = Planner(), FakeAce()
    planner.output = {'tool': 'musique_ace', 'parameters': VOCAL}
    app = create_app(settings, {'ollama': planner, 'monitor': FakeMonitor(),
                                'engines': {'ace': ace, 'comfy': FakeQwen()}})
    with TestClient(app) as client:
        conv = client.post('/api/conversations', json={'modele': 'fake', 'ephemere': ephemeral}).json()
        route = '/api/conversations/' + conv['id']
        assert client.post(route + '/messages', json={'contenu': 'Compose une chanson sur la mer'}).status_code == 202
        client.portal.call(drain_chat, app.state.services.chat)
        card = client.get(route).json()['actions'][0]
        assert ace.calls == []
        system = planner.calls[0][0]['content']
        assert 'musique_ace' in system and 'image_qwen' not in system
        assert '[verse]' in system and '2,5' in system
        path = '/api/actions/' + card['id']
        assert client.patch(path, json={'parameters': dict(card['parameters'], duree=999)}).status_code == 422
        invalid = client.patch(path, json={'parameters': dict(card['parameters'], paroles='secret sans balise')})
        assert invalid.status_code == 422 and 'balise' in invalid.json()['detail']
        assert 'secret' not in invalid.text
        params = dict(card['parameters'], titre='Un autre rivage', duree=90)
        assert client.post(path + '/valider', json={'parameters': params}).status_code == 202
        client.portal.call(drain, app.state.services.jobs)
        assert client.post(path + '/valider', json={'parameters': params}).status_code == 422
        assert ace.calls == [params]
        files = client.get(route + '/fichiers').json()
        assert len(files) == 1 and files[0]['type'] == 'audio'
        assert files[0]['parameters'] == params
        response = client.get('/api/fichiers/' + files[0]['id'] + '/contenu?telecharger=true')
        assert response.content == b'ID3-simulated-mp3'
        assert response.headers['content-type'] == 'audio/mpeg'
        assert client.get(path + '/medias/0').content == b'ID3-simulated-mp3'
        stored = settings.outputs_dir / conv['id'] / files[0]['name']
        assert stored.exists() is not ephemeral
        job = app.state.services.jobs.get(client.get(route).json()['actions'][0]['job_id'])
        assert job['status'] == 'termine' and job['engine'] == 'ace'
        assert job['payload'] == ({} if ephemeral else {'action_id': card['id']})
        if ephemeral:
            with app.state.services.db.session() as conn:
                assert conn.execute('SELECT count(*) FROM actions').fetchone()[0] == 0
                assert conn.execute('SELECT count(*) FROM fichiers').fetchone()[0] == 0
        else:
            assert client.get('/api/fichiers/' + files[0]['id'] + '/contenu', headers={'Range': 'bytes=0-2'}).content == b'ID3'
    assert not app.state.services.files.ephemeral


class AceApi:
    def __init__(self):
        self.calls, self.polls = [], 0
        self.status = 1
        self.submission_error = False
        self.audio_mime = 'audio/mpeg'

    def handle(self, request):
        payload = json.loads(request.content) if request.content else None
        self.calls.append((request.url.path, payload))
        if request.url.path == '/health':
            return httpx.Response(200, json={'data': {'status': 'ok', 'service': 'ACE-Step API'}})
        if request.url.path == '/release_task':
            if self.submission_error:
                raise httpx.ReadTimeout('Soumission reçue, réponse perdue')
            return httpx.Response(200, json={'data': {'task_id': 't1'}})
        if request.url.path == '/query_result':
            self.polls += 1
            return httpx.Response(200, json={'data': [{'task_id': 't1', 'status': self.status,
                                  'result': json.dumps([{'file': 'C:/ace/temp/song.mp3'}])}]})
        if request.url.path == '/v1/audio':
            assert request.url.params['path'] == 'C:/ace/temp/song.mp3'
            return httpx.Response(200, content=b'ID3-mp3', headers={'content-type': self.audio_mime})
        raise AssertionError(request.url)


def engine_for(tmp_path, api):
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(api.handle))
    return AceStepEngine(tmp_path, 8001, client=client)


@pytest.mark.asyncio
async def test_adapter_payload_result_and_mp3(tmp_path):
    api = AceApi()
    engine = engine_for(tmp_path, api)
    engine.process = SimpleNamespace(poll=lambda: None)
    engine.stop = AsyncMock()
    progress = []
    for params in (VOCAL, INSTRUMENTAL):
        validated = MusicTool(engine).validate(params)
        result = await engine.generate(validated, progress.append)
        assert result == {'task_id': 't1', 'audios': ['C:/ace/temp/song.mp3']}
        assert await engine.preview(result['audios'][0]) == (b'ID3-mp3', 'audio/mpeg')
        payload = [body for path, body in api.calls if path == '/release_task'][-1]
        assert payload['prompt'] == params['caption']
        assert payload['lyrics'] == params.get('paroles', '')
        assert payload['inference_steps'] == 8 and payload['batch_size'] == 1
        assert payload['audio_format'] == 'mp3' and payload['thinking'] is False
        assert payload['use_random_seed'] is False and payload['seed'] == 0
        assert payload['vocal_language'] == ('unknown' if params.get('instrumental') else 'fr')
    assert progress == [5, 100, 5, 100]
    engine.stop.assert_not_awaited()
    api.audio_mime = 'text/html'
    with pytest.raises(ValueError):
        await engine.preview('C:/ace/temp/song.mp3')
    await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['rejected', 'submission', 'cancel'])
async def test_generation_errors_stop_owned_engine(tmp_path, failure):
    api = AceApi()
    engine = engine_for(tmp_path, api)
    engine.process = SimpleNamespace(poll=lambda: None)
    engine.stop = AsyncMock()
    params = MusicTool(engine).validate(VOCAL)
    if failure == 'rejected':
        api.status = 2
    elif failure == 'submission':
        api.submission_error = True
    else:
        api.status = 0
    if failure == 'cancel':
        task = asyncio.create_task(engine.generate(params, lambda value: None))
        for _ in range(20):
            if api.polls:
                break
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(EngineError):
            await engine.generate(params, lambda value: None)
    engine.stop.assert_awaited_once()
    await engine.client.aclose()


@pytest.mark.asyncio
async def test_lazy_launch_and_external_instance_refused(tmp_path, monkeypatch):
    api = AceApi()
    engine = engine_for(tmp_path, api)
    engine.health = REAL_HEALTH.__get__(engine)
    assert await engine.health()
    with pytest.raises(EngineError, match='hors de VertIA'):
        await engine.start()
    with pytest.raises(EngineError, match='externe'):
        await engine.free()
    engine.health = AsyncMock(return_value=False)
    with pytest.raises(EngineError, match='introuvable'):
        await engine.start()
    python = tmp_path / '.venv' / 'Scripts' / 'python.exe'
    python.parent.mkdir(parents=True)
    python.touch()
    (tmp_path / 'acestep').mkdir()
    (tmp_path / 'acestep' / 'api_server.py').touch()
    launches = []
    def launch(args, **kwargs):
        launches.append((args, kwargs))
        return SimpleNamespace(poll=lambda: None, pid=123)
    engine.launcher = launch
    engine.health = AsyncMock(side_effect=[False, True])
    await engine.start()
    args, kwargs = launches[0]
    assert args == [str(python), '-B', 'acestep/api_server.py', '--host', '127.0.0.1', '--port', '8001']
    assert kwargs['cwd'] == tmp_path
    assert kwargs['env']['ACESTEP_INIT_LLM'] == 'false'
    assert kwargs['env']['ACESTEP_OFFLOAD_TO_CPU'] == 'true'
    assert kwargs['env']['ACESTEP_LM_BACKEND'] == 'pt'
    assert kwargs['env']['ACESTEP_CONFIG_PATH'] == 'acestep-v15-turbo'
    trace = []
    child = SimpleNamespace(terminate=lambda: trace.append('child'))
    parent = SimpleNamespace(children=lambda recursive: [child], terminate=lambda: trace.append('parent'))
    monkeypatch.setattr('vertia.engines.process.psutil.Process', lambda pid: parent if pid == 123 else None)
    monkeypatch.setattr('vertia.engines.process.psutil.wait_procs', lambda items, timeout: (items, []))
    await engine.free()
    assert trace == ['parent', 'child'] and engine.process is None
    await engine.close()


@pytest.mark.asyncio
async def test_pending_progress_and_malformed_result_stop(tmp_path):
    api = AceApi()
    def handle(request):
        response = api.handle(request)
        if request.url.path == '/query_result' and api.polls == 1:
            return httpx.Response(200, json={'data': [{'task_id': 't1', 'status': 0,
                                  'result': json.dumps([{'progress': .65}])}]})
        return response
    engine = AceStepEngine(tmp_path, 8001, client=httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(handle)))
    engine.process = SimpleNamespace(poll=lambda: None)
    engine.stop = AsyncMock()
    progress = []
    await engine.generate(MusicTool(engine).validate(INSTRUMENTAL), progress.append)
    assert progress == [5, 65, 100]
    def malformed(request):
        if request.url.path == '/query_result':
            return httpx.Response(200, json={'data': [{'task_id': 't1', 'status': 1, 'result': '{}'}]})
        return api.handle(request)
    await engine.client.aclose()
    engine.client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(malformed))
    with pytest.raises(EngineError):
        await engine.generate(MusicTool(engine).validate(INSTRUMENTAL), progress.append)
    engine.stop.assert_awaited_once()
    await engine.client.aclose()


@pytest.mark.asyncio
async def test_failed_tree_stop_keeps_survivors_until_confirmed(tmp_path, monkeypatch):
    engine = engine_for(tmp_path, AceApi())
    exited = False
    def terminate_parent():
        nonlocal exited
        exited = True
    child = SimpleNamespace(terminate=lambda: None, kill=lambda: None)
    parent = SimpleNamespace(children=lambda recursive: [child], terminate=terminate_parent, kill=lambda: None)
    engine.process = SimpleNamespace(pid=123, poll=lambda: 0 if exited else None)
    monkeypatch.setattr('vertia.engines.process.psutil.Process', lambda pid: parent)
    monkeypatch.setattr('vertia.engines.process.psutil.wait_procs', lambda items, timeout: ([], [child]))
    with pytest.raises(EngineError, match='incomplet'):
        await engine.free()
    assert exited and engine.stopping == [child]
    # Même si le parent est terminé, le survivant interdit le démarrage suivant.
    with pytest.raises(EngineError, match='incomplet'):
        await engine.start()
    monkeypatch.setattr('vertia.engines.process.psutil.wait_procs', lambda items, timeout: (items, []))
    await engine.free()
    assert engine.stopping == [] and engine.process is None
    await engine.close()
