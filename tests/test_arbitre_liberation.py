import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest

from test_chat import FakeOllama
from test_jobs import FakeMonitor
from vertia.app import create_app
from vertia.chemins import resoudre_chemins
from vertia.engines.base import EngineError
from vertia.jobs.arbiter import GpuArbiter


def creer_arbitre():
    verrou = SimpleNamespace(detenu=False, prolonger=AsyncMock())

    async def acquerir(**kwargs):
        verrou.detenu = True

    async def liberer():
        verrou.detenu = False

    verrou.acquerir = AsyncMock(side_effect=acquerir)
    verrou.liberer = AsyncMock(side_effect=liberer)
    moteurs = {nom: SimpleNamespace(start=AsyncMock(), free=AsyncMock()) for nom in ('a', 'b')}
    return GpuArbiter(moteurs, SimpleNamespace(check=AsyncMock()), idle_seconds=1, verrou=verrou)


@pytest.mark.parametrize('reprise', ['free', 'release_idle', 'close'])
async def test_echec_dechargement_conserve_jeton_et_reessaie(reprise, caplog):
    arbitre = creer_arbitre()
    await arbitre.execute('a', AsyncMock())
    prolongation = arbitre._prolongation
    arbitre.engines['a'].free.side_effect = EngineError('Déchargement simulé')
    try:
        with pytest.raises(EngineError, match='simulé'):
            await arbitre.free()
        assert arbitre.active == 'a' and arbitre.verrou.detenu
        arbitre.verrou.liberer.assert_not_awaited()
        assert arbitre._prolongation is prolongation and not prolongation.done()
        arbitre.engines['b'].free.assert_awaited()
        assert 'jeton GPU conservé' in caplog.text
        arbitre.engines['a'].free.side_effect = None
        arbitre.last_used = time.monotonic() - 2
        await getattr(arbitre, reprise)()
        assert arbitre.active is None and not arbitre.verrou.detenu
        assert prolongation.done() and arbitre._prolongation is None
        arbitre.verrou.liberer.assert_awaited_once()
        assert arbitre.engines['a'].free.await_count == 2
    finally:
        arbitre.engines['a'].free.side_effect = None
        await arbitre.close()


async def test_echec_moteur_non_actif_empeche_liberation_partielle():
    arbitre = creer_arbitre()
    await arbitre.execute('a', AsyncMock())
    arbitre.engines['b'].free.side_effect = EngineError('Moteur externe résident')
    try:
        with pytest.raises(EngineError):
            await arbitre.free()
        assert arbitre.active is None and arbitre.verrou.detenu
        await arbitre.free('a')
        assert arbitre.verrou.detenu
        arbitre.verrou.liberer.assert_not_awaited()
        arbitre.engines['b'].free.side_effect = None
        await arbitre.close()
        assert not arbitre.verrou.detenu
    finally:
        arbitre.engines['b'].free.side_effect = None
        await arbitre.close()


async def test_echec_bascule_ne_demarre_pas_autre_moteur():
    arbitre = creer_arbitre()
    await arbitre.execute('a', AsyncMock())
    arbitre.engines['a'].free.side_effect = EngineError('Déchargement simulé')
    operation = AsyncMock()
    try:
        with pytest.raises(EngineError):
            await arbitre.execute('b', operation)
        assert arbitre.active == 'a' and arbitre.verrou.detenu
        arbitre.engines['b'].start.assert_not_awaited()
        operation.assert_not_awaited()
        arbitre.engines['a'].free.side_effect = None
        await arbitre.execute('b', operation)
        assert arbitre.active == 'b'
        operation.assert_awaited_once()
        assert arbitre.verrou.detenu
    finally:
        arbitre.engines['a'].free.side_effect = None
        await arbitre.close()


async def test_liberation_nominale_et_ordre_garde_inchanges():
    arbitre = creer_arbitre()

    async def garde(*args):
        assert arbitre.verrou.detenu

    arbitre.guard.check.side_effect = garde
    await arbitre.execute('a', AsyncMock(return_value='réponse'))
    await arbitre.free('b')
    assert arbitre.active == 'a' and arbitre.verrou.detenu
    await arbitre.free('a')
    assert arbitre.active is None and not arbitre.verrou.detenu
    arbitre.verrou.liberer.assert_awaited_once()
    await arbitre.close()


@pytest.mark.parametrize('echecs', [set(), {'arbitre'}, {'préchargement', 'jobs', 'demandes', 'arbitre', 'chat', 'moteur'}])
def test_fermetures_independantes_du_lifespan(settings, tmp_path, caplog, echecs):
    app = create_app(replace(settings, preload_ollama=False), overrides={
        'ollama': FakeOllama(), 'monitor': FakeMonitor(),
        'chemins': resoudre_chemins(tmp_path, environ={})})
    services = app.state.services
    ordre = []

    def fermeture(nom):
        async def fermer():
            ordre.append(nom)
            if nom in echecs:
                raise RuntimeError('Fermeture simulée')
        return AsyncMock(side_effect=fermer)

    services.ollama_preload.close = fermeture('préchargement')
    services.jobs.close = fermeture('jobs')
    services.demandes.close = fermeture('demandes')
    services.arbiter.close = fermeture('arbitre')
    services.chat.close = fermeture('chat')
    moteurs = list(services.arbiter.engines.values())
    for index, moteur in enumerate(moteurs):
        if hasattr(moteur, 'close'):
            moteur.close = fermeture('moteur' if index == 1 else f'moteur {index}')
    fermer_service = services.ollama_service.close
    services.ollama_service.close = fermeture('service Ollama')
    try:
        with TestClient(app):
            services.actions.ephemeral['test'] = {}
            services.files.ephemeral['test'] = {}
        assert ordre[:5] == ['préchargement', 'jobs', 'demandes', 'arbitre', 'chat']
        assert ordre[-3:] == ['jobs', 'arbitre', 'service Ollama']
        assert 'moteur' in ordre and 'moteur 2' in ordre
        assert not services.actions.ephemeral and not services.files.ephemeral
        if echecs:
            assert 'Fermeture de' in caplog.text
    finally:
        asyncio.run(services.ollama.close())
        for moteur in moteurs[1:3]:
            asyncio.run(moteur.client.aclose())
        asyncio.run(fermer_service())
