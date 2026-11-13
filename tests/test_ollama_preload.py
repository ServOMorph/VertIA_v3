import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from vertia.core.db import Database
from vertia.core.events import EventBus
from vertia.engines.ollama_preload import OllamaPreload
from vertia.engines.ollama_service import OllamaService
from vertia.jobs.arbiter import GpuArbiter
from vertia.jobs.queue import JobQueue
from vertia.resources.monitor import MemoryRefused


def setup_preload(tmp_path, state='pret'):
    events = EventBus()
    service = OllamaService('http://127.0.0.1:1', events)
    service.state['etat'] = state
    service.inspect = AsyncMock()
    client = SimpleNamespace(models=AsyncMock(return_value=[{'name': 'fake'}]),
                             prepare_model=AsyncMock(), load_model=AsyncMock(), unload_model=AsyncMock())
    engine = SimpleNamespace(start=AsyncMock(), free=AsyncMock())
    other = SimpleNamespace(start=AsyncMock(), free=AsyncMock())
    guard = SimpleNamespace(check=AsyncMock())
    arbiter = GpuArbiter({'ollama': engine, 'comfy': other}, guard)
    db = Database(tmp_path / 'preload.db')
    db.initialize()
    jobs = JobQueue(db, arbiter, events)
    return OllamaPreload(service, client, jobs, 'fake'), other


@pytest.mark.asyncio
async def test_preload_waits_for_service_and_uses_gpu_queue_once(tmp_path):
    warmup, other = setup_preload(tmp_path, 'demarrage')
    warmup.start()
    task = warmup.task
    warmup.start()
    assert warmup.task is task
    await asyncio.sleep(.01)
    warmup.client.load_model.assert_not_awaited()
    warmup.service.state['etat'] = 'pret'

    async def load(model):
        assert model == 'fake'
        assert warmup.jobs.arbiter.lock.locked()
        assert warmup.jobs.active
        other.free.assert_awaited_once()
        assert warmup.service.state['prechargement']['etat'] == 'chargement'
    warmup.client.load_model.side_effect = load
    await asyncio.wait_for(task, 2)
    warmup.client.prepare_model.assert_awaited_once_with('fake')
    warmup.client.load_model.assert_awaited_once_with('fake')
    job = warmup.jobs.list()[0]
    assert job['kind'] == 'prechargement_ollama' and job['status'] == 'termine'
    assert job['resumable'] == 0 and job['priority'] == 100
    assert warmup.service.state['prechargement']['etat'] == 'termine'
    warmup.service.update('pret', 'Ollama disponible', ['fake'])
    assert warmup.service.state['prechargement']['etat'] == 'termine'
    await warmup.close()
    await warmup.jobs.close()
    await warmup.service.close()


@pytest.mark.asyncio
async def test_preload_missing_model_does_not_load_or_enqueue(tmp_path):
    warmup, _ = setup_preload(tmp_path)
    warmup.client.models.return_value = [{'name': 'other'}]
    await warmup.run()
    assert 'n’est pas installé' in warmup.service.state['prechargement']['message']
    assert warmup.jobs.list() == []
    warmup.client.load_model.assert_not_awaited()
    await warmup.jobs.close()
    await warmup.service.close()


@pytest.mark.asyncio
async def test_preload_respects_memory_refusal(tmp_path):
    warmup, _ = setup_preload(tmp_path)
    warmup.jobs.arbiter.guard.check.side_effect = MemoryRefused('RAM insuffisante')
    await warmup.run()
    warmup.client.load_model.assert_not_awaited()
    assert warmup.jobs.list()[0]['status'] == 'erreur'
    assert 'RAM insuffisante' in warmup.service.state['prechargement']['message']
    await warmup.jobs.close()
    await warmup.service.close()


@pytest.mark.asyncio
async def test_preload_cancel_releases_gpu_and_keeps_service_available(tmp_path):
    warmup, _ = setup_preload(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()
    async def load(model):
        started.set()
        await release.wait()
    warmup.client.load_model.side_effect = load
    warmup.start()
    await asyncio.wait_for(started.wait(), 2)
    closing = asyncio.create_task(warmup.close())
    await asyncio.sleep(.01)
    assert not closing.done()
    assert warmup.jobs.arbiter.lock.locked()
    release.set()
    await asyncio.wait_for(closing, 2)
    warmup.client.unload_model.assert_awaited_once_with('fake')
    assert not warmup.jobs.arbiter.lock.locked()
    assert warmup.jobs.list()[0]['status'] == 'annule'
    assert warmup.service.state['etat'] == 'pret'
    assert warmup.service.state['prechargement']['etat'] == 'annule'
    await warmup.jobs.close()
    await warmup.service.close()
