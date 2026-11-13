from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class EngineError(RuntimeError):
    """Erreur moteur explicite, sans contenu de prompt ni réponse externe brute."""


@dataclass(frozen=True)
class MemoryNeeds:
    ram_mb: int | None = None
    vram_mb: int | None = None
    note: str = ''


class Engine(Protocol):
    memory: MemoryNeeds

    async def start(self) -> None: ...
    async def health(self) -> bool: ...
    async def free(self) -> None: ...
    async def stop(self) -> None: ...
