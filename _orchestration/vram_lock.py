"""Verrou VRAM unique pour les sessions orchestrées par VertIA.

Codes de sortie : 0 ok, 2 attendre (file), 3 mesure VRAM impossible,
4 VRAM occupée hors jeton, 5 VRAM non libérée après release, 6 refus (pas détenteur),
7 pause utilisateur en cours, 8 nom de session inconnu.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ORCH_DIR = Path(os.environ.get("VERTIA_ORCH_DIR", Path(__file__).resolve().parent))
STATE = ORCH_DIR / "state"
SESSIONS = {"creation_3d", "worldmodel", "creation_llm", "creation_videos", "vertia", "vibeobs", "securite", "xmage", "site_internet_v3", "moulin_du_sud", "agent_trader_f8"}
MARGE_DEFAUT_MIB = 1000
BASELINE_DEFAUT_MIB = 1200
DUREE_MAX_MIN = 45
DUREE_MAX_LONGUE_MIN = 1440
FILE_TTL_S = 300
PRIORITE_TACHE_LONGUE = 9
ATTENTE_CODES = {2, 3, 4, 7}


def now():
    return time.time()


def iso(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def vram_used_mib():
    fake = os.environ.get("VERTIA_FAKE_VRAM_MIB")
    if fake is not None:
        return int(fake)
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        return int(out.stdout.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


class Mutex:
    def __init__(self):
        STATE.mkdir(parents=True, exist_ok=True)
        self.path = STATE / ".mutex"

    def __enter__(self):
        debut = now()
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if now() - self.path.stat().st_mtime > 30:
                        self.path.unlink()
                        continue
                except OSError:
                    pass
                if now() - debut > 10:
                    raise TimeoutError("mutex indisponible")
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except OSError:
            pass


def read_json(name, defaut):
    p = STATE / name
    if not p.exists():
        return defaut
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def write_json(name, data):
    p = STATE / name
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def supprimer(p):
    try:
        p.unlink()
    except OSError:
        pass


def journal(msg):
    STATE.mkdir(parents=True, exist_ok=True)
    with open(STATE / "journal.log", "a", encoding="utf-8") as f:
        f.write(f"{iso(now())} {msg}\n")


def tracer_refus(session, code, detail):
    derniers = read_json("derniers_refus.json", {})
    if derniers.get(session) != code:
        derniers[session] = code
        write_json("derniers_refus.json", derniers)
        journal(f"REFUS code={code} session={session} {detail}")


def oublier_refus(session):
    derniers = read_json("derniers_refus.json", {})
    if session in derniers:
        del derniers[session]
        write_json("derniers_refus.json", derniers)


def pause_flag(session):
    return STATE / f"pause_{session}.flag"


def pause_utilisateur():
    return (STATE / "hold.json").exists()


def baseline_mib():
    return read_json("baseline.json", {}).get("mib", BASELINE_DEFAUT_MIB)


def marge_mib():
    return read_json("baseline.json", {}).get("marge", MARGE_DEFAUT_MIB)


def seuil_libre_mib():
    return baseline_mib() + marge_mib()


def bornes_duree(minutes, longue):
    plafond = DUREE_MAX_LONGUE_MIN if longue else DUREE_MAX_MIN
    return max(1, min(minutes, plafond))


def ordre_urgences():
    return read_json("urgences.json", {}).get("ordre", [])


def priorite(session, defaut):
    ordre = ordre_urgences()
    return ordre.index(session) + 1 if session in ordre else defaut


def file_triee(queue):
    return sorted(queue, key=lambda q: (priorite(q["session"], q["priority"]), q["ts"]))


def file_vivante(queue):
    limite = now() - FILE_TTL_S
    return [q for q in queue if q.get("seen", q["ts"]) >= limite]


def nom_valide(session):
    s = session.lower()
    if s not in SESSIONS:
        print(f"SESSION_INCONNUE {session} (autorisees : {', '.join(sorted(SESSIONS))})")
        return None
    return s


def tenter(a, session):
    with Mutex():
        lock = read_json("lock.json", None)
        queue = file_vivante(read_json("queue.json", []))
        if lock and lock["holder"] == session and lock["expires"] > now():
            print(f"DEJA_DETENU jusqu'a {iso(lock['expires'])}")
            return 0
        actif = lock is not None and lock["expires"] > now()
        ancien = next((q for q in queue if q["session"] == session), None)
        queue = [q for q in queue if q["session"] != session]
        demande = {
            "session": session, "gb": a.gb, "minutes": a.minutes, "long": a.long,
            "interruptible": not a.non_interruptible, "priority": a.priority,
            "ts": ancien["ts"] if ancien else now(), "seen": now(),
        }
        a.priority = priorite(session, a.priority)
        demande["priority"] = a.priority
        queue_triee = file_triee(queue + [demande])
        rang = [q["session"] for q in queue_triee].index(session)
        if pause_utilisateur():
            write_json("queue.json", queue_triee)
            tracer_refus(session, 7, "pause utilisateur")
            print("PAUSE_UTILISATEUR")
            return 7
        if actif or rang > 0:
            write_json("queue.json", queue_triee)
            if actif and lock.get("long") and lock.get("interruptible") and (
                not a.long or a.priority < priorite(lock["holder"], lock.get("priority", PRIORITE_TACHE_LONGUE))
            ):
                if not pause_flag(lock["holder"]).exists():
                    pause_flag(lock["holder"]).write_text(f"demande de {session}\n", encoding="utf-8")
                    journal(f"PAUSE_DEMANDEE holder={lock['holder']} par={session}")
            detenteur = lock["holder"] if actif else queue_triee[0]["session"]
            tracer_refus(session, 2, f"rang={rang + 1} detenteur_ou_tete={detenteur}")
            print(f"ATTENDRE rang={rang + 1} detenteur_ou_tete={detenteur}")
            return 2
        used = vram_used_mib()
        if used is None:
            write_json("queue.json", queue_triee)
            tracer_refus(session, 3, "mesure vram impossible")
            print("MESURE_VRAM_IMPOSSIBLE")
            return 3
        if used > seuil_libre_mib():
            write_json("queue.json", queue_triee)
            tracer_refus(session, 4, f"used={used} seuil={seuil_libre_mib()}")
            print(f"VRAM_OCCUPEE used={used}MiB seuil={seuil_libre_mib()}MiB")
            return 4
        minutes = bornes_duree(a.minutes, a.long)
        lock = {
            "holder": session, "gb": a.gb, "long": a.long, "priority": a.priority,
            "interruptible": not a.non_interruptible, "started": now(),
            "expires": now() + minutes * 60,
        }
        write_json("lock.json", lock)
        write_json("queue.json", queue)
        supprimer(pause_flag(session))
        oublier_refus(session)
        journal(f"JETON session={session} gb={a.gb} min={minutes} long={a.long} used={used}")
        print(f"JETON jusqu'a {iso(lock['expires'])}")
        return 0


def cmd_acquire(a):
    session = nom_valide(a.session)
    if session is None:
        journal(f"REFUS code=8 session={a.session} nom inconnu")
        return 8
    if not a.wait:
        return tenter(a, session)
    fin = now() + a.timeout * 60
    intervalle = float(os.environ.get("VERTIA_POLL_S", "20"))
    while True:
        code = tenter(a, session)
        if code not in ATTENTE_CODES or now() >= fin:
            if code in ATTENTE_CODES:
                journal(f"ATTENTE_EXPIREE session={session} code={code}")
                print(f"ATTENTE_EXPIREE code={code}")
            return code
        time.sleep(intervalle)


def cmd_release(a):
    session = nom_valide(a.session)
    if session is None:
        return 8
    with Mutex():
        lock = read_json("lock.json", None)
        if not lock or lock["holder"] != session:
            print("REFUS pas detenteur")
            return 6
        supprimer(STATE / "lock.json")
        supprimer(pause_flag(session))
        used = vram_used_mib()
        journal(f"LIBERE session={session} used={used}")
        if used is None or used > seuil_libre_mib():
            print(f"LIBERE_MAIS_VRAM_NON_LIBEREE used={used}MiB seuil={seuil_libre_mib()}MiB")
            return 5
        print(f"LIBERE used={used}MiB")
        return 0


def cmd_extend(a):
    session = nom_valide(a.session)
    if session is None:
        return 8
    with Mutex():
        lock = read_json("lock.json", None)
        if not lock or lock["holder"] != session:
            print("REFUS pas detenteur")
            return 6
        minutes = bornes_duree(a.minutes, lock.get("long", False))
        lock["expires"] = max(lock["expires"], now()) + minutes * 60
        write_json("lock.json", lock)
        journal(f"PROLONGE session={session} min={minutes}")
        print(f"PROLONGE jusqu'a {iso(lock['expires'])}")
        return 0


def cmd_cancel(a):
    session = nom_valide(a.session)
    if session is None:
        return 8
    with Mutex():
        queue = [q for q in read_json("queue.json", []) if q["session"] != session]
        write_json("queue.json", queue)
        print("ANNULE")
        return 0


def cmd_should_pause(a):
    session = nom_valide(a.session)
    if session is None:
        return 8
    if pause_utilisateur() or pause_flag(session).exists():
        print("PAUSE")
        return 0
    return 1


def cmd_hold(a):
    with Mutex():
        write_json("hold.json", {"since": iso(now())})
        journal("PAUSE_UTILISATEUR debut")
    print("PAUSE_UTILISATEUR activee : aucun nouveau jeton, tache longue en cours invitee a se mettre en pause")
    return 0


def cmd_unhold(a):
    with Mutex():
        supprimer(STATE / "hold.json")
        journal("PAUSE_UTILISATEUR fin")
    print("PAUSE_UTILISATEUR levee")
    return 0


def cmd_urgences(a):
    if a.reset:
        with Mutex():
            supprimer(STATE / "urgences.json")
            journal("URGENCES supprimees")
        print("URGENCES supprimees : priorites demandees par les sessions")
        return 0
    if not a.sessions:
        print("URGENCES " + (" > ".join(ordre_urgences()) or "aucune"))
        return 0
    ordre = []
    for s in a.sessions:
        n = nom_valide(s)
        if n is None:
            return 8
        if n not in ordre:
            ordre.append(n)
    with Mutex():
        write_json("urgences.json", {"ordre": ordre, "date": iso(now())})
        journal("URGENCES " + " > ".join(ordre))
    print("URGENCES " + " > ".join(ordre))
    return 0


def cmd_baseline(a):
    used = vram_used_mib()
    if used is None:
        print("MESURE_VRAM_IMPOSSIBLE")
        return 3
    with Mutex():
        donnees = {"mib": used, "marge": a.marge, "date": iso(now())}
        write_json("baseline.json", donnees)
        journal(f"BASELINE mib={used} marge={a.marge}")
    print(f"BASELINE {used}MiB marge {a.marge}MiB")
    return 0


def rapport():
    lock = read_json("lock.json", None)
    queue = file_triee(file_vivante(read_json("queue.json", [])))
    lignes = ["# Etat orchestration VRAM", f"MAJ {iso(now())}", ""]
    if lock:
        etat = "EXPIRE" if lock["expires"] <= now() else "actif"
        lignes.append(f"Detenteur : {lock['holder']} ({etat}, jusqu'a {iso(lock['expires'])}, long={lock['long']}, interruptible={lock['interruptible']})")
    else:
        lignes.append("Detenteur : personne")
    lignes.append("File : " + (", ".join(f"{q['session']}(p{priorite(q['session'], q['priority'])})" for q in queue) or "vide"))
    lignes.append("Urgences : " + (" > ".join(ordre_urgences()) or "aucune"))
    lignes.append(f"Pause utilisateur : {'oui' if pause_utilisateur() else 'non'}")
    lignes.append(f"VRAM utilisee : {vram_used_mib()} MiB ; base {baseline_mib()} MiB ; seuil libre {seuil_libre_mib()} MiB")
    pauses = sorted(p.name for p in STATE.glob("pause_*.flag"))
    lignes.append("Pauses demandees : " + (", ".join(pauses) or "aucune"))
    return "\n".join(lignes)


def cmd_status(a):
    STATE.mkdir(parents=True, exist_ok=True)
    texte = rapport()
    print(texte)
    if a.write:
        (ORCH_DIR / "etat.md").write_text(texte + "\n", encoding="utf-8")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="vram_lock")
    sub = p.add_subparsers(dest="cmd", required=True)
    ac = sub.add_parser("acquire")
    ac.add_argument("session")
    ac.add_argument("--gb", type=float, default=0)
    ac.add_argument("--minutes", type=int, default=DUREE_MAX_MIN)
    ac.add_argument("--long", action="store_true")
    ac.add_argument("--non-interruptible", action="store_true")
    ac.add_argument("--priority", type=int, default=5)
    ac.add_argument("--wait", action="store_true")
    ac.add_argument("--timeout", type=float, default=240)
    ac.set_defaults(fn=cmd_acquire)
    for nom, fn in (("release", cmd_release), ("cancel", cmd_cancel), ("should-pause", cmd_should_pause)):
        s = sub.add_parser(nom)
        s.add_argument("session")
        s.set_defaults(fn=fn)
    ex = sub.add_parser("extend")
    ex.add_argument("session")
    ex.add_argument("--minutes", type=int, default=DUREE_MAX_MIN)
    ex.set_defaults(fn=cmd_extend)
    bl = sub.add_parser("baseline")
    bl.add_argument("--marge", type=int, default=MARGE_DEFAUT_MIB)
    bl.set_defaults(fn=cmd_baseline)
    ur = sub.add_parser("urgences")
    ur.add_argument("sessions", nargs="*")
    ur.add_argument("--reset", action="store_true")
    ur.set_defaults(fn=cmd_urgences)
    sub.add_parser("hold").set_defaults(fn=cmd_hold)
    sub.add_parser("unhold").set_defaults(fn=cmd_unhold)
    st = sub.add_parser("status")
    st.add_argument("--write", action="store_true")
    st.set_defaults(fn=cmd_status)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
