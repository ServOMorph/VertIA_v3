from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Awaitable, Callable, Protocol

from vertia.engines.base import Engine, MemoryNeeds
from vertia.tools.base import Tool

ACTIVITES = {'image', 'musique', 'voix', 'video', 'chat', '3d', 'animation_3d',
             'worldmodel', 'llm', 'outil'}
_NUMBER = r'(?:0|[1-9][0-9]*)'
_PRE = r'(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)'
_SEMVER = re.compile(
    rf'{_NUMBER}\.{_NUMBER}\.{_NUMBER}(?:-{_PRE}(?:\.{_PRE})*)?'
    r'(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?'
)


class OutilCapacite(Protocol):
    capacite: str
    moteur: str | None

    def valider(self, params: dict) -> dict: ...

    def executer(self, params: dict, dossier: Path) -> list[Path] | Awaitable[list[Path]]: ...


@dataclass(frozen=True)
class Module:
    nom: str
    activite: str
    titre: str
    version: str
    moteurs: dict[str, Callable[..., Engine]] = field(default_factory=dict)
    outils: dict[str, Callable[..., Tool]] = field(default_factory=dict)
    capacites: list[str] = field(default_factory=list)
    besoins: dict[str, MemoryNeeds] = field(default_factory=dict)
    poids: list[str] = field(default_factory=list)
    sante: Callable[[], dict] = dict
    lien: str | None = None

    def __post_init__(self):
        if not isinstance(self.nom, str) or not self.nom.isidentifier() or keyword.iskeyword(self.nom):
            raise ValueError('Nom de module invalide.')
        if not isinstance(self.activite, str) or self.activite not in ACTIVITES:
            raise ValueError('Activité de module inconnue.')
        if not isinstance(self.titre, str) or not self.titre.strip():
            raise ValueError('Titre de module invalide.')
        if not isinstance(self.version, str) or not _SEMVER.fullmatch(self.version):
            raise ValueError('Version de module invalide (semver attendu).')
        if not isinstance(self.capacites, list) or any(
            not isinstance(capacite, str) or not re.fullmatch(r'[a-z0-9_]+\.[a-z][a-z0-9_]*', capacite)
            for capacite in self.capacites
        ):
            raise ValueError('Capacité invalide (domaine.verbe attendu).')
        for factories in (self.moteurs, self.outils):
            if not isinstance(factories, dict) or any(
                not isinstance(name, str) or not (callable(factory) or (
                    factories is self.outils and isinstance(getattr(factory, 'capacite', None), str)
                    and callable(getattr(factory, 'valider', None))
                    and callable(getattr(factory, 'executer', None))))
                for name, factory in factories.items()
            ):
                raise ValueError('Fabriques de module invalides.')
        if not isinstance(self.besoins, dict) or any(
            name not in self.moteurs or not isinstance(needs, MemoryNeeds)
            for name, needs in self.besoins.items()
        ):
            raise ValueError('Besoins mémoire invalides.')
        if not isinstance(self.poids, list):
            raise ValueError('Liste de poids invalide.')
        for poids in self.poids:
            if not isinstance(poids, str) or not poids:
                raise ValueError('Chemin de poids invalide.')
            for path in (PurePosixPath(poids), PureWindowsPath(poids)):
                if path.is_absolute() or path.anchor or '..' in path.parts or str(path) == '.':
                    raise ValueError('Les poids doivent être relatifs à models/.')
        if not callable(self.sante):
            raise ValueError('Diagnostic de module invalide.')
