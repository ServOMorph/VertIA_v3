from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from vertia.app import create_app
from vertia.config import Settings
from vertia.resources.monitor import ResourceMonitor
from vertia.engines.comfy_qwen import ComfyQwenEngine
from vertia.engines.acestep import AceStepEngine
from vertia.engines.ollama_service import OllamaService


@pytest.fixture(autouse=True)
def offline_comfy(monkeypatch):
    monkeypatch.setenv('VERTIA_VERROU_GPU', '0')
    monkeypatch.setattr(OllamaService, 'start_background', lambda self: None)
    monkeypatch.setattr(ComfyQwenEngine, 'health', AsyncMock(return_value=False))
    monkeypatch.setattr(AceStepEngine, 'health', AsyncMock(return_value=False))


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(ResourceMonitor, '_hardware', lambda self: dict(
        gpus=[dict(used_mb=100, total_mb=8000, percent=1.25)],
        ram=dict(used_mb=1000, total_mb=48000, percent=2.1), processes=[], warnings=[]))
    return Settings.from_env(
        data_dir=tmp_path / "data",
        database=tmp_path / "data" / "vertia.db",
        outputs_dir=tmp_path / "outputs",
        local_config=tmp_path / ".vertia-local.json",
    )


@pytest.fixture
def app(settings):
    state = dict(gpus=[], processes=[], models=[], warnings=[],
                 ram=dict(used_mb=1000, total_mb=48000, percent=2.1))
    return create_app(settings, overrides={'monitor': SimpleNamespace(latest=state, sample=AsyncMock(return_value=state))})


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
