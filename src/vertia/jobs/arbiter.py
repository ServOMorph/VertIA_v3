from __future__ import annotations

import asyncio
import logging
import math
import time

from vertia.gpu.verrou import note_demande, terminer_nettoyage

logger = logging.getLogger(__name__)


class GpuArbiter:
    def __init__(self, engines, guard, idle_seconds=300, verrou=None):
        self.engines, self.guard = engines, guard
        self.active = None
        self.lock = asyncio.Lock()
        self.last_used = time.monotonic()
        self.idle_seconds = idle_seconds
        self.verrou = verrou
        self.travaux_actifs = 0
        self.prolongation_seconds = 30 * 60
        self._prolongation = None
        self._execution = None
        self._erreur_verrou = None

    async def _prolonger(self):
        try:
            while True:
                await asyncio.sleep(self.prolongation_seconds)
                await self.verrou.prolonger()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._erreur_verrou = exc
            if self._execution:
                self._execution.cancel()
            else:
                try:
                    await self.free()
                except Exception:
                    logger.exception('Libération des moteurs après perte du jeton GPU impossible.')

    async def _liberer(self, names):
        erreurs = []
        for name in names:
            try:
                await self.engines[name].free()
            except Exception as exc:
                erreurs.append(exc)
            finally:
                if self.active == name:
                    self.active = None
        if self.active is None:
            task, self._prolongation = self._prolongation, None
            if task and task is not asyncio.current_task():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if self.verrou:
                await self.verrou.liberer()
        if erreurs:
            raise erreurs[0]

    async def execute(self, engine, operation, memory_request=None):
        if engine not in self.engines:
            raise ValueError(f'Moteur non disponible : {engine}.')
        async with self.lock:
            memory = getattr(self.engines[engine], 'memory', None)
            gpu = engine != 'sans_gpu' and getattr(memory, 'vram_mb', None) != 0
            if not gpu:
                await self.guard.check(memory)
                await self.engines[engine].start()
                return await operation()
            self.travaux_actifs += 1
            self._execution = asyncio.current_task()
            self._erreur_verrou = None
            try:
                # Le jeton passe avant la garde mémoire : la pause d'un entraînement libère sa VRAM et sa RAM.
                if self.verrou and (self.active != engine or not self.verrou.detenu):
                    contexte = getattr(operation, '__dict__', {}).get('contexte_gpu')
                    note = contexte.get(note_demande, '') if contexte is not None else note_demande.get()
                    await self.verrou.acquerir(note=f'portail : {engine}' + (f' ; {note}' if note else ''),
                                               gb=max(1, math.ceil(vram / 1024)) if (vram := getattr(memory, 'vram_mb', None)) else 8)
                    if self._prolongation is None:
                        self._prolongation = asyncio.create_task(self._prolonger())
                # Libérer aussi les modèles présents avant le démarrage de VertIA.
                for name, adapter in self.engines.items():
                    if name != engine:
                        await adapter.free()
                        if self.active == name:
                            self.active = None
                needs = memory if self.active != engine else None
                reuse = getattr(self.engines[engine], 'can_reuse', None)
                if memory_request is not None and reuse is not None:
                    await self.guard.check(needs, reuse=lambda state: reuse(memory_request, state))
                else:
                    await self.guard.check(needs)
                self.active = None
                await self.engines[engine].start()
                self.active = engine
                return await operation()
            except BaseException:
                if self.verrou:
                    await terminer_nettoyage(self._liberer(list(self.engines)))
                if self._erreur_verrou is not None:
                    raise self._erreur_verrou
                raise
            finally:
                self._execution = None
                self.travaux_actifs -= 1
                self.last_used = time.monotonic()

    async def free(self, engine=None):
        async with self.lock:
            names = [engine] if engine else list(self.engines)
            for name in names:
                if name not in self.engines:
                    raise ValueError(f'Moteur non disponible : {name}.')
            await self._liberer(names)
            self.last_used = time.monotonic()

    async def release_idle(self):
        if self.lock.locked() or not self.idle_seconds or time.monotonic() - self.last_used < self.idle_seconds:
            return
        await self.free()

    async def close(self):
        if self.verrou and (self.active is not None or self.verrou.detenu or self._prolongation):
            await self.free()
