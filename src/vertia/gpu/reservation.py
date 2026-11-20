from __future__ import annotations

import time


class ReservationUi:
    """Réserve le GPU au chat tant qu'une interface est ouverte, le rend à sa fermeture."""

    def __init__(self, events, arbiter, preload, delai_fermeture_s=30.0, horloge=time.monotonic):
        self.events, self.arbiter, self.preload = events, arbiter, preload
        self.delai_fermeture_s = delai_fermeture_s
        self.horloge = horloge
        self.ouverte = False
        self._fermee_depuis = None

    async def tick(self) -> bool:
        """Retourne True si la libération sur inactivité reste autorisée."""
        if self.events.subscriber_count > 0:
            self._fermee_depuis = None
            if not self.ouverte:
                self.ouverte = True
                self.preload.start()
            return False
        if not self.ouverte:
            return True
        if self._fermee_depuis is None:
            self._fermee_depuis = self.horloge()
        if self.horloge() - self._fermee_depuis < self.delai_fermeture_s:
            return False
        if self.arbiter.lock.locked():
            return False
        self.ouverte = False
        self._fermee_depuis = None
        await self.preload.close()
        await self.arbiter.free()
        return True
