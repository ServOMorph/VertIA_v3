"""Reprise automatique des tâches GPU après un redémarrage de la machine.

python reprise_auto.py [--delay S] [--dry-run] [--apres-pause]

Pour chaque session déclarée dans reprise.json : si elle détient le jeton et
qu'aucun processus ne correspond, le jeton périmé est libéré puis la commande
de reprise est relancée en arrière-plan. Aucune action si la pause utilisateur
(hold) est active. Avec --apres-pause (lancé par vram_lock unhold), une session
déclarée sans processus actif est relancée même si elle a rendu son jeton.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCH = Path(os.environ.get("VERTIA_ORCH_DIR", str(HERE)))
STATE = ORCH / "state"
CONFIG = HERE / "reprise.json"
LOCK = HERE / "vram_lock.py"
DETACHED = 0x00000008 | 0x00000200


def lire(chemin, defaut):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def journal(texte):
    STATE.mkdir(parents=True, exist_ok=True)
    with open(STATE / "reprise.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {texte}\n")


def processus_actif(motif):
    cmd = (
        "(Get-CimInstance Win32_Process | Where-Object "
        f"{{ $_.CommandLine -like '*{motif}*' -and $_.ProcessId -ne $PID }} | Measure-Object).Count"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60)
    try:
        return int(r.stdout.strip()) > 0
    except ValueError:
        return True


def liberer(session):
    return subprocess.run([sys.executable, str(LOCK), "release", session], capture_output=True, text=True).returncode


def lancer(conf):
    STATE.mkdir(parents=True, exist_ok=True)
    sortie = open(STATE / "reprise_sortie.log", "a", encoding="utf-8")
    subprocess.Popen(
        conf["cmd"], cwd=conf["cwd"], stdout=sortie, stderr=sortie, stdin=subprocess.DEVNULL, creationflags=DETACHED
    )


def reprendre(config, actif=processus_actif, liberer_fn=liberer, lancer_fn=lancer, dry_run=False, apres_pause=False):
    if (STATE / "hold.json").exists():
        journal("hold actif : aucune reprise")
        return []
    verrou = lire(STATE / "lock.json", {})
    holder = verrou.get("holder")
    relances = []
    for session, conf in config.items():
        if holder != session and not apres_pause:
            continue
        if actif(conf["match"]):
            journal(f"{session} : processus deja actif")
            continue
        motif = "jeton perime" if holder == session else "fin de pause utilisateur"
        journal(f"{session} : {motif}, reprise{' (dry-run)' if dry_run else ''}")
        if not dry_run:
            if holder == session:
                liberer_fn(session)
            lancer_fn(conf)
        relances.append(session)
    if holder and holder not in config and not any(actif(c["match"]) for c in config.values()):
        journal(f"jeton perime de {holder} sans reprise declaree")
    return relances


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--delay", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apres-pause", action="store_true")
    a = p.parse_args(argv)
    if a.delay:
        time.sleep(a.delay)
    config = lire(CONFIG, {})
    relances = reprendre(config, dry_run=a.dry_run, apres_pause=a.apres_pause)
    print("reprises :", ", ".join(relances) if relances else "aucune")
    return 0


if __name__ == "__main__":
    sys.exit(main())
