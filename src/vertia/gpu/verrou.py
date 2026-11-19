from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from contextvars import ContextVar, copy_context
from pathlib import Path

from vertia.engines.base import EngineError

note_demande = ContextVar('note_demande_gpu', default='')


async def terminer_nettoyage(awaitable):
    task = asyncio.ensure_future(awaitable)
    annule = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            annule = True
    result = task.result()
    if annule:
        raise asyncio.CancelledError
    return result


def contextualiser(operation, note):
    token = note_demande.set(note)
    try:
        operation.contexte_gpu = copy_context()
    finally:
        note_demande.reset(token)


class VerrouIndisponible(EngineError):
    pass


class GpuOccupe(VerrouIndisponible):
    motif_code = 'gpu_occupe'


class PauseUtilisateur(VerrouIndisponible):
    motif_code = 'pause'


class _ProcessThread:
    def __init__(self, process):
        self._process = process

    @property
    def returncode(self):
        return self._process.poll()

    async def wait(self):
        return await asyncio.to_thread(self._process.wait)

    def kill(self):
        self._process.kill()


class VerrouGpu:
    def __init__(self, attente_s=600):
        self.attente_s = max(0, attente_s)
        self.detenu = False
        self._lock = asyncio.Lock()
        self.script = Path(__file__).resolve().parents[3] / '_orchestration' / 'vram_lock.py'

    async def _lancer(self, commande, args):
        try:
            return await asyncio.create_subprocess_exec(
                sys.executable, str(self.script), commande, 'vertia', *args,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=0x08000000 if os.name == 'nt' else 0)
        except NotImplementedError:
            # Boucle Selector (serveur lancé avec rechargement sous Windows) : pas de sous-processus asyncio.
            process = subprocess.Popen(
                [sys.executable, str(self.script), commande, 'vertia', *args],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=0x08000000 if os.name == 'nt' else 0)
            return _ProcessThread(process)

    async def _commande(self, commande, *args):
        lancement = asyncio.create_task(self._lancer(commande, args))
        process = None
        try:
            process = await asyncio.shield(lancement)
            # Le script attend en minutes et son dernier sondage peut dépasser le délai.
            timeout = self.attente_s + 30 if commande == 'acquire' else 30
            return await asyncio.wait_for(process.wait(), timeout)
        except BaseException:
            async def arreter():
                nonlocal process
                if process is None:
                    result = await asyncio.gather(lancement, return_exceptions=True)
                    if not isinstance(result[0], BaseException):
                        process = result[0]
                if process is not None:
                    if process.returncode is None:
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
                    await process.wait()

            await terminer_nettoyage(arreter())
            raise

    @staticmethod
    def _refus(code):
        if code in {2, 4}:
            return GpuOccupe('GPU occupé ; réessayez après la libération du jeton.')
        if code == 7:
            return PauseUtilisateur('GPU en pause à la demande de l’utilisateur.')
        return VerrouIndisponible(f'Verrou GPU indisponible (code {code}).')

    async def _nettoyer(self):
        await terminer_nettoyage(self._nettoyer_commandes())

    async def _nettoyer_commandes(self):
        self.detenu = False
        erreur = None
        # Une acquisition annulée peut avoir écrit le jeton juste avant l’arrêt.
        for commande in ('release', 'cancel'):
            try:
                code = await self._commande(commande)
                if code not in {0, 5, 6}:
                    raise self._refus(code)
            except (OSError, TimeoutError) as exc:
                erreur = VerrouIndisponible('Nettoyage du verrou GPU impossible.')
                erreur.__cause__ = exc
            except VerrouIndisponible as exc:
                erreur = exc
        if erreur:
            raise erreur

    async def acquerir(self, note: str, gb: float):
        async with self._lock:
            if self.detenu:
                return
            try:
                code = await self._commande('acquire', '--gb', str(gb), '--minutes', '45',
                                            '--wait', '--timeout', str(self.attente_s / 60), '--note', note)
                if code != 0:
                    raise self._refus(code)
                self.detenu = True
            except BaseException as exc:
                await self._nettoyer()
                if isinstance(exc, TimeoutError):
                    raise GpuOccupe('Délai d’attente du jeton GPU dépassé.') from exc
                if isinstance(exc, OSError):
                    raise VerrouIndisponible('Lancement du verrou GPU impossible.') from exc
                raise

    async def liberer(self):
        async with self._lock:
            if self.detenu:
                await self._nettoyer()

    async def prolonger(self):
        async with self._lock:
            if not self.detenu:
                return
            try:
                code = await self._commande('extend', '--minutes', '45')
                if code != 0:
                    raise self._refus(code)
            except BaseException as exc:
                await self._nettoyer()
                if isinstance(exc, (OSError, TimeoutError)):
                    raise VerrouIndisponible('Prolongation du verrou GPU impossible.') from exc
                raise
