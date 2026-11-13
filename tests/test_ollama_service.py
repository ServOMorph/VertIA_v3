import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from vertia.app import create_app
from vertia.core.events import EventBus
from vertia.engines.ollama_service import OllamaService
from fastapi.testclient import TestClient


def service(handler, launcher=None, **kwargs):
    client = httpx.AsyncClient(base_url='http://127.0.0.1:11434', transport=httpx.MockTransport(handler))
    return OllamaService('http://127.0.0.1:11434', EventBus(), client=client, launcher=launcher or Mock(), **kwargs)


@pytest.mark.asyncio
async def test_existing_service_is_reused_without_model_loading_or_process_stop():
    calls = []
    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={'models': [{'name': 'fake'}]})
    manager = service(handler)
    manager._terminate = Mock(side_effect=AssertionError('Processus externe'))
    await manager.ensure()
    await manager.inspect()
    assert manager.state['etat'] == 'pret'
    assert manager.state['modeles_charges'] == ['fake']
    manager.launcher.assert_not_called()
    await manager.close()
    manager._terminate.assert_not_called()
    assert all(method == 'GET' for method, _ in calls)


@pytest.mark.asyncio
async def test_absent_service_launches_hidden_once_with_configured_host(tmp_path, monkeypatch):
    executable = tmp_path / 'ollama.exe'
    executable.write_text('fake', encoding='utf-8')
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if len(calls) == 1:
            raise httpx.ConnectError('Absent', request=request)
        return httpx.Response(200, json={'models': []})
    process = SimpleNamespace(poll=lambda: None)
    launcher = Mock(return_value=process)
    manager = service(handler, launcher, executable=str(executable))
    manager.url = 'http://127.0.0.1:11555'
    monkeypatch.setenv('OLLAMA_MODELS', 'D:/Models test')
    await manager.ensure()
    await manager.ensure()
    await manager.inspect()
    assert manager.state['modeles_charges'] == []
    launcher.assert_called_once()
    args, kwargs = launcher.call_args
    assert args[0] == [str(executable), 'serve']
    assert kwargs['env']['OLLAMA_HOST'] == '127.0.0.1:11555'
    assert kwargs['env']['OLLAMA_MODELS'] == 'D:/Models test'
    if os.name == 'nt':
        assert kwargs['creationflags'] != 0
    manager.stop = AsyncMock()
    await manager.close()
    manager.stop.assert_awaited_once()
    assert set(calls) == {'/api/tags', '/api/ps'}


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['https://127.0.0.1:11434', 'http://example.com:11434',
                                 'http://user:pass@127.0.0.1:11434', 'http://127.0.0.1:11434/api'])
async def test_automatic_launch_refuses_nonlocal_or_ambiguous_url(url):
    def handler(request):
        raise httpx.ConnectError('Absent', request=request)
    manager = service(handler)
    manager.url = url
    with pytest.raises(ValueError, match='locale'):
        await manager.ensure()
    manager.launcher.assert_not_called()
    await manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [{'service': 'autre'}, [], '<html>autre service</html>'])
async def test_occupied_port_does_not_launch_second_service(payload):
    manager = service(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(ValueError):
        await manager.ensure()
    manager.launcher.assert_not_called()
    await manager.close()


@pytest.mark.asyncio
async def test_unknown_loaded_models_does_not_claim_empty_memory():
    def handler(request):
        if request.url.path == '/api/ps':
            return httpx.Response(500)
        return httpx.Response(200, json={'models': []})
    manager = service(handler)
    await manager.inspect()
    assert manager.state['etat'] == 'pret'
    assert manager.state['modeles_charges'] is None
    assert 'inconnu' in manager.state['message']
    await manager.close()


@pytest.mark.asyncio
async def test_missing_executable_disabled_start_and_failed_start(tmp_path, monkeypatch):
    def handler(request):
        raise httpx.ConnectError('Absent', request=request)
    monkeypatch.setattr('vertia.engines.ollama_service.shutil.which', lambda name: None)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    manager = service(handler)
    with pytest.raises(ValueError, match='introuvable'):
        await manager.ensure()
    manager.launcher.assert_not_called()
    manager.autostart = False
    with pytest.raises(ValueError, match='désactivé'):
        await manager.ensure()
    manager.autostart = True
    binary = tmp_path / 'Programs' / 'Ollama' / 'ollama.exe'
    binary.parent.mkdir(parents=True)
    binary.write_text('fake', encoding='utf-8')
    assert manager.command() == str(binary)
    manager.launcher.return_value = SimpleNamespace(pid=42, poll=lambda: 1)
    parent = SimpleNamespace(children=lambda recursive: [], terminate=Mock())
    monkeypatch.setattr('vertia.engines.process.psutil.Process', lambda pid: parent)
    monkeypatch.setattr('vertia.engines.process.psutil.wait_procs', lambda items, timeout: (items, []))
    with pytest.raises(ValueError, match='arrêté'):
        await manager.ensure()
    await manager.close()
    parent.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_supervisor_publishes_failure_and_recovers_when_service_appears(monkeypatch):
    online = False
    def handler(request):
        if not online:
            raise httpx.ConnectError('Absent', request=request)
        return httpx.Response(200, json={'models': []})
    manager = service(handler, autostart=False)
    task = asyncio.create_task(manager.run())
    await asyncio.sleep(.01)
    assert manager.state['etat'] == 'erreur'
    assert 'désactivé' in manager.state['message']
    revision = manager.state['revision']
    online = True
    await manager.inspect()
    assert manager.state['etat'] == 'pret'
    assert manager.state['revision'] > revision
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await manager.close()


def test_lifespan_supervises_service_and_exposes_status(settings):
    manager = SimpleNamespace(start_background=Mock(), close=AsyncMock(),
                              state={'etat': 'demarrage', 'modeles_charges': None, 'revision': 0})
    app = create_app(settings, overrides={'ollama_service': manager})
    with TestClient(app) as client:
        manager.start_background.assert_called_once()
        assert client.get('/api/ollama/etat').json()['etat'] == 'demarrage'
    manager.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_windows_connection_refusal_is_detected_before_connect_timeout(tmp_path):
    executable = tmp_path / 'ollama.exe'
    executable.write_text('fake', encoding='utf-8')
    launcher = Mock(return_value=SimpleNamespace(poll=lambda: None))
    manager = OllamaService('http://127.0.0.1:11434', EventBus(), executable=str(executable), launcher=launcher)
    attempts = 0
    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            # Windows peut mettre plus de deux secondes à refuser une connexion locale.
            if request.extensions['timeout']['connect'] <= 2.1:
                raise httpx.ConnectTimeout('Délai dépassé avant le refus Windows', request=request)
            raise httpx.ConnectError('Connexion refusée par Windows', request=request)
        return httpx.Response(200, json={'models': []})
    await manager.client.aclose()
    manager.client = httpx.AsyncClient(base_url=manager.url, timeout=manager.client.timeout,
                                     transport=httpx.MockTransport(handler))
    await manager.ensure()
    await manager.inspect()
    launcher.assert_called_once()
    assert manager.state['etat'] == 'pret'
    assert manager.state['modeles_charges'] == []
    assert manager.client.timeout.read == 2
    manager.stop = AsyncMock()
    await manager.close()
