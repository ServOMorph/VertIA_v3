from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from vertia.app import create_app
from vertia.chat.context import ContextBuilder, estimate_messages
from vertia.chat.repository import ChatRepository
from vertia.chat.service import ChatService
from vertia.core.db import Database
from vertia.core.events import EventBus
from vertia.engines.ollama import OllamaClient


class FakeOllama:
    def __init__(self):
        self.calls = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.block = False
        self.fail = False
        self.cancelled = False
        self.closed = False
        self.running = 0
        self.maximum = 0

    async def models(self):
        return [{'name': 'fake'}]

    async def loaded_models(self):
        return []

    async def unload_model(self, model):
        pass

    async def prepare_model(self, model):
        pass

    async def chat_stream(self, model, messages, num_predict):
        self.calls.append(messages)
        self.running += 1
        self.maximum = max(self.maximum, self.running)
        try:
            self.started.set()
            yield {'message': {'content': 'Bonjour '}}
            if self.block:
                await self.release.wait()
            if self.fail:
                raise RuntimeError('Erreur simulée')
            yield {'message': {'content': '**local**'}}
            yield {'done': True, 'prompt_eval_count': estimate_messages(messages)}
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        finally:
            self.running -= 1

    async def close(self):
        self.closed = True


def make_service(tmp_path, num_ctx=2048):
    db = Database(tmp_path / 'chat.db')
    db.initialize()
    fake = FakeOllama()
    repo = ChatRepository(db)
    bus = EventBus()
    return ChatService(repo, fake, bus, num_ctx), repo, fake


async def drain(service):
    await asyncio.wait_for(asyncio.shield(service.worker), 3)


