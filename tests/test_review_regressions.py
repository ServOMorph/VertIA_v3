import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import psutil
import pytest
from fastapi.testclient import TestClient

from test_jobs import drain, setup_queue
from test_tools import make_app, request_card
from vertia.engines.base import EngineError, MemoryNeeds
from vertia.engines.ollama import OllamaClient, OllamaEngine
from vertia.engines.process import ProcessOwner
from vertia.jobs.arbiter import GpuArbiter
from vertia.resources.monitor import MemoryRefused


@pytest.mark.asyncio
@pytest.mark.parametrize('parent_missing', [False, True])
async def test_dead_parent_survivors_block_gpu_handoff(monkeypatch, parent_missing):
    owner = ProcessOwner('fake')
    owner.process = SimpleNamespace(pid=42, poll=lambda: 1)
    child = SimpleNamespace(info={'ppid': 42}, children=lambda recursive: [],
                            terminate=Mock(), kill=Mock())
    parent = SimpleNamespace(children=Mock(return_value=[child]), terminate=Mock())
    lookup = Mock(side_effect=psutil.NoSuchProcess(42)) if parent_missing else Mock(return_value=parent)
    monkeypatch.setattr('vertia.engines.process.psutil.Process', lookup)
    monkeypatch.setattr('vertia.engines.process.psutil.process_iter', lambda attrs: iter([child]))
    wait = Mock(return_value=([], [child]))
    monkeypatch.setattr('vertia.engines.process.psutil.wait_procs', wait)
    target = SimpleNamespace(start=AsyncMock(), free=AsyncMock())
    arbiter = GpuArbiter({'source': SimpleNamespace(free=owner.stop), 'target': target},
                         SimpleNamespace(check=AsyncMock()))
    operation = AsyncMock()
    with pytest.raises(EngineError, match='incomplet'):
        await arbiter.execute('target', operation)
    assert owner.process is not None and owner.stopping == [child]
    child.terminate.assert_called_once()
    child.kill.assert_called_once()
    target.start.assert_not_awaited()
    operation.assert_not_awaited()
    wait.return_value = ([child], [])
    await arbiter.execute('target', operation)
    assert owner.process is None and owner.stopping == []
    operation.assert_awaited_once()


def test_cancel_latest_retry_keeps_conversation_busy(settings):
    app, _, qwen = make_app(settings)
    qwen.generate = AsyncMock(side_effect=RuntimeError('Échec simulé'))
    with TestClient(app) as client:
        path, conv = request_card(client, app)
        card = conv['actions'][0]
        queue = app.state.services.jobs
        job = client.post('/api/actions/' + card['id'] + '/valider',
                          json={'parameters': card['parameters']}).json()['job_id']
        client.portal.call(drain, queue)
        assert queue.get(job)['status'] == 'erreur'
        started = asyncio.Event()

        async def blocked(*args):
            started.set()
            await asyncio.Event().wait()

        qwen.generate.side_effect = blocked
        first = client.post('/api/jobs/' + job + '/reprendre').json()['id']
        client.portal.call(started.wait)
        latest = client.post('/api/jobs/' + job + '/reprendre').json()['id']
        assert client.post('/api/jobs/' + latest + '/annuler').status_code == 200
        assert queue.get(first)['status'] == 'actif'
        assert app.state.services.actions.busy(conv['id'])
        assert client.delete(path).status_code == 409
        assert client.post('/api/jobs/' + first + '/annuler').status_code == 200
        assert not app.state.services.actions.busy(conv['id'])
        assert client.delete(path).status_code == 200


@pytest.mark.asyncio
async def test_failed_start_retry_rechecks_minimum_ram(tmp_path):
    queue, arbiter, monitor, _ = setup_queue(tmp_path)
    engine = arbiter.engines['comfy']
    engine.memory = MemoryNeeds(ram_mb=17000)
    engine.start = AsyncMock(side_effect=EngineError('Démarrage échoué'))
    operation = AsyncMock()
    try:
        with pytest.raises(EngineError, match='Démarrage'):
            await arbiter.execute('comfy', operation)
        engine.start.side_effect = None
        monitor.latest['ram']['used_mb'] = 30000
        with pytest.raises(MemoryRefused, match='17000'):
            await arbiter.execute('comfy', operation)
        assert arbiter.active is None
        engine.start.assert_awaited_once()
        operation.assert_not_awaited()
    finally:
        await queue.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [httpx.ConnectError, httpx.ConnectTimeout])
async def test_offline_ollama_does_not_block_other_engine(error):
    def offline(request):
        raise error('Ollama arrêté', request=request)

    client = OllamaClient('http://fake', 2048, httpx.AsyncClient(
        base_url='http://fake', transport=httpx.MockTransport(offline)))
    target = SimpleNamespace(start=AsyncMock(), free=AsyncMock())
    arbiter = GpuArbiter({'ollama': OllamaEngine(client), 'target': target},
                         SimpleNamespace(check=AsyncMock()))
    operation = AsyncMock(return_value='ok')
    try:
        assert await arbiter.execute('target', operation) == 'ok'
        target.start.assert_awaited_once()
        operation.assert_awaited_once()
    finally:
        await client.close()
    for stage in ['list', 'unload']:
        for failure in [httpx.ReadTimeout('Lecture'), ValueError('Réponse invalide')]:
            fake = SimpleNamespace(loaded_models=AsyncMock(return_value=[{'name': 'fake'}]),
                                   unload_model=AsyncMock())
            method = fake.loaded_models if stage == 'list' else fake.unload_model
            method.side_effect = failure
            with pytest.raises(type(failure), match=str(failure)):
                await OllamaEngine(fake).free()
