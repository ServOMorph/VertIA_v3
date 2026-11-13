"""Contrôle avant push : refuse poids, fichiers lourds, .env et secrets dans les objets à pousser.

Usage : python pre_push_check.py [repo] [--audit]
  sans --audit : objets du HEAD absents de l'upstream (ou tout HEAD sans upstream)
  --audit      : tout l'historique (toutes les références)
Liste blanche : fichier .pre_push_allow à la racine du dépôt (un motif fnmatch par ligne).
Code de sortie : 0 aucun blocage, 1 blocage, 2 erreur git.
"""
import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

TAILLE_MAX = 50 * 1024 * 1024
SCAN_MAX = 2 * 1024 * 1024
EXTENSIONS = {".pt", ".ckpt", ".safetensors", ".gguf", ".bin", ".pth", ".onnx", ".mp4", ".wav"}
SECRETS = [
    ("cle_privee", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")),
    ("github_token", re.compile(rb"ghp_[A-Za-z0-9]{36}")),
    ("github_pat", re.compile(rb"github_pat_[A-Za-z0-9_]{50,}")),
    ("cle_sk", re.compile(rb"sk-[A-Za-z0-9_\-]{32,}")),
    ("aws", re.compile(rb"AKIA[0-9A-Z]{16}")),
    ("huggingface", re.compile(rb"hf_[A-Za-z0-9]{34,}")),
    ("slack", re.compile(rb"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("affectation_secret", re.compile(rb"(?i)(?:api[_-]?key|secret|token|passwd|password)\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']")),
]
PERSO = [
    ("chemin_utilisateur", re.compile(rb"[A-Za-z]:\\Users\\[^\\\s\"']+")),
    ("email_perso", re.compile(rb"[\w.+-]+@(?:gmail|outlook|hotmail|yahoo|orange|free)\.[a-z]+")),
]


def git(repo, *args, entree=None, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], input=entree, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="replace").strip())
    return r


def objets(repo, audit):
    if audit:
        spec = ["--all"]
    else:
        up = git(repo, "rev-parse", "--abbrev-ref", "@{upstream}", check=False)
        spec = ["HEAD"] if up.returncode != 0 else ["HEAD", "^" + up.stdout.decode().strip()]
    sortie = git(repo, "rev-list", "--objects", *spec).stdout.decode(errors="replace")
    resultat = {}
    for ligne in sortie.splitlines():
        sha, _, chemin = ligne.partition(" ")
        if chemin and sha not in resultat:
            resultat[sha] = chemin
    return resultat


def types_tailles(repo, shas):
    entree = ("\n".join(shas) + "\n").encode()
    sortie = git(repo, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)", entree=entree).stdout
    info = {}
    for ligne in sortie.decode().splitlines():
        parts = ligne.split()
        if len(parts) == 3 and parts[1] == "blob":
            info[parts[0]] = int(parts[2])
    return info


def lire_blobs(repo, shas):
    proc = subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for sha in shas:
        proc.stdin.write(sha.encode() + b"\n")
        proc.stdin.flush()
        entete = proc.stdout.readline().split()
        taille = int(entete[2])
        donnees = proc.stdout.read(taille)
        proc.stdout.read(1)
        yield sha, donnees
    proc.stdin.close()
    proc.wait()


def liste_blanche(repo):
    f = Path(repo) / ".pre_push_allow"
    if not f.exists():
        return []
    return [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]


def autorise(chemin, motifs):
    return any(fnmatch.fnmatch(chemin, m) for m in motifs)


def visibilite(repo):
    try:
        r = subprocess.run(["gh", "repo", "view", "--json", "visibility", "-q", ".visibility"],
                           cwd=repo, capture_output=True, text=True, timeout=15)
        return r.stdout.strip() or "inconnue"
    except (OSError, subprocess.SubprocessError):
        return "inconnue"


def controler(repo, audit=False):
    objs = objets(repo, audit)
    infos = types_tailles(repo, list(objs)) if objs else {}
    motifs = liste_blanche(repo)
    blocages, avertissements = [], []
    a_scanner = []
    for sha, taille in infos.items():
        chemin = objs[sha]
        if autorise(chemin, motifs):
            continue
        nom = chemin.rsplit("/", 1)[-1]
        ext = Path(nom).suffix.lower()
        if taille > TAILLE_MAX:
            blocages.append(f"{chemin}: fichier > 50 Mo ({taille // (1024 * 1024)} Mo)")
        if ext in EXTENSIONS:
            blocages.append(f"{chemin}: extension interdite {ext}")
        if nom == ".env" or (nom.startswith(".env.") and nom != ".env.example"):
            blocages.append(f"{chemin}: fichier d'environnement")
        if taille <= SCAN_MAX and ext not in EXTENSIONS:
            a_scanner.append(sha)
    for sha, donnees in lire_blobs(repo, a_scanner):
        chemin = objs[sha]
        if b"\0" in donnees[:8000]:
            continue
        for nom, rx in SECRETS:
            if rx.search(donnees):
                blocages.append(f"{chemin}: motif de secret ({nom})")
        for nom, rx in PERSO:
            if rx.search(donnees):
                avertissements.append(f"{chemin}: donnee personnelle ({nom})")
    return blocages, avertissements


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("repo", nargs="?", default=".")
    p.add_argument("--audit", action="store_true")
    a = p.parse_args(argv)
    repo = Path(a.repo).resolve()
    try:
        blocages, avertissements = controler(repo, a.audit)
    except RuntimeError as e:
        print(f"ERREUR_GIT {e}")
        return 2
    print(f"Visibilite du depot : {visibilite(repo)}")
    for l in avertissements[:50]:
        print("AVERTISSEMENT", l)
    for l in blocages[:50]:
        print("BLOCAGE", l)
    if blocages:
        print(f"REFUSE {len(blocages)} blocage(s)")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
