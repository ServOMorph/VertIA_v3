from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vertia.app import create_app
from vertia.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings.from_env(
        data_dir=tmp_path / "data",
        database=tmp_path / "data" / "vertia.db",
        outputs_dir=tmp_path / "outputs",
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
