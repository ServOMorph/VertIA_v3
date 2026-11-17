import argparse
import json
import random
import sys
import traceback


def initialiser():
    canal = sys.stdout
    sys.stdout = sys.stderr
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='cuda')
    return parser.parse_args(), canal


def ecrire(canal, message):
    canal.write(json.dumps(message, ensure_ascii=False) + '\n')
    canal.flush()


def graine(valeur):
    import numpy
    import torch

    random.seed(valeur)
    numpy.random.seed(valeur % 2**32)
    torch.manual_seed(valeur % 2**64)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(valeur % 2**64)


def servir(canal, traiter):
    ecrire(canal, {'pret': True})
    for ligne in sys.stdin:
        try:
            params = json.loads(ligne)
            fichiers = traiter(params)
            ecrire(canal, {'ok': True, 'fichiers': fichiers})
        except Exception:
            traceback.print_exc(file=sys.stderr)
            ecrire(canal, {'ok': False, 'erreur': 'Échec du traitement audio.'})
