import importlib.util
import subprocess
import time
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent / "_orchestration"


def charger(nom):
    spec = importlib.util.spec_from_file_location(nom, RACINE / f"{nom}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def lock(tmp_path, monkeypatch):
    m = charger("vram_lock")
    monkeypatch.setattr(m, "ORCH_DIR", tmp_path)
    monkeypatch.setattr(m, "STATE", tmp_path / "state")
    monkeypatch.setenv("VERTIA_FAKE_VRAM_MIB", "700")
    monkeypatch.setenv("VERTIA_POLL_S", "0.05")
    monkeypatch.setattr(m, "SESSIONS", {"a", "b", "llm", "video", "x", "bas", "haut"})
    return m


def run(m, *args):
    return m.main(list(args))


def test_acquire_puis_attente_puis_release(lock, capsys):
    assert run(lock, "acquire", "a", "--gb", "6") == 0
    assert run(lock, "acquire", "b") == 2
    assert run(lock, "release", "a") == 0
    assert run(lock, "acquire", "b") == 0


def test_vram_occupee_refuse(lock, monkeypatch):
    monkeypatch.setenv("VERTIA_FAKE_VRAM_MIB", "5000")
    assert run(lock, "acquire", "a") == 4


def test_mesure_impossible_refuse(lock, monkeypatch):
    monkeypatch.setattr(lock, "vram_used_mib", lambda: None)
    assert run(lock, "acquire", "a") == 3


def test_release_vram_non_liberee(lock, monkeypatch):
    assert run(lock, "acquire", "a") == 0
    monkeypatch.setenv("VERTIA_FAKE_VRAM_MIB", "6000")
    assert run(lock, "release", "a") == 5
    assert run(lock, "acquire", "b") == 4


def test_release_refuse_si_non_detenteur(lock):
    assert run(lock, "acquire", "a") == 0
    assert run(lock, "release", "b") == 6


def test_pause_demandee_au_detenteur_long(lock):
    assert run(lock, "acquire", "llm", "--long", "--minutes", "600") == 0
    assert run(lock, "should-pause", "llm") == 1
    assert run(lock, "acquire", "video") == 2
    assert run(lock, "should-pause", "llm") == 0
    assert run(lock, "release", "llm") == 0
    assert run(lock, "should-pause", "llm") == 1
    assert run(lock, "acquire", "video") == 0


def test_demande_longue_prioritaire_met_le_detenteur_en_pause(lock):
    assert run(lock, "acquire", "llm", "--long", "--minutes", "600", "--priority", "9") == 0
    assert run(lock, "acquire", "video", "--long", "--non-interruptible", "--priority", "2") == 2
    assert run(lock, "should-pause", "llm") == 0
    assert run(lock, "release", "llm") == 0
    assert run(lock, "acquire", "video", "--long", "--non-interruptible", "--priority", "2") == 0


def test_demande_longue_non_prioritaire_ne_met_pas_en_pause(lock):
    assert run(lock, "acquire", "llm", "--long", "--minutes", "600", "--priority", "2") == 0
    assert run(lock, "acquire", "video", "--long", "--priority", "5") == 2
    assert run(lock, "should-pause", "llm") == 1
    assert run(lock, "acquire", "x", "--long", "--priority", "2") == 2
    assert run(lock, "should-pause", "llm") == 1


def test_jeton_ancien_sans_priorite_traite_comme_tache_longue(lock):
    import json
    assert run(lock, "acquire", "llm", "--long", "--minutes", "600") == 0
    chemin = lock.STATE / "lock.json"
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    donnees.pop("priority")
    chemin.write_text(json.dumps(donnees), encoding="utf-8")
    assert run(lock, "acquire", "video", "--long", "--priority", "5") == 2
    assert run(lock, "should-pause", "llm") == 0


def test_pas_de_pause_si_detenteur_non_interruptible(lock):
    assert run(lock, "acquire", "video", "--non-interruptible") == 0
    assert run(lock, "acquire", "x") == 2
    assert run(lock, "should-pause", "video") == 1


def test_priorite_ordonne_la_file(lock):
    assert run(lock, "acquire", "a") == 0
    assert run(lock, "acquire", "bas", "--priority", "9") == 2
    assert run(lock, "acquire", "haut", "--priority", "1") == 2
    assert run(lock, "release", "a") == 0
    assert run(lock, "acquire", "bas", "--priority", "9") == 2
    assert run(lock, "acquire", "haut", "--priority", "1") == 0


def test_duree_plafonnee(lock):
    assert run(lock, "acquire", "a", "--minutes", "999") == 0
    verrou = lock.read_json("lock.json", None)
    assert verrou["expires"] - verrou["started"] <= 45 * 60 + 1
    assert run(lock, "release", "a") == 0
    assert run(lock, "acquire", "b", "--long", "--minutes", "999") == 0
    verrou = lock.read_json("lock.json", None)
    assert verrou["expires"] - verrou["started"] > 45 * 60


def test_verrou_expire_repris_si_vram_libre(lock):
    assert run(lock, "acquire", "a") == 0
    verrou = lock.read_json("lock.json", None)
    verrou["expires"] = time.time() - 1
    lock.write_json("lock.json", verrou)
    assert run(lock, "acquire", "b") == 0


def test_verrou_expire_non_repris_si_vram_occupee(lock, monkeypatch):
    assert run(lock, "acquire", "a") == 0
    verrou = lock.read_json("lock.json", None)
    verrou["expires"] = time.time() - 1
    lock.write_json("lock.json", verrou)
    monkeypatch.setenv("VERTIA_FAKE_VRAM_MIB", "6500")
    assert run(lock, "acquire", "b") == 4


def test_baseline_et_status(lock, tmp_path, monkeypatch):
    monkeypatch.setenv("VERTIA_FAKE_VRAM_MIB", "1500")
    assert run(lock, "baseline", "--marge", "500") == 0
    assert run(lock, "acquire", "a") == 0
    assert run(lock, "release", "a") == 0
    monkeypatch.setenv("VERTIA_FAKE_VRAM_MIB", "2100")
    assert run(lock, "acquire", "a") == 4
    assert run(lock, "status", "--write") == 0
    assert "Detenteur : personne" in (tmp_path / "etat.md").read_text(encoding="utf-8")


def test_session_inconnue_refusee(lock):
    assert run(lock, "acquire", "inconnue") == 8


def test_nom_insensible_a_la_casse(lock):
    assert run(lock, "acquire", "A") == 0
    assert run(lock, "release", "a") == 0


def test_tete_de_file_absente_expire(lock, monkeypatch):
    assert run(lock, "acquire", "a") == 0
    assert run(lock, "acquire", "b") == 2
    assert run(lock, "release", "a") == 0
    assert run(lock, "acquire", "x") == 2
    monkeypatch.setattr(lock, "FILE_TTL_S", 0)
    time.sleep(0.01)
    assert run(lock, "acquire", "x") == 0


def test_ordre_d_arrivee_conserve_au_rappel(lock):
    assert run(lock, "acquire", "a") == 0
    assert run(lock, "acquire", "b") == 2
    assert run(lock, "acquire", "x") == 2
    assert run(lock, "acquire", "b") == 2
    assert run(lock, "release", "a") == 0
    assert run(lock, "acquire", "x") == 2
    assert run(lock, "acquire", "b") == 0


def test_wait_obtient_le_jeton_apres_liberation(lock):
    import threading
    assert run(lock, "acquire", "a") == 0
    threading.Timer(0.3, lambda: lock.main(["release", "a"])).start()
    assert run(lock, "acquire", "b", "--wait", "--timeout", "0.1") == 0


def test_wait_expire(lock):
    assert run(lock, "acquire", "a") == 0
    assert run(lock, "acquire", "b", "--wait", "--timeout", "0.003") == 2


def test_pause_utilisateur(lock):
    assert run(lock, "acquire", "llm", "--long") == 0
    assert run(lock, "hold") == 0
    assert run(lock, "should-pause", "llm") == 0
    assert run(lock, "release", "llm") == 0
    assert run(lock, "acquire", "llm", "--long") == 7
    assert run(lock, "unhold") == 0
    assert run(lock, "should-pause", "llm") == 1
    assert run(lock, "acquire", "llm", "--long") == 0


def test_urgences_ordonnent_la_file(lock):
    assert run(lock, "urgences", "haut", "bas") == 0
    assert run(lock, "acquire", "a") == 0
    assert run(lock, "acquire", "bas", "--priority", "1") == 2
    assert run(lock, "acquire", "haut", "--priority", "9") == 2
    assert run(lock, "release", "a") == 0
    assert run(lock, "acquire", "bas", "--priority", "1") == 2
    assert run(lock, "acquire", "haut", "--priority", "9") == 0


def test_urgences_pause_et_reset(lock):
    assert run(lock, "urgences", "video", "llm") == 0
    assert run(lock, "acquire", "llm", "--long", "--priority", "9") == 0
    assert run(lock, "acquire", "video", "--long", "--priority", "9") == 2
    assert run(lock, "should-pause", "llm") == 0
    assert run(lock, "urgences", "inconnue") == 8
    assert run(lock, "urgences", "--reset") == 0
    assert lock.ordre_urgences() == []


@pytest.fixture
def depot(tmp_path):
    d = tmp_path / "depot"
    d.mkdir()
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(d), "config", "user.email", "t@example.org"], check=True)
    subprocess.run(["git", "-C", str(d), "config", "user.name", "t"], check=True)
    return d


