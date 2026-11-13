from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from vertia.app import create_app
from vertia.engines.ollama import OllamaEngine
from vertia.jobs.arbiter import GpuArbiter
from vertia.resources.monitor import MemoryGuard, MemoryRefused, parse_processes


def snapshot(free=600, model='fake', context=16384):
    used = 8192 - free
    return dict(ram=dict(total_mb=48000, used_mb=12000, percent=25),
                gpus=[dict(total_mb=8192, used_mb=used, percent=100 * used / 8192)],
                models=[dict(name=model, context_length=context, size_vram=6000 * 1024**2)],
                processes=[], warnings=[])


def arbiter_for(state):
    monitor = SimpleNamespace(sample=AsyncMock(return_value=state))
    engine = OllamaEngine(SimpleNamespace(num_ctx=16384))
    return GpuArbiter({'ollama': engine}, MemoryGuard(monitor, 92, 90))


@pytest.mark.asyncio
async def test_resident_model_can_run_above_normal_threshold():
    arbiter = arbiter_for(snapshot())
    operation = AsyncMock(return_value='ok')
    assert await arbiter.execute('ollama', operation, memory_request='fake') == 'ok'
    operation.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['other_model', 'other_context', 'missing_context', 'missing_size', 'cpu', 'multiple', 'unknown', 'no_request'])
async def test_resident_exception_requires_exact_loaded_model_and_context(change):
    state = snapshot()
    if change == 'other_model': state['models'][0]['name'] = 'other'
    if change == 'other_context': state['models'][0]['context_length'] = 4096
    if change == 'missing_context': state['models'][0].pop('context_length')
    if change == 'missing_size': state['models'][0].pop('size_vram')
    if change == 'cpu': state['models'][0]['size_vram'] = 0
    if change == 'multiple': state['models'].append(dict(state['models'][0], name='other'))
    if change == 'unknown': state['models'] = []
    arbiter = arbiter_for(state)
    operation = AsyncMock()
    with pytest.raises(MemoryRefused, match='limite de 92'):
        await arbiter.execute('ollama', operation, memory_request=None if change == 'no_request' else 'fake')
    operation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('free', [511, 100, 0])
async def test_resident_model_is_refused_near_saturation(free):
    arbiter = arbiter_for(snapshot(free=free))
    operation = AsyncMock()
    with pytest.raises(MemoryRefused, match='réserve requise 512'):
        await arbiter.execute('ollama', operation, memory_request='fake')
    operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_ram_limit_still_applies_to_resident_model():
    state = snapshot()
    state['ram']['percent'] = 90
    with pytest.raises(MemoryRefused, match='RAM'):
        await arbiter_for(state).execute('ollama', AsyncMock(), memory_request='fake')


@pytest.mark.asyncio
async def test_resident_policy_uses_new_sample_after_other_engine_freed():
    state = snapshot(free=200)
    arbiter = arbiter_for(state)
    async def release():
        state.update(snapshot(free=600))
    arbiter.engines['other'] = SimpleNamespace(free=release)
    await arbiter.execute('ollama', AsyncMock(), memory_request='fake')
    assert arbiter.active == 'ollama'


def test_chat_uses_resident_policy_end_to_end(settings):
    from test_chat import FakeOllama, drain
    fake = FakeOllama()
    fake.num_ctx = 16384
    state = snapshot()
    fake.loaded_models = AsyncMock(return_value=state['models'])
    app = create_app(settings, overrides={'ollama': fake,
                                         'monitor': SimpleNamespace(latest=state, sample=AsyncMock(return_value=state))})
    with TestClient(app) as client:
        conv = client.post('/api/conversations', json={'modele': 'fake'}).json()
        path = '/api/conversations/' + conv['id']
        assert client.post(path + '/messages', json={'contenu': 'Bonjour'}).status_code == 202
        client.portal.call(drain, app.state.services.chat)
        message = client.get(path).json()['messages'][1]
        assert message['statut'] == 'termine'
        assert 'Bonjour' in message['contenu']
        assert app.state.services.jobs.memory_requests == {}


def test_windows_process_memory_accepts_cim_name():
    rows = parse_processes('[{"Name":"pid_23772_luid_0x1_phys_0","LocalUsage":1048576},'
                           '{"InstanceName":null,"LocalUsage":20}]')
    assert rows == [{'pid': 23772, 'used_mb': 1}]


@pytest.mark.asyncio
async def test_resident_reserve_scales_with_large_gpu():
    state = snapshot()
    state['gpus'] = [dict(total_mb=65536, used_mb=64536, percent=98.47)]
    with pytest.raises(MemoryRefused, match='presque saturée'):
        await arbiter_for(state).execute('ollama', AsyncMock(), memory_request='fake')
