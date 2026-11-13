from __future__ import annotations

from typing import Protocol


class ParameterError(ValueError):
    """Consigne de correction explicite, sans valeur utilisateur ni réponse brute."""


class Tool(Protocol):
    name: str
    description: str
    engine: str
    parameters: dict

    def matches(self, text: str) -> bool: ...
    def validate(self, params: dict) -> dict: ...
    async def run(self, params: dict, progress) -> dict: ...
