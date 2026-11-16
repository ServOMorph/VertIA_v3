"""Déclaration passive du module Atelier pour le futur portail."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Module:
    nom: str = "atelier"
    activite: str = "image"
    titre: str = "Atelier"
    version: str = "0.2.0"
    lien = "http://127.0.0.1:4320"
    capacites: list = field(default_factory=lambda: ["image.editer"])
    moteurs: dict = field(default_factory=dict)
    outils: dict = field(default_factory=dict)
    besoins: dict = field(default_factory=dict)
    poids: list = field(default_factory=list)

    def sante(self):
        return {"pret": True, "message": "Éditeur local sans moteur"}


MODULE = Module()
