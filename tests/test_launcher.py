from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import run


def test_occupied_port_does_not_open_old_interface_or_start_server(monkeypatch, capsys):
    monkeypatch.setattr(run.sys, 'argv', ['run.py'])
    monkeypatch.setattr(run.Settings, 'from_env', lambda: SimpleNamespace(host='127.0.0.1', port=4310))
    monkeypatch.setattr(run, 'port_in_use', lambda *args: True)
    thread, server = Mock(), Mock()
    monkeypatch.setattr(run.threading, 'Thread', thread)
    monkeypatch.setattr(run.uvicorn, 'run', server)
    with pytest.raises(SystemExit) as error:
        run.main()
    assert error.value.code == 1
    assert 'ancienne instance' in capsys.readouterr().err
    thread.assert_not_called()
    server.assert_not_called()


def test_available_port_keeps_normal_startup(monkeypatch):
    monkeypatch.setattr(run.sys, 'argv', ['run.py', '--no-browser', '--no-reload'])
    monkeypatch.setattr(run.Settings, 'from_env', lambda: SimpleNamespace(host='127.0.0.1', port=4310, url='http://127.0.0.1:4310'))
    monkeypatch.setattr(run, 'port_in_use', lambda *args: False)
    server = Mock()
    monkeypatch.setattr(run.uvicorn, 'run', server)
    run.main()
    assert server.call_args.kwargs['port'] == 4310
    assert server.call_args.kwargs['reload'] is False


def test_port_check_handles_connection_refused(monkeypatch):
    monkeypatch.setattr(run.socket, 'create_connection', Mock(side_effect=ConnectionRefusedError))
    assert run.port_in_use('127.0.0.1', 4310) is False
