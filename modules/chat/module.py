from pathlib import Path

from vertia.config import Settings
from vertia.modules.contrat import Module

from .outil import OutilChat


def sante():
    executable = Settings.from_env().ollama_executable
    if executable:
        present = Path(executable).is_file()
        return dict(pret=present, executable_present=present,
                    message='Présence de l’exécutable uniquement ; service non contacté.')
    return dict(pret=True, message='Exécutable non renseigné ; service Ollama non contacté.')


MODULE = Module(nom='chat', activite='chat', titre='Discussion', version='0.1.0',
                capacites=['chat.generer'], outils={'generer': OutilChat},
                moteurs={}, besoins={}, poids=[], sante=sante, lien=None)
