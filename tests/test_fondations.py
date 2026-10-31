from __future__ import annotations

import asyncio
import re
from pathlib import Path

from vertia.core.db import MIGRATIONS, Database
from vertia.core.events import EventBus

TEMPLATE = Path(__file__).resolve().parents[1] / "src" / "vertia" / "templates" / "index.html"


def test_sante(client):
    response = client.get("/api/sante")
    assert response.status_code == 200
    assert response.json()["statut"] == "ok"


def test_page_accueil(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "VertIA" in response.text


def test_statiques(client):
    assert client.get("/static/css/tokens.css").status_code == 200
    assert client.get("/static/js/main.js").status_code == 200
    assert client.get("/static/fonts/inter-latin.woff2").status_code == 200


def test_migrations_idempotentes(tmp_path):
    db = Database(tmp_path / "x.db")
    assert db.initialize() == len(MIGRATIONS)
    assert db.initialize() == len(MIGRATIONS)


def test_preferences_ui_defaut_puis_maj(client):
    defaut = client.get("/api/preferences/ui").json()
    assert defaut["panels"]["chat"] is True
    nouveau = {"panels": {**defaut["panels"], "memoire": True}}
    assert client.put("/api/preferences/ui", json=nouveau).status_code == 200
    assert client.get("/api/preferences/ui").json()["panels"]["memoire"] is True


def test_preferences_ui_panneau_inconnu(client):
    response = client.put("/api/preferences/ui", json={"panels": {"inconnu": True}})
    assert response.status_code == 422


def test_bus_evenements_diffuse():
    async def scenario():
        bus = EventBus()
        stream = bus.subscribe(heartbeat=5)
        assert (await anext(stream)).startswith(": connecte")
        bus.publish("test", {"a": 1})
        message = await anext(stream)
        await stream.aclose()
        return message, bus.subscriber_count

    message, restants = asyncio.run(scenario())
    assert message == 'event: test\ndata: {"a": 1}\n\n'
    assert restants == 0


def test_contrat_ui_panneaux():
    html = TEMPLATE.read_text(encoding="utf-8")
    panneaux = set(re.findall(r'data-panel="([a-z]+)"', html))
    bascules = set(re.findall(r'data-toggle="([a-z]+)"', html))
    assert panneaux == bascules == {"chat", "fichiers", "memoire", "outils"}
    for ident in ("etat-serveur", "panel-toggles", "workspace", "chat-zone"):
        assert f'id="{ident}"' in html