def commiter(d, fichiers):
    for nom, contenu in fichiers.items():
        p = d / nom
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(contenu if isinstance(contenu, bytes) else contenu.encode())
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(d), "commit", "-q", "-m", "c"], check=True)


def test_push_propre_accepte(depot):
    m = charger("pre_push_check")
    commiter(depot, {"a.py": "print(1)\n", "README.md": "texte"})
    assert m.controler(depot) == ([], [])


def test_push_refuse_poids_env_et_secret(depot):
    m = charger("pre_push_check")
    jeton = "ghp_" + "a" * 36
    commiter(depot, {"w/model.safetensors": b"x", ".env": "A=1", "src/c.py": f'T = "{jeton}"\n'})
    blocages, _ = m.controler(depot)
    texte = "\n".join(blocages)
    assert "extension interdite" in texte
    assert "fichier d'environnement" in texte
    assert "github_token" in texte
    assert jeton not in texte


def test_env_example_autorise(depot):
    m = charger("pre_push_check")
    commiter(depot, {".env.example": "A=\n"})
    assert m.controler(depot)[0] == []


def test_liste_blanche(depot):
    m = charger("pre_push_check")
    commiter(depot, {"data/ref.onnx": b"x", ".pre_push_allow": "data/*.onnx\n"})
    assert m.controler(depot)[0] == []


def test_avertissement_donnee_personnelle_non_bloquant(depot):
    m = charger("pre_push_check")
    commiter(depot, {"n.md": "chemin C:\\Users\\jean\\x et jean@gmail.com"})
    blocages, avert = m.controler(depot)
    assert blocages == []
    assert len(avert) == 2


def test_audit_detecte_fichier_supprime_de_l_historique(depot):
    m = charger("pre_push_check")
    commiter(depot, {"w.ckpt": b"x"})
    subprocess.run(["git", "-C", str(depot), "rm", "-q", "w.ckpt"], check=True)
    subprocess.run(["git", "-C", str(depot), "commit", "-q", "-m", "rm"], check=True)
    assert m.controler(depot, audit=True)[0] != []


def test_taille_max(depot, monkeypatch):
    m = charger("pre_push_check")
    monkeypatch.setattr(m, "TAILLE_MAX", 10)
    commiter(depot, {"gros.txt": "x" * 100})
    assert "50 Mo" in m.controler(depot)[0][0]
