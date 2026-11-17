"""Déclaration passive du module Atelier pour le portail."""
from vertia.modules.contrat import Module


def sante():
    return {"pret": True, "message": "Éditeur local sans moteur"}

MODULE = Module(nom="atelier", activite="image", titre="Atelier", version="0.2.0",
                lien="/atelier/", capacites=["image.editer"], sante=sante)
