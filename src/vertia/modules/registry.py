from __future__ import annotations

import importlib.util
import sys
from dataclasses import fields
from pathlib import Path
from uuid import uuid4

from vertia.chemins import ROOT
from vertia.modules.contrat import Module


class RegistreModules:
    def __init__(self, dossier: Path = ROOT / 'modules'):
        self.erreurs: list[str] = []
        self._modules: dict[str, Module] = {}
        self._capacites: dict[str, Module] = {}
        dossier = Path(dossier)
        if not dossier.exists():
            return
        for declaration in sorted(dossier.glob('*/module.py')):
            name = f'_vertia_module_{uuid4().hex}'
            try:
                spec = importlib.util.spec_from_file_location(
                    name, declaration, submodule_search_locations=[str(declaration.parent)])
                if spec is None or spec.loader is None:
                    raise ValueError('Import de module indisponible.')
                imported = importlib.util.module_from_spec(spec)
                sys.modules[name] = imported
                spec.loader.exec_module(imported)
                value = imported.MODULE
                if isinstance(value, Module):
                    module = value
                elif isinstance(value, dict):
                    module = Module(**value)
                else:
                    module = Module(**{field.name: getattr(value, field.name)
                                       for field in fields(Module) if hasattr(value, field.name)})
                if module.nom in self._modules:
                    raise ValueError(f'Nom de module déjà déclaré : {module.nom}.')
                self._modules[module.nom] = module
                for capacite in module.capacites:
                    if capacite in self._capacites:
                        self.erreurs.append(f'{declaration.parent.name} : capacité déjà déclarée : {capacite}.')
                    else:
                        self._capacites[capacite] = module
            except Exception as exc:
                for key in list(sys.modules):
                    if key == name or key.startswith(name + '.'):
                        sys.modules.pop(key, None)
                self.erreurs.append(f'{declaration.parent.name} : {type(exc).__name__} : {exc}')

    def modules(self) -> list[Module]:
        return list(self._modules.values())

    def par_activite(self, activite: str) -> list[Module]:
        return [module for module in self._modules.values() if module.activite == activite]

    def capacites(self) -> dict[str, Module]:
        return dict(self._capacites)

    def sante(self) -> dict[str, dict]:
        result = {}
        for module in self._modules.values():
            try:
                diagnostic = module.sante()
                if not isinstance(diagnostic, dict):
                    raise ValueError('Le diagnostic doit renvoyer un dict.')
                result[module.nom] = diagnostic
            except Exception as exc:
                result[module.nom] = {'pret': False, 'erreur': f'{type(exc).__name__} : {exc}'}
        return result
