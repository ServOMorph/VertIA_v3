import importlib.util
import json
import time
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent / "_orchestration"


@pytest.fixture
def verif(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("verif_reprise", RACINE / "verif_reprise.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(m, "STATE", state)
    monkeypatch.setattr(m, "SORTIE", state / "reprise_sortie.log")
    relances = []
    monkeypatch.setattr(m, "relancer", lambda: relances.append(1))
    m.relances = relances
    monkeypatch.setattr(m, "DELAI_RELANCE", 0.1)
    monkeypatch.setattr(m, "PAUSE_RELANCE", 0.01)
    return m


def ecrire(m, nom, valeur):
    (m.STATE / nom).write_text(json.dumps(valeur), encoding="utf-8")


def test_reprise_ok_quand_un_pas_apparait(verif, monkeypatch):
    verif.SORTIE.write_text("step 10 train\npause au pas 12 : pause_demandee\n", encoding="utf-8")
    ecrire(verif, "lock.json", {"holder": "llm", "expires": time.time() + 600})
    sommeil = lambda s: verif.SORTIE.open("a", encoding="utf-8").write("step 13 train\n")
    monkeypatch.setattr(verif.time, "sleep", sommeil)
    assert verif.verifier("llm", 30, 5, 5, pause=0) == 0
    assert "REPRISE_OK llm pas=13" in (verif.STATE / "reprise.log").read_text(encoding="utf-8")
    assert not verif.relances


def test_ancien_pas_ne_compte_pas_et_ko_sans_pas(verif):
    verif.SORTIE.write_text("step 10 train\n", encoding="utf-8")
    ecrire(verif, "lock.json", {"holder": "llm", "expires": time.time() + 600})
    assert verif.verifier("llm", 5, 0.05, 5, pause=0.01) == 2
    assert "REPRISE_KO llm" in (verif.STATE / "alertes.log").read_text(encoding="utf-8")
    assert verif.relances == [1]


def test_gpu_libre_sans_reprise_donne_ko(verif):
    ecrire(verif, "queue.json", [])
    assert verif.verifier("llm", 5, 5, 0.05, pause=0.01) == 2
    assert "GPU libre" in (verif.STATE / "alertes.log").read_text(encoding="utf-8")


def test_attend_tant_qu_une_autre_session_travaille(verif):
    ecrire(verif, "lock.json", {"holder": "shorts", "expires": time.time() + 600})
    assert verif.verifier("llm", 0.2, 0.05, 0.05, pause=0.01) == 2
    assert "pas de reprise en" in (verif.STATE / "alertes.log").read_text(encoding="utf-8")


def test_hold_utilisateur_suspend_le_controle_gpu_libre(verif):
    ecrire(verif, "hold.json", {"since": "x"})
    assert verif.verifier("llm", 0.2, 0.05, 0.05, pause=0.01) == 0
    assert "pause utilisateur active" in (verif.STATE / "reprise.log").read_text(encoding="utf-8")
    assert not (verif.STATE / "alertes.log").exists() and not verif.relances


def test_echec_persistant_apres_relance_donne_escalade(verif):
    verif.SORTIE.write_text("step 10 train\n", encoding="utf-8")
    ecrire(verif, "lock.json", {"holder": "llm", "expires": time.time() + 600})
    assert verif.verifier("llm", 5, 0.05, 5, pause=0.01) == 2
    alertes = (verif.STATE / "alertes.log").read_text(encoding="utf-8")
    assert "REPRISE_KO llm" in alertes and "ESCALADE_REPRISE llm" in alertes


def test_relance_reussie_n_escalade_pas(verif, monkeypatch):
    verif.SORTIE.write_text("step 10 train\n", encoding="utf-8")
    ecrire(verif, "lock.json", {"holder": "llm", "expires": time.time() + 600})
    monkeypatch.setattr(verif, "relancer", lambda: verif.SORTIE.open("a", encoding="utf-8").write("step 11 train\n"))
    assert verif.verifier("llm", 5, 0.05, 5, pause=0.01) == 1
    assert "REPRISE_OK_APRES_RELANCE llm pas=11" in (verif.STATE / "reprise.log").read_text(encoding="utf-8")
    assert "ESCALADE_REPRISE" not in (verif.STATE / "alertes.log").read_text(encoding="utf-8")
