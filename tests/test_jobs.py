from __future__ import annotations

import asyncio
import json
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from vertia.app import create_app
from vertia.core.db import Database
from vertia.core.events import EventBus
from vertia.jobs.arbiter import GpuArbiter
from vertia.jobs.queue import JobQueue
from vertia.resources.monitor import MemoryGuard, ResourceMonitor, parse_gpus, parse_processes


class FakeMonitor:
    def __init__(self):
        self.latest = dict(gpus=[dict(used_mb=1000, total_mb=8000, percent=12.5)],
                           ram=dict(used_mb=10000, total_mb=48000, percent=21),
                           models=[], processes=[], warnings=[])

    async def sample(self):
        return self.latest


class FakeEngine:
    def __init__(self, name, trace):
        self.name, self.trace = name, trace
        self.fail = False

    async def start(self):
        self.trace.append('start:' + self.name)

    async def free(self):
        self.trace.append('free:' + self.name)
        if self.fail:
            raise RuntimeError('Libération impossible')


def setup_queue(tmp_path):
    db = Database(tmp_path / 'jobs.db')
    db.initialize()
    trace = []
    monitor = FakeMonitor()
    engines = {name: FakeEngine(name, trace) for name in ['ollama', 'comfy', 'ace', 'video']}
    arbiter = GpuArbiter(engines, MemoryGuard(monitor, 92, 90), idle_seconds=1)
    queue = JobQueue(db, arbiter, EventBus())
    return queue, arbiter, monitor, trace


async def drain(queue):
    if queue.worker:
        await asyncio.wait_for(asyncio.shield(queue.worker), 3)


@pytest.mark.asyncio
async def test_arbiter_exclusive_switch_and_idle_release(tmp_path):
    queue, arbiter, _, trace = setup_queue(tmp_path)
    running = maximum = 0

    async def operation():
        nonlocal running, maximum
        running += 1
        maximum = max(maximum, running)
        await asyncio.sleep(.01)
        running -= 1

    await asyncio.gather(*(arbiter.execute(name, operation) for name in arbiter.engines))
    assert maximum == 1
    assert trace.index('free:ollama', trace.index('start:ollama')) < trace.index('start:comfy')
    assert arbiter.active == 'video'
    arbiter.last_used = time.monotonic() - 2
    await arbiter.release_idle()
    assert arbiter.active is None
    await queue.close()


@pytest.mark.asyncio
async def test_failed_free_prevents_next_engine(tmp_path):
    queue, arbiter, _, trace = setup_queue(tmp_path)
    arbiter.engines['ollama'].fail = True
    with pytest.raises(RuntimeError, match='Libération'):
        await arbiter.execute('comfy', lambda: asyncio.sleep(0))
    assert 'start:comfy' not in trace
    await queue.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('resource,percent', [('ram', 90), ('gpus', 92)])
async def test_guard_refuses_before_engine_start(tmp_path, resource, percent):
    queue, arbiter, monitor, trace = setup_queue(tmp_path)
    metric = monitor.latest[resource][0] if resource == 'gpus' else monitor.latest[resource]
    metric['percent'] = percent
    with pytest.raises(RuntimeError, match='RAM|VRAM'):
        await arbiter.execute('ollama', lambda: asyncio.sleep(0))
    assert 'start:ollama' not in trace
    await queue.close()


@pytest.mark.asyncio
async def test_priority_progress_sse_and_errors_do_not_block(tmp_path):
    queue, _, _, _ = setup_queue(tmp_path)
    trace = []

    async def handler(payload, progress):
        trace.append(payload['name'])
        progress(50)
        if payload.get('fail'):
            raise RuntimeError('Erreur simulée')

    queue.register('fake', handler)
    stream = queue.events.subscribe()
    await anext(stream)
    low = queue.submit('fake', 'comfy', {'name': 'low'}, -10)
    high = queue.submit('fake', 'ollama', {'name': 'high', 'fail': True}, 10)
    cancelled = queue.submit('fake', 'video', {'name': 'cancelled'})
    await queue.cancel(cancelled)
    await drain(queue)
    assert trace == ['high', 'low']
    assert queue.get(low)['progress'] == 100
    assert queue.get(high)['status'] == 'erreur'
    assert queue.get(cancelled)['status'] == 'annule'
    events = []
    while True:
        event = await asyncio.wait_for(anext(stream), 1)
        events.append(event)
        if '"progress": 100.0' in event:
            break
    assert any('"progress": 50.0' in event and 'event: jobs.maj' in event for event in events)
    await stream.aclose()
    await queue.close()


