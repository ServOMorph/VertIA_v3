"""Vérifie qu'une tâche longue déclarée dans reprise.json repart après une pause GPU.

python verif_reprise.py <session> [--attente-max S] [--delai-pas S] [--delai-libre S]

Lancé en arrière-plan par vram_lock quand une session déclarée rend son jeton.
Tant qu'une autre session tient le GPU ou attend dans la file, on patiente.
Quand la session reprend le jeton, une ligne `step N` doit apparaître dans
state/reprise_sortie.log dans le délai --delai-pas : REPRISE_OK.
Si le GPU reste libre sans reprise pendant --delai-libre, ou si aucun pas
n'apparaît : REPRISE_KO, journalisée dans state/alertes.log, puis relance par
reprise_auto.py --apres-pause (une seule fois).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCH = Path(os.environ.get("VERTIA_ORCH_DIR", str(HERE)))
STATE = ORCH / "state"
CONFIG = HERE / "reprise.json"
SORTIE = STATE / "reprise_sortie.log"
PAS = re.compile(r"^step (\d+)")
DETACHED = 0x00000008 | 0x00000200
DELAI_RELANCE = 900.0
PAUSE_RELANCE = 10.0


def lire(nom, defaut):
    try:
        return json.loads((STATE / nom).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def journal(texte, alerte=False):
    STATE.mkdir(parents=True, exist_ok=True)
    ligne = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {texte}\n"
    for nom in ("reprise.log",) + (("alertes.log",) if alerte else ()):
        with open(STATE / nom, "a", encoding="utf-8") as f:
            f.write(ligne)


def taille_sortie():
    try:
        return SORTIE.stat().st_size
    except OSError:
        return 0


def dernier_pas(depuis):
    try:
        with open(SORTIE, "rb") as f:
            f.seek(depuis)
            texte = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    pas = [int(m.group(1)) for m in map(PAS.match, texte.splitlines()) if m]
    return pas[-1] if pas else None


def detenteur():
    lock = lire("lock.json", {})
    if lock and lock.get("expires", 0) > time.time():
        return lock.get("holder")
    return None


def file_vide():
    return not [q for q in lire("queue.json", []) if q.get("seen", q.get("ts", 0)) >= time.time() - 300]


def hold_actif():
    return bool(lire("hold.json", {}))


def relancer():
    subprocess.Popen([sys.executable, str(HERE / "reprise_auto.py"), "--apres-pause"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=DETACHED if os.name == "nt" else 0)


def verifier(session, attente_max, delai_pas, delai_libre, pause=10.0):
    debut = time.time()
    libre_depuis = None
    jeton_depuis = None
    position = taille_sortie()
    while time.time() - debut < attente_max:
        tenant = detenteur()
        if tenant == session:
            if jeton_depuis is None:
                jeton_depuis = time.time()
            pas = dernier_pas(position)
            if pas is not None:
                journal(f"REPRISE_OK {session} pas={pas} apres {round(time.time() - debut)} s")
                return 0
            if time.time() - jeton_depuis > delai_pas:
                return echec(session, f"jeton repris sans pas d'entrainement en {delai_pas} s")
            libre_depuis = None
        elif tenant is None and file_vide() and not hold_actif():
            jeton_depuis = None
            libre_depuis = libre_depuis or time.time()
            if time.time() - libre_depuis > delai_libre:
                return echec(session, f"GPU libre depuis {delai_libre} s sans reprise")
        else:
            jeton_depuis = None
            libre_depuis = None
        time.sleep(pause)
    if hold_actif():
        journal(f"VERIF_REPRISE {session} arretee : pause utilisateur active (reprise par unhold)")
        return 0
    return echec(session, f"pas de reprise en {attente_max} s")


def echec(session, motif, delai_relance=None):
    delai_relance = DELAI_RELANCE if delai_relance is None else delai_relance
    journal(f"REPRISE_KO {session} : {motif} ; relance reprise_auto", alerte=True)
    position = taille_sortie()
    relancer()
    fin = time.time() + delai_relance
    while time.time() < fin:
        pas = dernier_pas(position)
        if pas is not None:
            journal(f"REPRISE_OK_APRES_RELANCE {session} pas={pas}")
            return 1
        if hold_actif():
            journal(f"VERIF_REPRISE {session} arretee : pause utilisateur active")
            return 1
        time.sleep(PAUSE_RELANCE)
    journal(f"ESCALADE_REPRISE {session} : toujours pas d'entrainement {delai_relance:.0f} s apres la relance ; "
            "probleme majeur, solliciter l'utilisateur", alerte=True)
    return 2


def main():
    p = argparse.ArgumentParser()
    p.add_argument("session")
    p.add_argument("--attente-max", type=float, default=6 * 3600)
    p.add_argument("--delai-pas", type=float, default=600)
    p.add_argument("--delai-libre", type=float, default=300)
    a = p.parse_args()
    try:
        declarees = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        declarees = {}
    if a.session not in declarees:
        print(f"SESSION_NON_DECLAREE {a.session}")
        return 8
    return verifier(a.session, a.attente_max, a.delai_pas, a.delai_libre)


if __name__ == "__main__":
    sys.exit(main())
