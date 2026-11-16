"""Client HTTP léger du portail VertIA, sans dépendance tierce."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ErreurCLI(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ErreurCLI(10, message)


def lancer_serveur():
    root = Path(__file__).resolve().parent
    python = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    options = dict(cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.name == 'nt':
        options['creationflags'] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        options['start_new_session'] = True
    subprocess.Popen([str(python), str(root / 'run.py'), '--headless'], **options)


class Client:
    def __init__(self, port):
        self.base = f'http://127.0.0.1:{port}/api/v1'

    def requete(self, chemin, body=None, timeout=5):
        data = None if body is None else json.dumps(body).encode('utf-8')
        request = Request(self.base + chemin, data=data, headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=max(.001, timeout)) as response:
                return json.load(response)
        except HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            code = 10 if exc.code == 422 else 1
            if exc.code == 404 and 'session_inconnue' in detail:
                code = 8
            raise ErreurCLI(code, detail) from exc

    def assurer_serveur(self, lanceur):
        try:
            self.requete('/sante')
            return
        except (OSError, URLError, ValueError, ErreurCLI):
            pass
        try:
            lanceur()
        except OSError as exc:
            raise ErreurCLI(9, 'Démarrage du serveur impossible.') from exc
        attente = float(os.getenv('VERTIA_START_TIMEOUT', '60'))
        if not math.isfinite(attente) or attente < 0:
            raise ErreurCLI(10, 'VERTIA_START_TIMEOUT invalide.')
        deadline = time.monotonic() + attente
        while time.monotonic() < deadline:
            try:
                self.requete('/sante', timeout=min(1, deadline - time.monotonic()))
                return
            except (OSError, URLError, ValueError, ErreurCLI):
                time.sleep(min(.1, max(0, deadline - time.monotonic())))
        raise ErreurCLI(9, 'Serveur injoignable après démarrage automatique.')

    def attendre(self, demande_id, timeout, sans_attente=False):
        deadline = time.monotonic() + timeout
        while True:
            reste = deadline - time.monotonic()
            if reste <= 0:
                raise ErreurCLI(5, 'Délai d’attente dépassé.')
            try:
                etat = self.requete('/demandes/' + demande_id, timeout=min(5, reste))
            except (TimeoutError, URLError) as exc:
                if time.monotonic() >= deadline:
                    raise ErreurCLI(5, 'Délai d’attente dépassé.') from exc
                raise
            code = afficher_etat(etat)
            if code != 2:
                return code
            if sans_attente:
                return 2
            time.sleep(min(.1, max(0, deadline - time.monotonic())))


def afficher_etat(demande):
    etat = demande['etat']
    if etat in {'livre', 'valide'}:
        for chemin in demande.get('chemins', []):
            print(chemin)
        return 0
    if etat == 'plafond':
        return 11
    if etat == 'echec':
        print(demande.get('erreur') or demande.get('motif_code', 'moteur'), file=sys.stderr)
        return {'gpu_occupe': 4, 'moteur': 6, 'pause': 7}.get(demande.get('motif_code'), 6)
    if etat == 'annule':
        print('Demande annulée.', file=sys.stderr)
        return 1
    return 2


def arguments(argv):
    parser = Parser(description=__doc__)
    parser.add_argument('action', help='capacité, retour, etat ou capacites')
    parser.add_argument('suite', nargs='*')
    parser.add_argument('--session')
    parser.add_argument('--prompt')
    parser.add_argument('--param', action='append', nargs='+', default=[])
    parser.add_argument('--critere', default='')
    parser.add_argument('--essais', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=1800)
    parser.add_argument('--sans-attente', action='store_true')
    parser.add_argument('--motif', default='')
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0 or not 1 <= args.essais <= 5:
        raise ErreurCLI(10, 'Timeout ou nombre d’essais invalide.')
    if args.action == 'retour':
        if len(args.suite) != 2 or args.suite[1] not in {'valide', 'a_refaire'}:
            raise ErreurCLI(10, 'retour exige un id et valide|a_refaire.')
    elif args.action == 'etat':
        if len(args.suite) != 1:
            raise ErreurCLI(10, 'etat exige un id.')
    elif args.suite or (args.action != 'capacites' and not args.session):
        raise ErreurCLI(10, 'Capacité et --session requis.')
    params = {}
    if args.prompt is not None:
        params['prompt'] = args.prompt
    for group in args.param:
        for entry in group:
            key, sep, value = entry.partition('=')
            if not sep or not key:
                raise ErreurCLI(10, '--param exige k=v.')
            try:
                params[key] = json.loads(value)
            except ValueError:
                params[key] = value
    return args, params


def main(argv=None, *, lanceur=None):
    identifie = False
    try:
        args, params = arguments(argv)
        try:
            port = int(os.getenv('VERTIA_PORT', '4310'))
        except ValueError as exc:
            raise ErreurCLI(10, 'Port invalide.') from exc
        if not 1 <= port <= 65535:
            raise ErreurCLI(10, 'Port invalide.')
        client = Client(port)
        client.assurer_serveur(lanceur or lancer_serveur)
        if args.action == 'capacites':
            print('id=', file=sys.stderr)
            identifie = True
            print(json.dumps(client.requete('/capacites'), ensure_ascii=False), file=sys.stderr)
            return 0
        if args.action in {'retour', 'etat'}:
            demande_id = args.suite[0]
            # Les identifiants ne doivent jamais injecter de chemin ou de requête HTTP.
            if not demande_id.isalnum():
                raise ErreurCLI(10, 'Identifiant de demande invalide.')
        else:
            capacite = args.action if '.' in args.action else args.action + '.generer'
            demande_id = client.requete('/demandes', dict(session=args.session, capacite=capacite,
                params=params, critere=args.critere, essais_max=args.essais))['id']
        print('id=' + demande_id, file=sys.stderr)
        identifie = True
        if args.action == 'retour':
            demande = client.requete('/demandes/' + demande_id + '/retour',
                                     dict(verdict=args.suite[1], motif=args.motif))
            code = afficher_etat(demande)
            if code != 2:
                return code
        if args.action == 'etat':
            demande = client.requete('/demandes/' + demande_id)
            print(demande['etat'], file=sys.stderr)
            return afficher_etat(demande)
        return client.attendre(demande_id, args.timeout, args.sans_attente)
    except ErreurCLI as exc:
        if not identifie:
            print('id=', file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return exc.code
    except (OSError, URLError, ValueError, KeyError, TypeError) as exc:
        if not identifie:
            print('id=', file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