def test_context_pairs_budget_and_overflow():
    context = ContextBuilder(1024)
    history = [dict(role=role, contenu=str(index) * 150) for index in range(8) for role in ('user', 'assistant')]
    window = context.build('fake', '', history, 'question')
    assert window.omitted > 0 and window.omitted % 2 == 0
    assert window.estimated + context.response_margin <= 1024
    assert [m['role'] for m in window.messages][1:-1] == ['user', 'assistant'] * ((len(window.messages) - 2) // 2)
    context.calibrate('fake', window.estimated, window.estimated * 2)
    assert context.build('fake', '', history, 'question').omitted >= window.omitted
    with pytest.raises(ValueError, match='dépassent'):
        context.build('fake', '', [], 'x' * 5000)


@pytest.mark.asyncio
async def test_queue_serializes_and_retains_ephemeral_history(tmp_path):
    service, repo, fake = make_service(tmp_path)
    conv = repo.create_conversation('fake', None, True)
    service.submit(conv['id'], 'Je me nomme Alice')
    service.submit(conv['id'], 'Mon prénom ?')
    await drain(service)
    assert fake.maximum == 1
    assert fake.calls[1][1:3] == [
        {'role': 'user', 'content': 'Je me nomme Alice'},
        {'role': 'assistant', 'content': 'Bonjour **local**'},
    ]
    assert len(repo.messages(conv['id'])) == 4
    with repo.db.session() as conn:
        assert conn.execute('SELECT COUNT(*) FROM conversations').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0
    await service.close()


@pytest.mark.asyncio
async def test_stop_closes_active_stream_cancels_queue_and_keeps_partial(tmp_path):
    service, repo, fake = make_service(tmp_path)
    conv = repo.create_conversation('fake', None, False)
    fake.block = True
    service.submit(conv['id'], 'premier')
    service.submit(conv['id'], 'second')
    await fake.started.wait()
    assert service.messages(conv['id'])[1]['contenu'] == 'Bonjour '
    await service.stop(conv['id'])
    await drain(service)
    messages = repo.messages(conv['id'])
    assert fake.cancelled
    assert messages[1]['statut'] == 'arrete'
    assert messages[1]['contenu'] == 'Bonjour '
    assert messages[2]['statut'] == messages[3]['statut'] == 'annule'
    assert len(fake.calls) == 1
    fake.block = False
    service.submit(conv['id'], 'reprendre')
    await drain(service)
    assert len(fake.calls) == 2
    await service.close()


@pytest.mark.asyncio
async def test_stop_immediately_after_enqueue(tmp_path):
    service, repo, fake = make_service(tmp_path)
    conv = repo.create_conversation('fake', None, False)
    service.submit(conv['id'], 'annuler avant départ')
    await service.stop(conv['id'])
    await drain(service)
    assert not fake.calls
    assert repo.messages(conv['id'])[1]['statut'] == 'annule'
    await service.close()


@pytest.mark.asyncio
async def test_error_does_not_block_next_message(tmp_path):
    service, repo, fake = make_service(tmp_path)
    conv = repo.create_conversation('fake', None, False)
    fake.fail = True
    service.submit(conv['id'], 'erreur')
    await drain(service)
    assert repo.messages(conv['id'])[1]['statut'] == 'erreur'
    fake.fail = False
    service.submit(conv['id'], 'suite')
    await drain(service)
    assert repo.messages(conv['id'])[-1]['statut'] == 'termine'
    assert len(fake.calls[-1]) == 2
    await service.close()


@pytest.mark.asyncio
async def test_summary_incremental_only_after_foreground(tmp_path):
    service, repo, fake = make_service(tmp_path, 1024)
    conv = repo.create_conversation('fake', None, False)
    for index in range(8):
        repo.append(conv['id'], 'user', f'question {index}' * 12, 'termine')
        repo.append(conv['id'], 'assistant', f'reponse {index}' * 12, 'termine')
    service.submit(conv['id'], 'suite')
    service.submit(conv['id'], 'encore')
    await drain(service)
    current = repo.conversation(conv['id'])
    assert current['resume_count'] > 0
    assert current['resume_count'] % 2 == 0
    assert current['resume'] == 'Bonjour **local**'
    assert fake.calls[0][-1]['content'] == 'suite'
    assert fake.calls[1][-1]['content'] == 'encore'
    assert fake.maximum == 1
    service.submit(conv['id'], 'apres résumé')
    await drain(service)
    assert 'Bonjour **local**' in fake.calls[-1][0]['content']
    await service.close()


@pytest.mark.asyncio
async def test_shutdown_cancels_and_marks_pending(tmp_path):
    service, repo, fake = make_service(tmp_path)
    conv = repo.create_conversation('fake', None, False)
    fake.block = True
    service.submit(conv['id'], 'premier')
    service.submit(conv['id'], 'deuxième')
    await fake.started.wait()
    await asyncio.wait_for(service.close(), 2)
    assert fake.closed and fake.cancelled
    assert not service.pending
    assert repo.messages(conv['id'])[-1]['statut'] == 'annule'


def test_repository_restart_migration_and_folder_deletion(tmp_path):
    service, repo, _ = make_service(tmp_path)
    folder = repo.create_folder('Travail', 'Sois concis')
    conv = repo.create_conversation('fake', folder['id'], False)
    repo.append(conv['id'], 'user', 'interruption', 'actif')
    restored = ChatRepository(repo.db)
    assert restored.messages(conv['id'])[0]['statut'] == 'interrompu'
    restored.delete_folder(folder['id'])
    assert restored.conversation(conv['id'])['dossier_id'] is None
    restored.delete_conversation(conv['id'])
    assert restored.messages(conv['id']) == []


def test_chat_api_validation_crud_and_injection(settings):
    fake = FakeOllama()
    app = create_app(settings, overrides={'ollama': fake})
    with TestClient(app) as client:
        assert client.get('/api/modeles').json()['modeles'] == [{'name': 'fake'}]
        f = client.post('/api/dossiers', json={'nom': 'Projet', 'system_prompt': 'Sois précis'}).json()
        assert client.put('/api/dossiers/' + f['id'], json={'nom': 'Écriture', 'system_prompt': 'Sois bref'}).status_code == 200
        c = client.post('/api/conversations', json={'dossier_id': f['id'], 'modele': 'fake'}).json()
        path = '/api/conversations/' + c['id']
        assert client.post(path + '/messages', json={'contenu': '   '}).status_code == 422
        assert client.post(path + '/messages', json={'contenu': 'Bonjour'}).status_code == 202
        client.portal.call(drain, app.state.services.chat)
        assert 'Sois bref' in fake.calls[0][0]['content']
        assert len(client.get(path).json()['messages']) == 2
        assert client.get(path).json()['titre'] == 'Bonjour'
        assert client.patch(path, json={'titre': 'Titre'}).status_code == 200
        assert client.delete('/api/dossiers/' + f['id']).status_code == 200
        assert client.get(path).json()['dossier_id'] is None
        assert client.delete(path).status_code == 200
        assert client.get(path).status_code == 404
        assert client.post('/api/conversations', json={'dossier_id': 'inconnu'}).status_code == 404
    assert fake.closed


@pytest.mark.asyncio
async def test_ollama_ndjson_lifecycle_and_options():
    requests = []

    async def handler(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'models': [{'name': 'fake'}]})
        if request.url.path == '/api/generate':
            return httpx.Response(200, json={'done': True})
        return httpx.Response(200, text='\n' + json.dumps({'message': {'content': 'é'}}) + '\n' + json.dumps({'done': True}) + '\n')

    http = httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(handler))
    ollama = OllamaClient('http://ollama.test', 4096, http)
    assert await ollama.models() == [{'name': 'fake'}]
    assert await ollama.loaded_models() == [{'name': 'fake'}]
    await ollama.load_model('fake')
    await ollama.unload_model('fake')
    chunks = [chunk async for chunk in ollama.chat_stream('fake', [{'role': 'user', 'content': 'Salut'}], 128)]
    assert chunks[-1]['done']
    bodies = [json.loads(r.content) for r in requests if r.method == 'POST']
    assert all(b['options']['num_ctx'] == 4096 for b in bodies)
    assert [b['keep_alive'] for b in bodies] == [-1, 0, -1]
    assert bodies[-1]['options']['num_predict'] == 128
    await ollama.close()


