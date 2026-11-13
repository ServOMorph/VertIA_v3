from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest

from vertia.config import Settings
from vertia.setup import SetupConfig, diagnose, save_config


def config(settings, tmp_path):
    return SetupConfig.current(replace(settings, comfy_dir=tmp_path / 'comfy', acestep_dir=tmp_path / 'ace'))


def test_save_restart_and_no_hot_change(client, settings, tmp_path, monkeypatch):
    proposed = config(settings, tmp_path)
    before = client.app.state.services.arbiter.engines['comfy']
    start = AsyncMock(side_effect=AssertionError('Aucun lancement'))
    monkeypatch.setattr(before, 'start', start)
    assert not client.get('/api/installation').json()['accueil_termine']
    response = client.put('/api/installation', json=proposed.model_dump())
    assert response.status_code == 200
    assert response.json()['redemarrage_requis']
    state = client.get('/api/installation').json()
    assert state['configuration'] == proposed.model_dump()
    assert state['redemarrage_requis']
    assert before.directory == settings.comfy_dir
    loaded = Settings.from_env(local_config=settings.local_config)
    assert loaded.comfy_dir == tmp_path / 'comfy'
    assert loaded.acestep_dir == tmp_path / 'ace'
    assert client.post('/api/installation/terminer').status_code == 200
    assert client.get('/api/installation').json()['accueil_termine']
    start.assert_not_awaited()
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('change', [
    {'ollama_url': 'http://example.com'}, {'ollama_url': 'http://127.0.0.1.evil.test'},
    {'ollama_url': 'http://user:password@localhost'}, {'ollama_url': 'http://localhost/api'},
    {'ollama_url': 'http://localhost:99999'}, {'ollama_url': 'http://localhost#fragment'},
    {'ollama_url': 'https://localhost'}, {'comfy_dir': 'relative'},
    {'default_model': '  '}, {'acestep_port': 80}, {'unexpected': 'value'},
])
def test_invalid_settings_never_written(client, settings, tmp_path, change):
    proposed = config(settings, tmp_path).model_dump() | change
    assert client.put('/api/installation', json=proposed).status_code == 422
    assert not settings.local_config.exists()


def test_colliding_ports_and_write_failure(client, settings, tmp_path, monkeypatch):
    proposed = config(settings, tmp_path).model_dump()
    assert client.put('/api/installation', json=proposed | {'comfy_port': settings.port}).status_code == 422
    assert client.put('/api/installation', json=proposed | {'comfy_port': proposed['acestep_port']}).status_code == 422
    assert client.put('/api/installation', json=proposed | {'comfy_port': 11434}).status_code == 422
    assert client.put('/api/installation', json=proposed | {'ollama_url': f'http://localhost:{settings.port}'}).status_code == 422
    from vertia.web import setup
    monkeypatch.setattr(setup, 'save_config', lambda *args: (_ for _ in ()).throw(PermissionError()))
    response = client.put('/api/installation', json=proposed)
    assert response.status_code == 503
    assert 'droits' in response.json()['detail']


def test_atomic_replace_failure_preserves_previous_settings(settings, tmp_path, monkeypatch):
    proposed = config(settings, tmp_path)
    save_config(settings.local_config, proposed)
    previous = settings.local_config.read_bytes()
    from pathlib import Path
    monkeypatch.setattr(Path, 'replace', lambda *args: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(PermissionError):
        save_config(settings.local_config, proposed.model_copy(update={'default_model': 'different'}))
    assert settings.local_config.read_bytes() == previous
    assert not list(tmp_path.glob('*.tmp'))


def test_corrupt_config_recovery(settings):
    settings.local_config.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError, match='Configuration locale illisible'):
        Settings.from_env(local_config=settings.local_config)


@pytest.mark.asyncio
async def test_diagnostic_offline_and_present_files(settings, tmp_path):
    proposed = config(settings, tmp_path)
    requests = []

    def offline(request):
        requests.append(request)
        raise httpx.ConnectError('offline', request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(offline)) as client:
        state = await diagnose(proposed, client)
    assert all(not state[key]['joignable'] for key in ('ollama', 'comfy', 'ace'))
    assert not state['comfy']['installation']['present']
    assert not state['comfy']['image']['present']
    assert not state['comfy']['video']['present']
    assert not state['ace']['checkpoint_present']
    assert {r.method for r in requests} == {'GET'}
    assert {r.url.path for r in requests} == {'/api/tags', '/system_stats', '/health'}
    for section in ('installation', 'image', 'video'):
        for filename in state['comfy'][section]['manquants']:
            path = tmp_path / 'comfy' / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'not real model weights')
    checkpoint = tmp_path / 'ace/checkpoints/acestep-v15-turbo/config.json'
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text('{}', encoding='utf-8')

    def online(request):
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': proposed.default_model}, {'name': '<img onerror=alert(1)>'}]})
        if request.url.path == '/system_stats':
            return httpx.Response(200, json={'system': {}})
        return httpx.Response(200, json={'data': {'service': 'ACE-Step API', 'status': 'ok'}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(online)) as client:
        state = await diagnose(proposed, client)
    assert all(state[key]['joignable'] for key in ('ollama', 'comfy', 'ace'))
    assert state['ollama']['modele_choisi_present']
    assert all(state['comfy'][key]['present'] for key in ('installation', 'image', 'video'))
    assert state['ace']['checkpoint_present']
    assert not state['ace']['installation']['present']


def test_diagnostic_endpoint_rejects_unrelated_service(client, settings, tmp_path, monkeypatch):
    original = httpx.AsyncClient
    requests = []

    def response(request):
        requests.append(request)
        return httpx.Response(200, json={'message': 'unrelated service'})

    from vertia.web import setup
    monkeypatch.setattr(setup.httpx, 'AsyncClient', lambda **kwargs: original(
        transport=httpx.MockTransport(response), **kwargs))
    result = client.post('/api/installation/diagnostic', json=config(settings, tmp_path).model_dump())
    assert result.status_code == 200
    assert all(not result.json()[key]['joignable'] for key in ('ollama', 'comfy', 'ace'))
    assert len(requests) == 3
    assert not settings.local_config.exists()
