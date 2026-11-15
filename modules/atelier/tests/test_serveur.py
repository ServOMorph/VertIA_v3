from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from modules.atelier import serveur


@pytest.fixture
def client(tmp_path):
    with TestClient(serveur.creer_app(tmp_path / "projets")) as client:
        yield client


def test_enregistrer_relire_lister(client, tmp_path):
    assert client.get("/api/projets").json() == []
    assert not (tmp_path / "projets").exists()
    projet = {"format": "atelier", "version": 1, "calques": []}
    assert client.post("/api/projets/Mandala 1", json=projet).status_code == 200
    assert client.get("/api/projets/Mandala 1").json() == projet
    assert client.get("/api/projets").json() == ["Mandala 1"]
    assert client.post("/api/projets/Mandala 1", json={"nouveau": True}).status_code == 200
    assert client.get("/api/projets/Mandala 1").json() == {"nouveau": True}
    assert not list((tmp_path / "projets").glob("*.tmp"))


@pytest.mark.parametrize("nom", ["..", "../x", "a/b", "a\\b", "/absolu", "C:\\x", "", " ", "x" * 81])
def test_traversee(client, tmp_path, nom):
    url = "/api/projets/" + quote(nom, safe="")
    assert client.post(url, json={}).status_code in (400, 404)
    assert client.get(url).status_code in (400, 404)
    assert list(tmp_path.rglob("*.json")) == []


def test_html(client):
    reponse = client.get("/")
    assert reponse.status_code == 200
    assert "text/html" in reponse.headers["content-type"]
    assert "Atelier" in reponse.text


@pytest.mark.parametrize("nom", ["%2E%2E", "%2E%2E%2Fx", "%00", "%20", "%2Fetc%2Fpasswd"])
def test_traversee_encodee(client, tmp_path, nom):
    assert client.post(f"/api/projets/{nom}", json={}).status_code == 400
    assert client.get(f"/api/projets/{nom}").status_code == 400
    assert list(tmp_path.rglob("*.json")) == []


def test_erreurs(client, monkeypatch):
    assert client.get("/api/projets/absent").status_code == 404
    assert client.post("/api/projets/test", content="{").status_code == 400
    assert client.post("/api/projets/test", json=[]).status_code == 400
    monkeypatch.setattr(serveur, "MAX_CORPS_OCTETS", 8)
    assert client.post("/api/projets/test", content=b"x" * 9).status_code == 413


def test_lien_hors_dossier(tmp_path):
    dossier = tmp_path / "projets"
    dossier.mkdir()
    externe = tmp_path / "externe.json"
    externe.write_text("{}")
    try:
        (dossier / "lien.json").symlink_to(externe)
    except OSError:
        pytest.skip("Création de liens non autorisée")
    with TestClient(serveur.creer_app(dossier)) as client:
        assert client.get("/api/projets").json() == []
        assert client.post("/api/projets/lien", json={"x": 1}).status_code == 400
        assert client.get("/api/projets/lien").status_code == 400
    assert externe.read_text() == "{}"


def test_echec_remplacement_atomique(tmp_path, monkeypatch):
    dossier = tmp_path / "projets"
    with TestClient(serveur.creer_app(dossier), raise_server_exceptions=False) as client:
        assert client.post("/api/projets/Scan", json={"original": True}).status_code == 200
        def refuser_remplacement(*args):
            raise OSError("Remplacement indisponible")
        monkeypatch.setattr(serveur.os, "replace", refuser_remplacement)
        assert client.post("/api/projets/Scan", json={"original": False}).status_code == 500
        assert client.get("/api/projets/Scan").json() == {"original": True}
        assert not list(dossier.glob("*.tmp"))