@pytest.mark.asyncio
async def test_ollama_cancel_releases_http_response():
    closed = asyncio.Event()
    started = asyncio.Event()

    class BlockedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"message":{"content":"partiel"}}\n'
            started.set()
            await asyncio.Event().wait()

        async def aclose(self):
            closed.set()

    async def handler(request):
        return httpx.Response(200, stream=BlockedStream())

    http = httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(handler))
    ollama = OllamaClient('http://ollama.test', 1024, http)

    async def consume():
        async for _ in ollama.chat_stream('fake', [], 128):
            pass

    task = asyncio.create_task(consume())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    await ollama.close()


@pytest.mark.asyncio
async def test_new_message_preempts_summary_without_parallel_inference(tmp_path):
    service, repo, fake = make_service(tmp_path, 1024)
    summary_started = asyncio.Event()
    original = fake.chat_stream

    async def stream(model, messages, num_predict):
        is_summary = 'Actualise le résumé' in messages[0]['content']
        fake.block = is_summary
        if is_summary:
            summary_started.set()
        async for payload in original(model, messages, num_predict):
            yield payload

    fake.chat_stream = stream
    conv = repo.create_conversation('fake', None, False)
    for _ in range(6):
        repo.append(conv['id'], 'user', 'ancienne question ' * 10, 'termine')
        repo.append(conv['id'], 'assistant', 'ancienne réponse ' * 10, 'termine')
    service.submit(conv['id'], 'première demande')
    await asyncio.wait_for(summary_started.wait(), 2)
    service.submit(conv['id'], 'demande prioritaire')
    fake.release.set()
    await drain(service)
    assert fake.cancelled and fake.maximum == 1
    assert fake.calls[2][-1]['content'] == 'demande prioritaire'
    assert repo.messages(conv['id'])[-1]['statut'] == 'termine'
    await service.close()


