from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess

from vertia.chemins import ROOT
from vertia.engines.base import EngineError, MemoryNeeds
from vertia.engines.process import ProcessOwner

TRAVAILLEURS = ('chatterbox', 'kokoro', 'whisper')


def python_travailleur(chemins, nom):
    venv = chemins.engines_dir / 'voix' / nom / '.venv'
    return venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


class VoixEngine(ProcessOwner):
    memory = MemoryNeeds(vram_mb=None, note='Besoins VRAM des travailleurs voix à mesurer.')

    def __init__(self, chemins, *, pythons=None, scripts=None, delai_pret=600,
                 delai_requete=1800, launcher=subprocess.Popen):
        super().__init__('Voix')
        self.chemins = chemins
        self.pythons = {nom: python_travailleur(chemins, nom) for nom in TRAVAILLEURS}
        self.pythons.update(pythons or {})
        self.scripts = {nom: ROOT / 'modules/voix/travailleurs' / f'travailleur_{nom}.py'
                        for nom in TRAVAILLEURS}
        self.scripts.update(scripts or {})
        self.delai_pret, self.delai_requete = delai_pret, delai_requete
        self.launcher = launcher
        self.travailleur = None
        self._verrou = asyncio.Lock()
        self._lecture = None
        self._journal = None

    async def start(self):
        pass

    async def health(self):
        return not self.stopping and (self.process is None or self.owned())

    async def stop(self):
        process = self.process
        await super().stop()
        if self._lecture is not None:
            await asyncio.gather(self._lecture, return_exceptions=True)
            self._lecture = None
        if process is not None:
            process.wait()
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
        if self._journal is not None:
            self._journal.close()
            self._journal = None
        self.travailleur = None

    async def free(self):
        await self.stop()

    async def close(self):
        await self.stop()

    async def _lire(self, delai):
        self._lecture = asyncio.create_task(asyncio.to_thread(self.process.stdout.readline, 1024**2 + 1))
        try:
            ligne = await asyncio.wait_for(asyncio.shield(self._lecture), delai)
        except TimeoutError as exc:
            raise EngineError('Délai du travailleur voix dépassé.') from exc
        if not ligne:
            raise EngineError('Le travailleur voix s’est arrêté sans réponse.')
        try:
            if len(ligne) > 1024**2 or not ligne.endswith('\n'):
                raise ValueError
            message = json.loads(ligne)
            if not isinstance(message, dict):
                raise ValueError
            return message
        except ValueError as exc:
            raise EngineError('Réponse du travailleur voix illisible.') from exc

    async def _demarrer(self, nom):
        if self.travailleur == nom and self.owned():
            return
        await self.stop()
        python, script = Path(self.pythons[nom]), Path(self.scripts[nom])
        if not python.is_file() or not script.is_file():
            raise EngineError(f'Installation du travailleur {nom} introuvable.')
        logs = self.chemins.data_dir / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, HF_HOME=str(self.chemins.models_dir / 'hf'),
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                   VERTIA_WHISPER_DIR=str(self.chemins.models_dir / 'whisper'),
                   PYTHONIOENCODING='utf-8')
        self._journal = (logs / f'voix_{nom}.log').open('a', encoding='utf-8')
        self.process = self.launcher(
            [str(python), '-u', '-B', str(script.resolve()), '--device', 'cuda'],
            cwd=script.parent, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._journal, text=True, encoding='utf-8', errors='strict',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.travailleur = nom
        if await self._lire(self.delai_pret) != {'pret': True}:
            raise EngineError('Le travailleur voix n’a pas annoncé être prêt.')

    async def requete(self, nom, params, sortie):
        if nom not in TRAVAILLEURS:
            raise EngineError('Travailleur voix inconnu.')
        async with self._verrou:
            try:
                await self._demarrer(nom)
                message = dict(params, sortie=str(Path(sortie).resolve()))
                self.process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
                self.process.stdin.flush()
                resultat = await self._lire(self.delai_requete)
                if resultat.get('ok') is False:
                    raise EngineError('Le travailleur voix a refusé la requête. Consultez son journal.')
                if (resultat.get('ok') is not True or not isinstance(resultat.get('fichiers'), list)
                        or any(not isinstance(n, str) for n in resultat['fichiers'])):
                    raise EngineError('Réponse du travailleur voix illisible.')
                return resultat['fichiers']
            except asyncio.CancelledError:
                await self.stop()
                raise
            except (OSError, UnicodeError) as exc:
                await self.stop()
                raise EngineError('Communication avec le travailleur voix impossible.') from exc
            except BaseException:
                await self.stop()
                raise
