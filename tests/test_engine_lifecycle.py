from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from vertia.engines.acestep import AceStepEngine
from vertia.engines.base import EngineError
from vertia.engines.comfy_qwen import ComfyQwenEngine
from vertia.jobs.arbiter import GpuArbiter


@pytest.mark.asyncio
@pytest.mark.parametrize('adapter', [ComfyQwenEngine, AceStepEngine])
async def test_surviving_child_blocks_start_and_gpu_handoff(tmp_path, monkeypatch, adapter):
    engine = adapter(tmp_path, 1, client=SimpleNamespace(aclose=AsyncMock()))
    dead = False
    def terminate_parent():
        nonlocal dead
        dead = True
    child = SimpleNamespace(terminate=lambda: None, kill=lambda: None)
    parent = SimpleNamespace(children=lambda recursive: [child], terminate=terminate_parent)
    engine.process = SimpleNamespace(pid=42, poll=lambda: 0 if dead else None)
    monkeypatch.setattr('vertia.engines.process.psutil.Process', lambda pid: parent)
    monkeypatch.setattr('vertia.engines.process.psutil.wait_procs', lambda items, timeout: ([], [child]))
    with pytest.raises(EngineError, match='incomplet'):
        await engine.free()
    assert dead and engine.stopping == [child]
    with pytest.raises(EngineError, match='incomplet'):
        await engine.start()
    other = SimpleNamespace(start=AsyncMock(), free=AsyncMock())
    arbiter = GpuArbiter({'source': engine, 'cible': other}, SimpleNamespace(check=AsyncMock()))
    operation = AsyncMock()
    with pytest.raises(EngineError, match='incomplet'):
        await arbiter.execute('cible', operation)
    other.start.assert_not_awaited()
    operation.assert_not_awaited()
    monkeypatch.setattr('vertia.engines.process.psutil.wait_procs', lambda items, timeout: (items, []))
    await arbiter.execute('cible', operation)
    assert engine.process is None and engine.stopping == []
    other.start.assert_awaited_once()
    operation.assert_awaited_once()
    await engine.close()


@pytest.mark.asyncio
async def test_repeated_cancellation_keeps_gpu_lock_until_owned_tree_stops(tmp_path, monkeypatch):
    engine = ComfyQwenEngine(tmp_path, 1, client=SimpleNamespace(aclose=AsyncMock()))
    engine.start = AsyncMock()
    engine.process = SimpleNamespace(pid=42, poll=lambda: None)
    parent = SimpleNamespace(children=lambda recursive: [], terminate=lambda: None)
    monkeypatch.setattr('vertia.engines.process.psutil.Process', lambda pid: parent)
    waiting = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    def wait(items, timeout):
        loop.call_soon_threadsafe(waiting.set)
        assert release.wait(5), 'Le test doit autoriser la fin de l’arrêt.'
        return items, []
    monkeypatch.setattr('vertia.engines.process.psutil.wait_procs', wait)
    arbiter = GpuArbiter({'comfy': engine}, SimpleNamespace(check=AsyncMock()))
    task = asyncio.create_task(arbiter.execute('comfy', engine.stop))
    try:
        await asyncio.wait_for(waiting.wait(), 2)
        for _ in range(2):
            task.cancel()
            await asyncio.sleep(0)
            assert arbiter.lock.locked() and not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not arbiter.lock.locked() and engine.process is None
    await engine.close()


@pytest.mark.asyncio
async def test_unhealthy_owned_comfy_is_stopped_before_replacement(tmp_path):
    engine = ComfyQwenEngine(tmp_path, 1, client=SimpleNamespace(aclose=AsyncMock()))
    engine.process = SimpleNamespace(poll=lambda: None)
    engine.stop = AsyncMock(side_effect=EngineError('Arrêt incomplet'))
    with pytest.raises(EngineError, match='incomplet'):
        await engine.start()
    engine.stop.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('adapter', [ComfyQwenEngine, AceStepEngine])
async def test_malformed_health_is_unavailable(tmp_path, adapter):
    # Les fixtures neutralisent health ; utiliser la méthode d'origine conservée par les tests API.
    from test_tools import REAL_HEALTH as comfy_health
    from test_music import REAL_HEALTH as ace_health
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=[])))
    engine = adapter(tmp_path, 1, client=client)
    health = comfy_health if adapter is ComfyQwenEngine else ace_health
    assert not await health(engine)
    await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('devices', [[], [{'type': 'cpu', 'torch_vram_total': 0}]])
async def test_external_comfy_without_gpu_measurement_refuses_handoff(tmp_path, devices):
    from test_tools import REAL_HEALTH
    def response(request):
        if request.url.path == '/system_stats':
            return httpx.Response(200, json={'system': {}, 'devices': devices})
        return httpx.Response(200, json={'queue_running': [], 'queue_pending': []})
    client = httpx.AsyncClient(base_url='http://fake', transport=httpx.MockTransport(response))
    engine = ComfyQwenEngine(tmp_path, 1, client=client)
    engine.health = REAL_HEALTH.__get__(engine)
    with pytest.raises(EngineError, match='non mesurable'):
        await engine.free()
    assert engine.process is None
    await engine.close()
