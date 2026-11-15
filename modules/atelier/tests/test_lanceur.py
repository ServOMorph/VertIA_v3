import sys
from unittest.mock import MagicMock

import pytest

import run_atelier


@pytest.mark.parametrize("arguments", [["--port", "4310"], ["--port", "0"], ["--port", "65536"]])
def test_port_interdit(monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["run_atelier.py", *arguments])
    serveur = MagicMock()
    monkeypatch.setattr(run_atelier.uvicorn, "Server", serveur)
    with pytest.raises(SystemExit) as erreur:
        run_atelier.main()
    assert erreur.value.code == 2
    serveur.assert_not_called()


def test_port_occupe(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_atelier.py"])
    monkeypatch.delenv("ATELIER_PORT", raising=False)
    sock = MagicMock()
    sock.__enter__.return_value = sock
    sock.bind.side_effect = OSError("occupé")
    monkeypatch.setattr(run_atelier.socket, "socket", MagicMock(return_value=sock))
    serveur = MagicMock()
    navigateur = MagicMock()
    monkeypatch.setattr(run_atelier.uvicorn, "Server", serveur)
    monkeypatch.setattr(run_atelier.webbrowser, "open", navigateur)
    with pytest.raises(SystemExit) as erreur:
        run_atelier.main()
    assert erreur.value.code == 1
    assert "occupé" in capsys.readouterr().err
    serveur.assert_not_called()
    navigateur.assert_not_called()


def test_lancement_simule_sans_navigateur(monkeypatch):
    monkeypatch.setenv("ATELIER_PORT", "4327")
    monkeypatch.setattr(sys, "argv", ["run_atelier.py", "--sans-navigateur"])
    sock = MagicMock()
    sock.__enter__.return_value = sock
    monkeypatch.setattr(run_atelier.socket, "socket", MagicMock(return_value=sock))
    config, serveur, thread = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(run_atelier.uvicorn, "Config", config)
    monkeypatch.setattr(run_atelier.uvicorn, "Server", serveur)
    monkeypatch.setattr(run_atelier.threading, "Thread", thread)
    run_atelier.main()
    sock.bind.assert_called_once_with(("127.0.0.1", 4327))
    serveur.return_value.run.assert_called_once_with(sockets=[sock])
    config.assert_called_once_with(run_atelier.app, host="127.0.0.1", port=4327)
    thread.assert_not_called()