@pytest.mark.asyncio
async def test_active_cancellation_unwinds_before_next_job(tmp_path):
    queue, _, _, _ = setup_queue(tmp_path)
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def blocked():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            stopped.set()

    task = asyncio.create_task(queue.run('chat', 'ollama', blocked))
    await started.wait()
    job_id = queue.active
    await queue.cancel(job_id)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
    assert queue.get(job_id)['status'] == 'annule'
    await queue.run('chat', 'ollama', lambda: asyncio.sleep(0))
    await queue.close()


@pytest.mark.asyncio
async def test_transient_chat_failure_does_not_persist_private_error(tmp_path):
    queue, _, _, _ = setup_queue(tmp_path)

    async def fail():
        raise RuntimeError('Texte privé renvoyé dans une erreur du moteur')

    with pytest.raises(RuntimeError, match='Texte privé'):
        await queue.run('chat', 'ollama', fail)
    assert 'Texte privé' not in json.dumps(queue.list())
    assert queue.list()[0]['status'] == 'erreur'
    await queue.close()


@pytest.mark.asyncio
async def test_restart_pending_replay_and_explicit_interrupted_retry(tmp_path):
    queue, arbiter, _, _ = setup_queue(tmp_path)
    # Simuler l'état disque d'un processus disparu sans exécuter son worker.
    with queue.db.session() as conn:
        for job_id, status, resumable in [('pending', 'attente', 1), ('running', 'actif', 1), ('chat', 'attente', 0)]:
            conn.execute('INSERT INTO jobs(id,kind,engine,status,resumable) VALUES(?,?,?,?,?)',
                         (job_id, 'fake', 'ollama', status, resumable))
    restored = JobQueue(queue.db, arbiter, queue.events)
    calls = []

    async def handler(payload, progress):
        calls.append(payload)

    restored.register('fake', handler)
    assert restored.get('running')['status'] == restored.get('chat')['status'] == 'interrompu'
    restored.start()
    await drain(restored)
    assert len(calls) == 1 and restored.get('pending')['status'] == 'termine'
    retry_id = restored.retry('running')
    await drain(restored)
    assert len(calls) == 2 and restored.get(retry_id)['status'] == 'termine'
    with pytest.raises(ValueError):
        restored.retry('chat')
    await restored.close()
    await queue.close()


@pytest.mark.asyncio
async def test_queue_shutdown_and_priority_validation(tmp_path):
    queue, _, _, _ = setup_queue(tmp_path)
    started = asyncio.Event()

    async def blocked(payload, progress):
        started.set()
        await asyncio.Event().wait()

    queue.register('fake', blocked)
    active = queue.submit('fake', 'ace')
    await started.wait()
    pending = queue.submit('fake', 'video')
    queue.prioritize(pending, 20)
    with pytest.raises(ValueError):
        queue.prioritize(active, 20)
    await queue.close()
    assert queue.get(active)['status'] == 'interrompu'
    assert queue.get(pending)['status'] == 'attente'


@pytest.mark.asyncio
async def test_chat_and_other_engine_share_exclusive_queue(tmp_path):
    from test_chat import FakeOllama, drain as drain_chat
    from vertia.chat.repository import ChatRepository
    from vertia.chat.service import ChatService

    queue, arbiter, _, _ = setup_queue(tmp_path)
    fake = FakeOllama()
    fake.block = True
    repo = ChatRepository(queue.db)
    service = ChatService(repo, fake, queue.events, 2048, jobs=queue)
    conv = repo.create_conversation('fake', None, True)
    called = []

    async def handler(payload, progress):
        assert fake.running == 0
        assert arbiter.active == 'comfy'
        called.append(True)

    queue.register('image', handler)
    service.submit(conv['id'], 'premier')
    await fake.started.wait()
    image = queue.submit('image', 'comfy', priority=10)
    assert queue.get(image)['status'] == 'attente'
    await service.stop(conv['id'])
    await drain_chat(service)
    await drain(queue)
    assert called == [True] and fake.cancelled
    assert repo.messages(conv['id'])[1]['statut'] == 'arrete'
    assert queue.get(image)['status'] == 'termine'
    await service.close()
    await queue.close()