@pytest.mark.asyncio
async def test_model_switch_unloads_only_other_models():
    unloaded = []

    async def handler(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'models': [{'name': 'other'}, {'model': 'chosen'}]})
        unloaded.append(json.loads(request.content))
        return httpx.Response(200, json={'done': True})

    client = httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(handler))
    ollama = OllamaClient('http://ollama.test', 2048, client)
    await ollama.prepare_model('chosen')
    assert [u['model'] for u in unloaded] == ['other']
    assert unloaded[0]['keep_alive'] == 0
    await ollama.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', ['{"error":"modèle absent"}\n', '{"message":{"content":"partiel"}}\n'])
async def test_ollama_reports_error_or_truncated_stream(payload):
    async def handler(request):
        return httpx.Response(200, text=payload)

    client = httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(handler))
    ollama = OllamaClient('http://ollama.test', 1024, client)
    with pytest.raises(RuntimeError):
        _ = [chunk async for chunk in ollama.chat_stream('fake', [], 128)]
    await ollama.close()


@pytest.mark.asyncio
async def test_chat_sse_offsets_and_terminal_status(tmp_path):
    service, repo, fake = make_service(tmp_path)
    conv = repo.create_conversation('fake', None, False)
    stream = service.events.subscribe()
    await anext(stream)
    job = service.submit(conv['id'], 'bonjour')
    await drain(service)
    events = []
    while True:
        event = await asyncio.wait_for(anext(stream), 1)
        events.append(event)
        if event.startswith('event: chat.fin'):
            break
    deltas = [json.loads(e.split('data: ')[1]) for e in events if e.startswith('event: chat.delta')]
    assert [d['offset'] for d in deltas] == [0, 8]
    assert all(d['message_id'] == job['message_id'] for d in deltas)
    assert json.loads(events[-1].split('data: ')[1])['statut'] == 'termine'
    await stream.aclose()
    await service.close()


def test_api_rejects_delete_during_generation(settings):
    fake = FakeOllama()
    fake.block = True
    app = create_app(settings, overrides={'ollama': fake})
    with TestClient(app) as client:
        f = client.post('/api/dossiers', json={'nom': 'Dossier'}).json()
        c = client.post('/api/conversations', json={'dossier_id': f['id']}).json()
        path = '/api/conversations/' + c['id']
        client.post(path + '/messages', json={'contenu': 'attendre'})
        client.portal.call(fake.started.wait)
        assert client.delete(path).status_code == 409
        assert client.delete('/api/dossiers/' + f['id']).status_code == 409
        assert client.patch(path, json={'dossier_id': None}).status_code == 409
        assert client.post(path + '/stop').status_code == 200
        assert client.delete(path).status_code == 200


@pytest.mark.asyncio
async def test_stop_also_cancels_summary_and_prevents_restart(tmp_path):
    service, repo, fake = make_service(tmp_path, 1024)
    conv = repo.create_conversation('fake', None, False)
    history = []
    for _ in range(2):
        history.extend([{'role': 'user', 'contenu': 'question'}, {'role': 'assistant', 'contenu': 'réponse'}])
    fake.block = True
    service.summaries[conv['id']] = (history, 4)
    service.worker = asyncio.create_task(service._work())
    await fake.started.wait()
    assert service.state()['resume'] == conv['id']
    await service.stop(conv['id'])
    await drain(service)
    assert fake.cancelled
    assert not service.summaries
    assert len(fake.calls) == 1
    await service.close()


@pytest.mark.asyncio
async def test_large_evicted_exchange_is_summarized_in_bounded_chunks(tmp_path):
    service, repo, fake = make_service(tmp_path, 1024)
    conv = repo.create_conversation('fake', None, False)
    history = [{'role': 'user', 'contenu': 'x' * 5000}, {'role': 'assistant', 'contenu': 'y' * 1000}]
    service.summaries[conv['id']] = (history, 2)
    service.worker = asyncio.create_task(service._work())
    await drain(service)
    assert repo.conversation(conv['id'])['resume_count'] == 2
    assert len(fake.calls) > 1
    assert all(estimate_messages(call) + service.context.response_margin <= 1024 for call in fake.calls)
    inputs = ''.join(call[-1]['content'] for call in fake.calls)
    assert inputs.count('x') == 5000 and inputs.count('y') == 1000
    await service.close()
