import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from vertia.engines.comfy_qwen import ComfyQwenEngine
from vertia.gpu.reservation import ReservationUi
from vertia.jobs.arbiter import GpuArbiter


class Horloge:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def reservation(clients=0):
    events = SimpleNamespace(subscriber_count=clients)
    arbiter = SimpleNamespace(lock=asyncio.Lock(), free=AsyncMock())
    preload = SimpleNamespace(start=MagicMock(), close=AsyncMock())
    horloge = Horloge()
    return ReservationUi(events, arbiter, preload, delai_fermeture_s=30, horloge=horloge), horloge


@pytest.mark.asyncio
async def test_sans_interface_la_liberation_sur_inactivite_reste_autorisee():
    res, _ = reservation()
    assert await res.tick() is True
    res.preload.start.assert_not_called()
    res.arbiter.free.assert_not_awaited()


@pytest.mark.asyncio
async def test_ouverture_precharge_une_fois_et_bloque_la_liberation():
    res, _ = reservation(clients=1)
    assert await res.tick() is False
    assert await res.tick() is False
    res.preload.start.assert_called_once()


@pytest.mark.asyncio
async def test_fermeture_rend_le_gpu_apres_le_delai():
    res, horloge = reservation(clients=1)
    await res.tick()
    res.events.subscriber_count = 0
    assert await res.tick() is False
    horloge.t = 29
    assert await res.tick() is False
    res.arbiter.free.assert_not_awaited()
    horloge.t = 30
    assert await res.tick() is True
    res.preload.close.assert_awaited_once()
    res.arbiter.free.assert_awaited_once()
    assert await res.tick() is True
    res.arbiter.free.assert_awaited_once()


@pytest.mark.asyncio
async def test_rechargement_de_page_dans_le_delai_garde_le_gpu():
    res, horloge = reservation(clients=1)
    await res.tick()
    res.events.subscriber_count = 0
    await res.tick()
    horloge.t = 10
    res.events.subscriber_count = 1
    assert await res.tick() is False
    res.events.subscriber_count = 0
    horloge.t = 35
    assert await res.tick() is False
    res.arbiter.free.assert_not_awaited()
    res.preload.start.assert_called_once()


@pytest.mark.asyncio
async def test_fermeture_attend_la_fin_du_travail_en_cours():
    res, horloge = reservation(clients=1)
    await res.tick()
    res.events.subscriber_count = 0
    await res.tick()
    horloge.t = 60
    async with res.arbiter.lock:
        assert await res.tick() is False
    res.arbiter.free.assert_not_awaited()
    assert await res.tick() is True
    res.arbiter.free.assert_awaited_once()


@pytest.mark.asyncio
async def test_reouverture_relance_le_prechargement():
    res, horloge = reservation(clients=1)
    await res.tick()
    res.events.subscriber_count = 0
    await res.tick()
    horloge.t = 30
    await res.tick()
    res.events.subscriber_count = 1
    await res.tick()
    assert res.preload.start.call_count == 2


@pytest.mark.asyncio
async def test_qwen_demande_le_jeton_du_gpu_entier():
    assert ComfyQwenEngine.memory.jeton_gb == 8
    verrou = SimpleNamespace(detenu=False, acquerir=AsyncMock(), liberer=AsyncMock(), prolonger=AsyncMock())
    engine = SimpleNamespace(memory=ComfyQwenEngine.memory, start=AsyncMock(), free=AsyncMock())
    arbiter = GpuArbiter({'comfy': engine}, SimpleNamespace(check=AsyncMock()), verrou=verrou)
    await arbiter.execute('comfy', AsyncMock(return_value='ok'))
    assert verrou.acquerir.await_args.kwargs['gb'] == 8
    if arbiter._prolongation:
        arbiter._prolongation.cancel()