def test_monitor_parses_multi_gpu_wddm_and_unavailable_values():
    gpus = parse_gpus('1000, 8000, 20, 50\nN/A, N/A, N/A, N/A\n200, 4000, N/A, 40')
    assert len(gpus) == 2
    assert gpus[0]['percent'] == 12.5 and gpus[1]['utilization'] is None
    assert parse_processes(json.dumps([
        dict(InstanceName='pid_42_luid_1_phys_0', LocalUsage=1024 ** 2),
        dict(InstanceName='pid_42_luid_1_phys_1', LocalUsage=2 * 1024 ** 2),
    ])) == [dict(pid=42, used_mb=3)]
    assert parse_processes('null') == []


@pytest.mark.asyncio
async def test_monitor_reports_missing_tools_without_inventing_gpu():
    class Ollama:
        async def loaded_models(self):
            raise OSError('offline')

    def unavailable(args):
        raise subprocess.TimeoutExpired(args, 4)

    monitor = ResourceMonitor(Ollama(), unavailable)
    state = await monitor.sample()
    assert state['gpus'] == state['models'] == []
    assert state['ram']['total_mb'] > 0 and len(state['warnings']) >= 2


def test_resource_api_controls_and_jobs(settings):
    from test_chat import FakeOllama

    trace = []
    monitor = FakeMonitor()
    app = create_app(settings, overrides={'ollama': FakeOllama(), 'monitor': monitor,
                                         'engines': {'comfy': FakeEngine('comfy', trace)}})
    queue = app.state.services.jobs

    async def handler(payload, progress):
        await asyncio.Event().wait()

    queue.register('fake', handler)
    with TestClient(app) as client:
        assert client.get('/api/ressources').json()['limits'] == dict(vram=92, ram=90)
        assert client.post('/api/ressources/liberer?engine=inconnu').status_code == 422
        assert client.post('/api/ressources/liberer').status_code == 200
        job_id = client.portal.call(queue.submit, 'fake', 'comfy')
        assert client.get('/api/jobs').json()[0]['id'] == job_id
        assert client.post('/api/ressources/liberer').status_code == 409
        assert client.patch('/api/jobs/' + job_id, json={'priority': 101}).status_code == 422
        assert client.post('/api/jobs/' + job_id + '/annuler').json()['status'] == 'annule'
        assert client.post('/api/jobs/' + job_id + '/reprendre').status_code == 202
        assert client.post('/api/jobs/missing/annuler').status_code == 404


def test_chat_guard_failure_is_visible_and_ephemeral_payload_not_saved(settings):
    from test_chat import FakeOllama, drain as drain_chat

    monitor = FakeMonitor()
    monitor.latest['ram']['percent'] = 99
    fake = FakeOllama()
    app = create_app(settings, overrides={'ollama': fake, 'monitor': monitor})
    with TestClient(app) as client:
        conv = client.post('/api/conversations', json={'modele': 'fake', 'ephemere': True}).json()
        path = '/api/conversations/' + conv['id']
        client.post(path + '/messages', json={'contenu': 'Texte privé éphémère'})
        client.portal.call(drain_chat, app.state.services.chat)
        message = client.get(path).json()['messages'][1]
        assert message['statut'] == 'erreur' and 'RAM' in message['erreur']
        assert not fake.calls
        jobs = client.get('/api/jobs').json()
        assert jobs[0]['status'] == 'erreur' and jobs[0]['payload'] == {}
        assert 'Texte privé' not in json.dumps(jobs)
