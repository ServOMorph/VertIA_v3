import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "reprise_auto", Path(__file__).resolve().parent.parent / "_orchestration" / "reprise_auto.py"
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

CONF = {"creation_llm": {"cwd": "x", "cmd": ["y"], "match": "run_369m.py"}}


def preparer(tmp_path, monkeypatch, holder=None, hold=False):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(mod, "STATE", state)
    if holder:
        (state / "lock.json").write_text(json.dumps({"holder": holder}), encoding="utf-8")
    if hold:
        (state / "hold.json").write_text("{}", encoding="utf-8")


def appels():
    liste = []
    return liste, (lambda s: liste.append(("liberer", s)) or 0), (lambda c: liste.append(("lancer", c["match"])))


def test_reprise_si_processus_absent(tmp_path, monkeypatch):
    preparer(tmp_path, monkeypatch, holder="creation_llm")
    liste, lib, lan = appels()
    r = mod.reprendre(CONF, actif=lambda m: False, liberer_fn=lib, lancer_fn=lan)
    assert r == ["creation_llm"]
    assert liste == [("liberer", "creation_llm"), ("lancer", "run_369m.py")]


def test_rien_si_processus_actif(tmp_path, monkeypatch):
    preparer(tmp_path, monkeypatch, holder="creation_llm")
    liste, lib, lan = appels()
    assert mod.reprendre(CONF, actif=lambda m: True, liberer_fn=lib, lancer_fn=lan) == []
    assert liste == []


def test_rien_si_autre_detenteur_ou_vide(tmp_path, monkeypatch):
    preparer(tmp_path, monkeypatch, holder="creation_videos")
    liste, lib, lan = appels()
    assert mod.reprendre(CONF, actif=lambda m: False, liberer_fn=lib, lancer_fn=lan) == []
    assert liste == []


def test_rien_si_hold(tmp_path, monkeypatch):
    preparer(tmp_path, monkeypatch, holder="creation_llm", hold=True)
    liste, lib, lan = appels()
    assert mod.reprendre(CONF, actif=lambda m: False, liberer_fn=lib, lancer_fn=lan) == []
    assert liste == []


def test_dry_run(tmp_path, monkeypatch):
    preparer(tmp_path, monkeypatch, holder="creation_llm")
    liste, lib, lan = appels()
    r = mod.reprendre(CONF, actif=lambda m: False, liberer_fn=lib, lancer_fn=lan, dry_run=True)
    assert r == ["creation_llm"] and liste == []


def test_apres_pause_relance_sans_jeton(tmp_path, monkeypatch):
    preparer(tmp_path, monkeypatch)
    liste, lib, lan = appels()
    assert mod.reprendre(CONF, actif=lambda m: False, liberer_fn=lib, lancer_fn=lan, apres_pause=True) == ["creation_llm"]
    assert liste == [("lancer", "run_369m.py")]


def test_apres_pause_rien_si_processus_actif(tmp_path, monkeypatch):
    preparer(tmp_path, monkeypatch, holder="creation_videos")
    liste, lib, lan = appels()
    assert mod.reprendre(CONF, actif=lambda m: True, liberer_fn=lib, lancer_fn=lan, apres_pause=True) == []
    assert liste == []
