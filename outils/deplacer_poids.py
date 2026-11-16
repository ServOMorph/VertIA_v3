"""Déplacement vérifié de dossiers de poids, simulé sauf avec --appliquer."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))

from vertia.chemins import resoudre_chemins


class Refus(Exception):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Plan:
    source: Path
    destination: Path
    fichiers: tuple[str, ...]
    dossiers: tuple[str, ...]
    taille: int
    libre: int
    destination_existante: bool


def models_dir() -> Path:
    return resoudre_chemins(ROOT).models_dir


def normaliser(chemin: str | Path) -> Path:
    chemin = Path(chemin)
    if any(segment.casefold() == 'creation_llm' for segment in chemin.parts):
        raise Refus(f'Chemin creation_llm interdit : {chemin}')
    chemin = Path(os.path.abspath(chemin))
    if any(segment.casefold() == 'creation_llm' for segment in chemin.parts):
        raise Refus(f'Chemin creation_llm interdit : {chemin}')
    return chemin


def est_lien(chemin: Path) -> bool:
    info = chemin.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def verifier_chemin(chemin: Path) -> None:
    for element in (*reversed(chemin.parents), chemin):
        if os.path.lexists(element) and est_lien(element):
            raise Refus(f'Jonction ou lien interdit : {element}')


def inventaire(racine: Path) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    """Parcourt uniquement des dossiers réels, sans suivre de reparse point."""
    verifier_chemin(racine)
    if not racine.is_dir():
        raise Refus(f'La source doit être un dossier réel existant : {racine}')
    fichiers, dossiers, taille = [], [], 0

    def visiter(dossier: Path) -> None:
        nonlocal taille
        with os.scandir(dossier) as elements:
            for element in elements:
                chemin = Path(element.path)
                if est_lien(chemin):
                    raise Refus(f'Jonction ou lien interne interdit : {chemin}')
                relatif = chemin.relative_to(racine).as_posix()
                if element.is_dir(follow_symlinks=False):
                    dossiers.append(relatif)
                    visiter(chemin)
                elif element.is_file(follow_symlinks=False):
                    fichiers.append(relatif)
                    taille += element.stat(follow_symlinks=False).st_size
                else:
                    raise Refus(f'Fichier spécial interdit : {chemin}')

    visiter(racine)
    return tuple(sorted(fichiers)), tuple(sorted(dossiers)), taille


def verifier_disponible(chemin: Path) -> None:
    if os.name != 'nt':
        raise Refus('Le contrôle exclusif et les jonctions nécessitent Windows.')
    from ctypes import wintypes

    api = ctypes.WinDLL('kernel32', use_last_error=True)
    ouvrir = api.CreateFileW
    ouvrir.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    ouvrir.restype = wintypes.HANDLE
    fermer = api.CloseHandle
    fermer.argtypes = [wintypes.HANDLE]
    fermer.restype = wintypes.BOOL
    handle = ouvrir(str(chemin), 0x80000000 | 0x40000000, 0, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise Refus(f'Fichier utilisé ou accès exclusif refusé : {chemin}')
    fermer(handle)


def verifier_espace(destination: Path, taille: int) -> int:
    existant = destination
    while not existant.exists():
        existant = existant.parent
    libre = shutil.disk_usage(existant).free
    if libre * 10 <= taille * 11:
        raise Refus(f'Espace insuffisant : {libre} octets libres, requis > {taille * 1.1:.0f}.')
    return libre


def preparer(source: str | Path, destination: str | Path) -> Plan:
    source, destination = normaliser(source), normaliser(destination)
    verifier_chemin(source)
    verifier_chemin(destination)
    if source == destination or source in destination.parents or destination in source.parents:
        raise Refus('La source et la destination ne doivent pas être imbriquées.')
    poids = normaliser(models_dir())
    if destination == poids or poids not in destination.parents:
        raise Refus(f'Le dossier de poids doit être situé sous models/ : {poids}')
    verifier_mklink(source, destination)
    fichiers, dossiers, taille = inventaire(source)
    existe = destination.exists()
    if existe and (not destination.is_dir() or any(destination.iterdir())):
        raise Refus(f'Destination non vide ou non répertoire : {destination}')
    for relatif in fichiers:
        verifier_disponible(source / relatif)
    libre = verifier_espace(destination, taille)
    return Plan(source, destination, fichiers, dossiers, taille, libre, existe)


def hacher_fichier(chemin: Path) -> str:
    verifier_chemin(chemin)
    with chemin.open('rb') as flux:
        return hashlib.file_digest(flux, 'sha256').hexdigest()


def empreinte(racine: Path) -> str:
    fichiers, dossiers, _ = inventaire(racine)
    contenu = {'dossiers': dossiers, 'fichiers': [
        (relatif, hacher_fichier(racine / relatif)) for relatif in fichiers]}
    return hashlib.sha256(json.dumps(contenu, ensure_ascii=True, sort_keys=True).encode()).hexdigest()


def comparer(source: Path, destination: Path) -> str:
    original, copie = empreinte(source), empreinte(destination)
    if original != copie:
        raise Refus('Empreintes SHA-256 différentes ; copie refusée.', 3)
    return original


def instantane(plan: Plan) -> tuple:
    resultat = []
    for relatif in plan.fichiers:
        chemin = plan.source / relatif
        verifier_chemin(chemin)
        info = chemin.stat(follow_symlinks=False)
        resultat.append((relatif, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino))
    return tuple(resultat)


def copier(plan: Plan) -> None:
    verifier_chemin(plan.source)
    verifier_chemin(plan.destination)
    plan.destination.mkdir(parents=True, exist_ok=True)
    for relatif in plan.dossiers:
        (plan.destination / relatif).mkdir(exist_ok=True)
    for relatif in plan.fichiers:
        source, destination = plan.source / relatif, plan.destination / relatif
        verifier_chemin(source)
        verifier_chemin(destination)
        shutil.copy2(source, destination)


def supprimer_arbre(chemin: Path, proprietaire: Path) -> None:
    """La racine doit être celle explicitement détenue par cette opération."""
    if chemin != proprietaire or chemin == chemin.parent:
        raise Refus(f'Suppression hors opération interdite : {chemin}')
    fichiers, dossiers, _ = inventaire(chemin)
    for relatif in fichiers:
        fichier = chemin / relatif
        verifier_chemin(fichier)
        fichier.unlink()
    for relatif in sorted(dossiers, key=lambda nom: len(Path(nom).parts), reverse=True):
        dossier = chemin / relatif
        verifier_chemin(dossier)
        dossier.rmdir()
    verifier_chemin(chemin)
    chemin.rmdir()


def nettoyer_copie(plan: Plan) -> None:
    if os.path.lexists(plan.destination):
        supprimer_arbre(plan.destination, plan.destination)
    if plan.destination_existante:
        plan.destination.mkdir()


def verifier_mklink(source: Path, destination: Path) -> None:
    if os.name != 'nt':
        raise Refus('Les jonctions nécessitent Windows.')
    # Les métacaractères cmd sont refusés, même entre guillemets (% notamment).
    if any(caractere in str(source) + str(destination) for caractere in '%!\r\n"&|<>^'):
        raise Refus('Caractère incompatible avec mklink dans le chemin.')


def creer_jonction(source: Path, destination: Path) -> None:
    verifier_mklink(source, destination)
    resultat = subprocess.run(
        ['cmd.exe', '/d', '/c', 'mklink', '/J', str(source), str(destination)],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if resultat.returncode:
        raise OSError(f'mklink a échoué : {resultat.stderr.strip() or resultat.stdout.strip()}')
    verifier_jonction(source, destination)


def verifier_jonction(source: Path, destination: Path) -> None:
    # IO_REPARSE_TAG_MOUNT_POINT distingue une jonction d'un lien symbolique.
    if (not os.path.lexists(source) or not est_lien(source)
            or getattr(source.lstat(), 'st_reparse_tag', 0) != 0xA0000003
            or source.resolve(strict=True) != destination.resolve(strict=True)):
        raise Refus(f'La source doit être une jonction vers {destination} : {source}')


def supprimer_jonction(source: Path, destination: Path) -> None:
    verifier_jonction(source, destination)
    os.rmdir(source)


def restaurer(plan: Plan) -> None:
    """Rétablit la source depuis la copie vérifiée ; conserve la copie si échec."""
    if os.path.lexists(plan.source) and est_lien(plan.source):
        supprimer_jonction(plan.source, plan.destination)
    fichiers, dossiers, taille = inventaire(plan.destination)
    inverse = Plan(plan.destination, plan.source, fichiers, dossiers, taille, 0, True)
    copier(inverse)
    comparer(plan.destination, plan.source)
    nettoyer_copie(plan)


def verifier_journal(journal: Path, source: Path, destination: Path) -> None:
    verifier_chemin(journal)
    if any(journal == racine or racine in journal.parents for racine in (source, destination)):
        raise Refus('Le journal doit être hors des dossiers déplacés.')
    if journal.exists() and not journal.is_file():
        raise Refus(f'Journal invalide : {journal}')


def journaliser(flux, entree: dict) -> None:
    position = flux.tell()
    try:
        flux.write(json.dumps(entree, ensure_ascii=True) + '\n')
        flux.flush()
        os.fsync(flux.fileno())
    except Exception:
        flux.seek(position)
        flux.truncate()
        flux.flush()
        raise


def afficher(plan: Plan, *, retour: bool = False) -> None:
    print(f'{"Retour" if retour else "Déplacement"} : {plan.source} -> {plan.destination}')
    print(f'{len(plan.fichiers)} fichiers ; {plan.taille} octets ; espace libre : {plan.libre} octets')
    for fichier in plan.fichiers:
        print(f'  {fichier}')
    if retour:
        print(f'Jonction à supprimer : {plan.destination} -> {plan.source}')
    else:
        print(f'Jonction à créer : {plan.source} -> {plan.destination}')


def deplacer(source: str | Path, destination: str | Path, *, appliquer: bool = False,
             journal: Path | None = None) -> dict | None:
    plan = preparer(source, destination)
    journal = normaliser(journal if journal is not None else models_dir() / '_deplacements.jsonl')
    verifier_journal(journal, plan.source, plan.destination)
    afficher(plan)
    if not appliquer:
        print('Simulation : aucune modification.')
        return None
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open('a', encoding='utf-8') as flux:
        try:
            initial = instantane(plan)
            copier(plan)
            signature = comparer(plan.source, plan.destination)
        except Exception:
            nettoyer_copie(plan)
            raise
        entree = dict(id=uuid.uuid4().hex, date=datetime.now(timezone.utc).isoformat(),
                      source=str(plan.source), destination=str(plan.destination),
                      nombre_fichiers=len(plan.fichiers), taille=plan.taille,
                      empreinte=signature, etat='deplace')
        try:
            for relatif in plan.fichiers:
                verifier_disponible(plan.source / relatif)
            if inventaire(plan.source) != (plan.fichiers, plan.dossiers, plan.taille):
                raise Refus('La source a changé pendant la copie ; déplacement refusé.')
            if instantane(plan) != initial:
                raise Refus('La source a changé pendant la copie ; déplacement refusé.')
        except Exception:
            nettoyer_copie(plan)
            raise
        try:
            supprimer_arbre(plan.source, plan.source)
        except Exception:
            restaurer(plan)
            raise
        try:
            creer_jonction(plan.source, plan.destination)
        except Exception as exc:
            restaurer(plan)
            raise Refus(f'Jonction impossible ; état initial rétabli : {exc}', 4) from exc
        try:
            journaliser(flux, entree)
        except Exception:
            restaurer(plan)
            raise
    print(f'Déplacement journalisé : {entree["id"]}')
    return entree


def lire_entree(journal: Path, identifiant: str) -> dict:
    verifier_chemin(journal)
    entree = None
    try:
        with journal.open(encoding='utf-8') as flux:
            for ligne in flux:
                candidate = json.loads(ligne)
                if not isinstance(candidate, dict):
                    raise ValueError('entrée non objet')
                if candidate.get('id') == identifiant:
                    entree = candidate
    except (OSError, ValueError) as exc:
        raise Refus(f'Journal illisible : {exc}') from exc
    if entree is None or entree.get('etat') != 'deplace':
        raise Refus(f'Déplacement inconnu ou déjà rétabli : {identifiant}')
    if not all(isinstance(entree.get(cle), str) and entree[cle]
               for cle in ('source', 'destination', 'empreinte')):
        raise Refus('Entrée de journal incomplète.')
    return entree


def retour(identifiant: str, *, appliquer: bool = False, journal: Path | None = None) -> None:
    journal = normaliser(journal if journal is not None else models_dir() / '_deplacements.jsonl')
    entree = lire_entree(journal, identifiant)
    source, destination = normaliser(entree['source']), normaliser(entree['destination'])
    verifier_chemin(source.parent)
    verifier_chemin(destination)
    verifier_journal(journal, source, destination)
    verifier_mklink(source, destination)
    verifier_jonction(source, destination)
    # Préparer sans suivre la jonction à l'ancien emplacement.
    fichiers, dossiers, taille = inventaire(destination)
    poids = normaliser(models_dir())
    if destination == poids or poids not in destination.parents:
        raise Refus('La destination du journal doit être sous models/.')
    if source == destination or source in destination.parents or destination in source.parents:
        raise Refus('Chemins imbriqués dans le journal.')
    for relatif in fichiers:
        verifier_disponible(destination / relatif)
    libre = verifier_espace(source.parent, taille)
    if empreinte(destination) != entree['empreinte']:
        raise Refus('Empreinte des poids différente du journal ; retour refusé.', 3)
    plan = Plan(destination, source, fichiers, dossiers, taille, libre, False)
    afficher(plan, retour=True)
    if not appliquer:
        print('Simulation : aucune modification.')
        return
    with journal.open('a', encoding='utf-8') as flux:
        supprimer_jonction(source, destination)
        try:
            copier(plan)
            if comparer(destination, source) != entree['empreinte']:
                raise Refus('Les poids ont changé pendant le retour ; retour refusé.', 3)
        except Exception:
            nettoyer_copie(plan)
            creer_jonction(source, destination)
            raise
        try:
            supprimer_arbre(destination, destination)
            journaliser(flux, dict(entree, etat='retabli', date=datetime.now(timezone.utc).isoformat()))
        except Exception:
            # Suppression partielle ou journal indisponible : conserver le déplacement initial.
            restaurer(plan)
            creer_jonction(source, destination)
            raise
    print(f'Déplacement rétabli : {identifiant}')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commandes = parser.add_subparsers(dest='commande', required=True)
    mouvement = commandes.add_parser('deplacer')
    mouvement.add_argument('source', type=Path)
    mouvement.add_argument('destination', type=Path)
    annulation = commandes.add_parser('retour')
    annulation.add_argument('identifiant')
    for commande in (mouvement, annulation):
        commande.add_argument('--appliquer', action='store_true')
        commande.add_argument('--journal', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.commande == 'deplacer':
            deplacer(args.source, args.destination, appliquer=args.appliquer, journal=args.journal)
        else:
            retour(args.identifiant, appliquer=args.appliquer, journal=args.journal)
    except Refus as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    except Exception as exc:
        print(f'Erreur interne : {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
