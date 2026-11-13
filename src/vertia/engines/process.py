from __future__ import annotations

import asyncio

import psutil

from vertia.engines.base import EngineError


class ProcessOwner:
    """Arrête uniquement l'arbre lancé par cet adaptateur, sans oublier les survivants."""

    def __init__(self, label):
        self.label = label
        self.process = None
        self.stopping = []
        self._stop_task = None

    def owned(self):
        return self.process is not None and self.process.poll() is None

    def _terminate(self):
        if not self.stopping:
            try:
                parent = psutil.Process(self.process.pid)
                self.stopping = parent.children(recursive=True) + [parent]
            except psutil.NoSuchProcess:
                for child in psutil.process_iter(['ppid']):
                    if child.info['ppid'] == self.process.pid:
                        self.stopping.append(child)
                        try:
                            self.stopping.extend(child.children(recursive=True))
                        except psutil.NoSuchProcess:
                            pass
        owned = self.stopping
        for item in reversed(owned):
            try:
                item.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(owned, timeout=5)
        for item in alive:
            try:
                item.kill()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(alive, timeout=5)
        self.stopping = alive
        if alive:
            raise EngineError(f'Arrêt {self.label} incomplet. Libérez ce moteur avant de poursuivre.')

    async def stop(self):
        if self._stop_task is None and (self.process is not None or self.stopping):
            self._stop_task = asyncio.create_task(asyncio.to_thread(self._terminate))
        task = self._stop_task
        cancelled = False
        if task is not None:
            try:
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        # Le verrou GPU doit rester détenu jusqu'à la fin de l'arrêt.
                        cancelled = True
                task.result()
            finally:
                if task.done():
                    self._stop_task = None
        self.process = None
        if cancelled:
            raise asyncio.CancelledError
