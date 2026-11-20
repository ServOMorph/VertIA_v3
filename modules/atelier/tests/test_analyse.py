import base64
from io import BytesIO
import json
import time

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from modules.atelier import serveur


RESULTAT = {"reponse": "Éclaircir le ciel", "propositions": [], "taille": [4, 3]}


@pytest.fixture
def analyse(tmp_path, monkeypatch):
    script = tmp_path / "faux_vertia_gen.py"
    inbox = tmp_path / "inbox"
    cible = tmp_path / "outbox/resultat.json"
    cible.parent.mkdir()
    cible.write_text(json.dumps(RESULTAT), encoding="utf-8")
    script.write_text(
        "import pathlib, sys, json\n"
        "p = pathlib.Path(__file__).parent\n"
        '(p / "arguments.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")\n'
        'print("outbox/resultat.json")\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ATELIER_INBOX", str(inbox))
    monkeypatch.setenv("ATELIER_VERTIA_GEN", str(script))
    with TestClient(serveur.creer_app(tmp_path / "projets", racine_retouche=tmp_path)) as client:
        yield client, script, inbox, cible


def donnees(**extras):
    flux = BytesIO()
    Image.new("RGB", (4, 3), "white").save(flux, format="PNG")
    return {"image": "data:image/png;base64," + base64.b64encode(flux.getvalue()).decode(),
            "prompt": "Que proposes-tu ?", **extras}


def demarrer(client, **extras):
    reponse = client.post("/api/analyse", json=donnees(**extras))
    assert reponse.status_code == 200, reponse.text
    return "/api/analyse/" + reponse.json()["id"]


def attendre(client, url, etats_transitoires=("attente", "en_cours")):
    limite = time.monotonic() + 10
    while time.monotonic() < limite:
        etat = client.get(url).json()
        if etat["etat"] not in etats_transitoires:
            return etat
        time.sleep(.01)
    pytest.fail("État de l’analyse inchangé")


@pytest.mark.parametrize("historique", [
    [{"role": "assistant", "contenu": 'Déjà prévu : "le ciel"'}],
    [{"role": "assistant", "contenu": "é" * 8000}] * 20,
])
def test_succes_et_arguments(analyse, tmp_path, historique):
    client, _, inbox, _ = analyse
    url = demarrer(client, historique=historique)
    assert attendre(client, url) == {"etat": "termine", "message": "Terminé"}
    resultat = client.get(f"{url}/resultat")
    assert resultat.headers["content-type"] == "application/json"
    assert resultat.json() == RESULTAT
    identifiant = url.rsplit("/", 1)[-1]
    args = json.loads((tmp_path / "arguments.json").read_text(encoding="utf-8"))
    assert args[:8] == ["image.analyser", "--session", "vertia", "--prompt", "Que proposes-tu ?",
                        "--param", f"source=atelier_{identifiant}_analyse.png", "--param"]
    assert json.loads(args[8].removeprefix("historique=")) == historique
    assert args[9:] == ["--timeout", "1700"]
    assert list(inbox.iterdir()) == []
    assert client.get(f"/api/retouche/{identifiant}").status_code == 404
    assert client.delete(url).json()["etat"] == "termine"


@pytest.mark.parametrize("contenu", [b"{", b"[]", b'{"zone":NaN}', b'{"a":"' + b"x" * (1024 * 1024) + b'"}'])
def test_resultat_invalide(analyse, contenu):
    client, _, inbox, cible = analyse
    cible.write_bytes(contenu)
    url = demarrer(client)
    assert attendre(client, url)["etat"] == "echec"
    assert client.get(f"{url}/resultat").status_code == 409
    assert list(inbox.iterdir()) == []


def test_resultat_hors_outbox_et_relecture(analyse, tmp_path):
    client, script, _, cible = analyse
    url = demarrer(client)
    assert attendre(client, url)["etat"] == "termine"
    cible.write_bytes(b"[]")
    assert client.get(f"{url}/resultat").status_code == 404
    (tmp_path / "externe.json").write_text("{}")
    script.write_text('print("externe.json")')
    assert attendre(client, demarrer(client))["etat"] == "echec"


@pytest.mark.parametrize("extras", [
    {"prompt": " "}, {"prompt": "a" * 4001}, {"image": "illisible"},
    {"historique": None}, {"historique": [{"role": "system", "contenu": ""}]},
    {"historique": [{"role": "user", "contenu": "a" * 8001}]},
    {"historique": [{"role": "user", "contenu": ""}] * 21},
])
def test_parametres_invalides(analyse, extras):
    client, _, inbox, _ = analyse
    assert client.post("/api/analyse", json=donnees(**extras)).status_code == 400
    assert not inbox.exists()


@pytest.mark.parametrize("code,message", [*serveur.ERREURS_RETOUCHE.items(), (42, "erreur interne")])
def test_codes_de_sortie(analyse, code, message):
    client, script, _, _ = analyse
    script.write_text(f"raise SystemExit({code})")
    assert attendre(client, demarrer(client)) == {"etat": "echec", "message": message}


def test_conflit_annulation_et_independance(analyse):
    client, script, inbox, _ = analyse
    script.write_text("import time\ntime.sleep(60)\n")
    url = demarrer(client)
    assert attendre(client, url, ("attente",))["etat"] == "en_cours"
    assert client.post("/api/analyse", json=donnees()).status_code == 409
    assert client.get(f"{url}/resultat").status_code == 409
    params = donnees()
    retouche = client.post("/api/retouche", json={**params, "masque": params["image"]})
    assert retouche.status_code == 200
    assert client.delete(url).json() == {"etat": "annule", "message": "Annulé"}
    assert client.delete("/api/retouche/" + retouche.json()["id"]).json()["etat"] == "annule"
    assert list(inbox.iterdir()) == []
