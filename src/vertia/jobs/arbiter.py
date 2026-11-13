from __future__ import annotations

import asyncio
import time

class GpuArbiter:
    def __init__(self, engines, guard, idle_seconds=300):
        self.engines, self.guard = engines, guard
        self.active = None
        self.lock = asyncio.Lock()
        self.last_used = time.monotonic()
        self.idle_seconds = idle_seconds

    async def execute(self, engine, operation, memory_request=None):
        if engine not in self.engines:
            raise ValueError(f'Moteur non disponible : {engine}.')
        async with self.lock:
            # Libérer aussi les modèles présents avant le démarrage de VertIA.
            for name, adapter in self.engines.items():
                if name != engine:
                    await adapter.free()
                    if self.active == name:
                        self.active = None
            needs = getattr(self.engines[engine], 'memory', None) if self.active != engine else None
            reuse = getattr(self.engines[engine], 'can_reuse', None)
            if memory_request is not None and reuse is not None:
                await self.guard.check(needs, reuse=lambda state: reuse(memory_request, state))
            else:
                await self.guard.check(needs)
            self.active = None
            try:
                await self.engines[engine].start()
                self.active = engine
                return await operation()
            finally:
                self.last_used = time.monotonic()

    async def free(self, engine=None):
        async with self.lock:
            names = [engine] if engine else list(self.engines)
            for name in names:
                if name not in self.engines:
                    raise ValueError(f'Moteur non disponible : {name}.')
                await self.engines[name].free()
                if self.active == name:
                    self.active = None
            self.last_used = time.monotonic()

    async def release_idle(self):
        if self.lock.locked() or not self.idle_seconds or time.monotonic() - self.last_used < self.idle_seconds:
            return
        await self.free()
