import json
import math
import re

from vertia.engines.base import EngineError


def cadre_reperage(largeur, hauteur):
    pas = 28
    minimum = math.ceil(850_000 / pas**2)
    maximum = 1_000_000 // pas**2
    rapport = max(largeur, hauteur) / min(largeur, hauteur)

    def cle(taille):
        court, long = taille
        ratio = long / court / rapport
        ecart = abs((ratio if largeur >= hauteur else 1 / ratio) - 1)
        distance = abs(court * long * pas**2 - 925_000)
        if ecart <= 0.02:
            return (0, distance, ecart)
        # Pour les panoramas extrêmes, le quadrillage peut imposer un écart supérieur à 2 %.
        return (1, ecart, distance)

    court, long = min(
        ((court, long)
         for court in range(1, math.isqrt(maximum) + 1)
         for long in range(max(court, math.ceil(minimum / court)), maximum // court + 1)),
        key=cle,
    )
    return (long * pas, court * pas) if largeur >= hauteur else (court * pas, long * pas)


def _boite_numerique(valeur):
    return (isinstance(valeur, (list, tuple)) and len(valeur) == 4
            and all(type(n) is int or (type(n) is float and math.isfinite(n)) for n in valeur))


def zone_vers_source(boite, taille_reperage, taille_source):
    if not _boite_numerique(boite):
        return None
    zone = [
        round(min(max(n, 0), cote_reperage) * cote_source / cote_reperage)
        for n, cote_reperage, cote_source in zip(boite, taille_reperage * 2, taille_source * 2)
    ]
    x1, y1, x2, y2 = zone
    return zone if x2 - x1 >= 4 and y2 - y1 >= 4 else None


def extraire_boite(texte):
    decodeur = json.JSONDecoder()
    premiere_liste = None
    fin = 0
    for debut in re.finditer(r'[\[{]', texte):
        if debut.start() < fin:
            continue
        try:
            valeur, fin = decodeur.raw_decode(texte, debut.start())
        except (ValueError, RecursionError):
            continue
        a_lire = [valeur]
        while a_lire:
            valeur = a_lire.pop()
            if isinstance(valeur, dict):
                boite = valeur.get('bbox_2d')
                if _boite_numerique(boite):
                    return boite
                a_lire.extend(reversed(valeur.values()))
            elif isinstance(valeur, list):
                if premiere_liste is None and _boite_numerique(valeur):
                    premiere_liste = valeur
                a_lire.extend(reversed(valeur))
    return premiere_liste


def analyser_dialogue(texte):
    try:
        resultat = json.loads(texte)
    except (ValueError, RecursionError):
        resultat = None
        decodeur = json.JSONDecoder()
        for debut in re.finditer(r'\{', texte):
            try:
                resultat = decodeur.raw_decode(texte, debut.start())[0]
                break
            except (ValueError, RecursionError):
                continue
        if resultat is None:
            raise EngineError('JSON du modèle de dialogue illisible.')
    if not isinstance(resultat, dict):
        raise EngineError('Le JSON du modèle de dialogue doit être un objet.')

    def nettoyer(valeur, limite):
        return valeur.strip()[:limite] if isinstance(valeur, str) else ''

    propositions = []
    candidates = resultat.get('propositions')
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            titre = nettoyer(candidate.get('titre'), 120)
            cible = nettoyer(candidate.get('cible'), 200)
            prompt = nettoyer(candidate.get('prompt'), 1000)
            if titre and cible and prompt:
                type_cible = 'emplacement' if candidate.get('type') == 'emplacement' else 'objet'
                propositions.append(dict(titre=titre, cible=cible, prompt=prompt, type=type_cible, zone=None))
                if len(propositions) == 4:
                    break
    return nettoyer(resultat.get('reponse'), 4000), propositions
