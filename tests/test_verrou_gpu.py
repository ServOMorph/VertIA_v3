from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from vertia.app import create_app
from vertia.config import Settings
from vertia.engines.base import EngineError, MemoryNeeds
from vertia.gpu import GpuOccupe, PauseUtilisateur, VerrouGpu, VerrouIndisponible
from vertia.gpu.verrou import note_demande
from vertia.jobs.arbiter import GpuArbiter


class FauxProcessus:
    def __init__(self, code, delai=0):
        self.code, self.delai = code, delai
        self.returncode = None
        self.tue = False
        self.termine = asyncio.Event()

    async def wait(self):
        if self.returncode is None:
            await asyncio.sleep(self.delai)
            self.returncode = self.code
        self.termine.set()
        return self.returncode

    def kill(self):
        self.tue = True
        self.returncode = -9


@pytest.fixture
def processus(monkeypatch):
    appels, processus = [], []
    reponses = {}

    async def lancer(*args, **kwargs):
        commande = args[2]
        appels.append(args)
        reponse = reponses.get(commande, [(0, 0)])
        code, delai = reponse.pop(0) if len(reponse) > 1 else reponse[0]
        proc = FauxProcessus(code, delai)
        processus.append(proc)
        return proc

    monkeypatch.setattr('vertia.gpu.verrou.asyncio.create_subprocess_exec', lancer)
    return SimpleNamespace(appels=appels, reponses=reponses, processus=processus,
                           commandes=lambda: [args[2] for args in appels])


def arbitre(verrou, trace=None, engines=None):
    trace = trace if trace is not None else []

    async def demarrer():
        assert verrou.detenu
        trace.append('start')

    moteur = SimpleNamespace(memory=MemoryNeeds(vram_mb=2049),
                             start=AsyncMock(side_effect=demarrer), free=AsyncMock())
    return GpuArbiter(engines or {'gpu': moteur}, SimpleNamespace(check=AsyncMock()),
                      idle_seconds=1, verrou=verrou)


@pytest.mark.asyncio
async def test_acquisition_concurrente_idempotente_et_commande(processus):
    processus.reponses['acquire'] = [(0, .01)]
    verrou = VerrouGpu(attente_s=120)
    await asyncio.gather(*(verrou.acquerir('portail : gpu', 3) for _ in range(5)))
    assert verrou.detenu
    assert processus.commandes() == ['acquire']
    args = processus.appels[0]
    assert args[:4] == (sys.executable, str(verrou.script), 'acquire', 'vertia')
    assert verrou.script == Path(__file__).resolve().parents[1] / '_orchestration/vram_lock.py'
    assert args[args.index('--timeout') + 1] == '2.0'
    assert args[args.index('--note') + 1] == 'portail : gpu'
    await verrou.prolonger()
    assert processus.appels[1][-2:] == ('--minutes', '45')
    await verrou.liberer()
    await verrou.liberer()
    assert not verrou.detenu and processus.commandes().count('release') == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('code,erreur', [(2, GpuOccupe), (4, GpuOccupe), (7, PauseUtilisateur),
                                       (3, VerrouIndisponible), (5, VerrouIndisponible),
                                       (6, VerrouIndisponible), (8, VerrouIndisponible)])
async def test_refus_sans_jeton_ni_demarrage(processus, code, erreur):
    processus.reponses['acquire'] = [(code, 0)]
    verrou = VerrouGpu()
    arbiter = arbitre(verrou)
    operation = AsyncMock()
    with pytest.raises(erreur):
        await arbiter.execute('gpu', operation)
    assert not verrou.detenu and arbiter.active is None
    assert arbiter.travaux_actifs == 0 and arbiter._prolongation is None
    arbiter.engines['gpu'].start.assert_not_awaited()
    operation.assert_not_awaited()
    assert processus.commandes() == ['acquire', 'release', 'cancel']


@pytest.mark.asyncio
async def test_reutilisation_inactivite_et_aucune_liberation_pendant_travail(processus):
    verrou = VerrouGpu()
    arbiter = arbitre(verrou)
    entree, sortie = asyncio.Event(), asyncio.Event()

    async def operation():
        entree.set()
        await sortie.wait()

    task = asyncio.create_task(arbiter.execute('gpu', operation))
    await entree.wait()
    renouvellement = arbiter._prolongation
    arbiter.last_used = time.monotonic() - 10
    await arbiter.release_idle()
    assert verrou.detenu and arbiter.travaux_actifs == 1
    sortie.set()
    await task
    await arbiter.execute('gpu', AsyncMock())
    assert processus.commandes() == ['acquire']
    assert arbiter._prolongation is renouvellement
    args = processus.appels[0]
    assert args[args.index('--gb') + 1] == '3'
    arbiter.last_used = time.monotonic() - 2
    await arbiter.release_idle()
    assert not verrou.detenu and renouvellement.done()
    assert arbiter.active is None


@pytest.mark.asyncio
async def test_changement_moteur_conserve_jeton_et_liberation_partielle(processus):
    verrou = VerrouGpu()
    arbiter = arbitre(verrou)
    arbiter.engines['autre'] = SimpleNamespace(start=AsyncMock(), free=AsyncMock())
    await arbiter.execute('gpu', AsyncMock())
    await arbiter.execute('autre', AsyncMock())
    assert processus.commandes() == ['acquire']
    assert arbiter.active == 'autre'
    await arbiter.free('gpu')
    assert verrou.detenu
    await arbiter.free('autre')
    assert not verrou.detenu


@pytest.mark.asyncio
@pytest.mark.parametrize('etape', ['start', 'operation', 'guard'])
async def test_echec_sans_fuite_et_reprise(processus, etape):
    verrou = VerrouGpu()
    arbiter = arbitre(verrou)
    operation = AsyncMock()
    cible = {'start': arbiter.engines['gpu'].start, 'operation': operation,
             'guard': arbiter.guard.check}[etape]
    cible.side_effect = EngineError('Échec simulé')
    with pytest.raises(EngineError, match='simulé'):
        await arbiter.execute('gpu', operation)
    assert not verrou.detenu and arbiter.active is None and arbiter._prolongation is None
    cible.side_effect = None
    await arbiter.execute('gpu', AsyncMock())
    assert verrou.detenu
    await arbiter.close()
    assert not verrou.detenu


@pytest.mark.asyncio
async def test_annulation_acquisition_tue_sous_processus_et_nettoie(processus):
    processus.reponses['acquire'] = [(0, 100)]
    verrou = VerrouGpu()
    task = asyncio.create_task(verrou.acquerir('test', 1))
    while not processus.processus:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processus.processus[0].tue and processus.processus[0].termine.is_set()
    assert not verrou.detenu
    assert processus.commandes() == ['acquire', 'release', 'cancel']


@pytest.mark.asyncio
async def test_timeout_borne_et_nettoyage(processus, monkeypatch):
    verrou = VerrouGpu(attente_s=1)
    vrai_wait_for = asyncio.wait_for

    async def attendre(awaitable, timeout):
        return await vrai_wait_for(awaitable, .01 if timeout == 31 else timeout)

    monkeypatch.setattr('vertia.gpu.verrou.asyncio.wait_for', attendre)
    processus.reponses['acquire'] = [(0, 100)]
    with pytest.raises(GpuOccupe, match='Délai'):
        await verrou.acquerir('test', 1)
    assert not verrou.detenu and processus.processus[0].tue


@pytest.mark.asyncio
async def test_prolongation_unique_pendant_travail_et_echec(processus):
    verrou = VerrouGpu()
    arbiter = arbitre(verrou)
    arbiter.prolongation_seconds = .01

    async def operation():
        while processus.commandes().count('extend') < 2:
            await asyncio.sleep(.005)

    await asyncio.wait_for(arbiter.execute('gpu', operation), 1)
    assert verrou.detenu
    processus.reponses['extend'] = [(6, 0)]
    with pytest.raises(VerrouIndisponible):
        await asyncio.wait_for(arbiter.execute('gpu', lambda: asyncio.sleep(10)), 1)
    assert not verrou.detenu and arbiter.active is None and arbiter._prolongation is None


@pytest.mark.asyncio
async def test_pas_de_jeton_pour_moteur_nul_ou_cpu(processus):
    verrou = VerrouGpu()
    engines = {name: SimpleNamespace(memory=MemoryNeeds(vram_mb=0), start=AsyncMock(), free=AsyncMock())
               for name in ['sans_gpu', 'cpu']}
    arbiter = arbitre(verrou, engines=engines)
    for name in engines:
        await arbiter.execute(name, AsyncMock())
    await arbiter.close()
    assert not processus.appels


@pytest.mark.asyncio
async def test_annulation_travail_libere_avant_retour(processus):
    verrou = VerrouGpu()
    arbiter = arbitre(verrou)
    entree = asyncio.Event()

    async def operation():
        entree.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(arbiter.execute('gpu', operation))
    await entree.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not verrou.detenu and arbiter._prolongation is None
    assert arbiter.travaux_actifs == 0


@pytest.mark.asyncio
async def test_annulations_repetees_attendent_nettoyage(processus):
    processus.reponses['release'] = [(0, .03)]
    verrou = VerrouGpu()
    arbiter = arbitre(verrou)
    entree = asyncio.Event()

    async def operation():
        entree.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(arbiter.execute('gpu', operation))
    await entree.wait()
    task.cancel()
    while 'release' not in processus.commandes():
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not verrou.detenu and arbiter._prolongation is None
    assert all(proc.termine.is_set() for proc in processus.processus)


@pytest.mark.asyncio
@pytest.mark.parametrize('code', [0, 5, 6])
async def test_release_accepte_codes_sans_jeton(processus, code):
    verrou = VerrouGpu()
    await verrou.acquerir('test', 1)
    processus.reponses['release'] = [(code, 0)]
    await verrou.liberer()
    assert not verrou.detenu


@pytest.mark.asyncio
async def test_lancement_impossible_erreur_typee(monkeypatch):
    monkeypatch.setattr('vertia.gpu.verrou.asyncio.create_subprocess_exec',
                        AsyncMock(side_effect=OSError('indisponible')))
    verrou = VerrouGpu()
    with pytest.raises(VerrouIndisponible):
        await verrou.acquerir('test', 1)
    assert not verrou.detenu


@pytest.mark.asyncio
async def test_echec_prolongation_au_repos_nettoie(processus):
    verrou = VerrouGpu()
    arbiter = arbitre(verrou)
    arbiter.prolongation_seconds = .01
    await arbiter.execute('gpu', AsyncMock())
    renouvellement = arbiter._prolongation
    processus.reponses['extend'] = [(6, 0)]
    await asyncio.wait_for(renouvellement, 1)
    assert not verrou.detenu and arbiter.active is None and arbiter._prolongation is None


@pytest.mark.asyncio
@pytest.mark.parametrize('code,motif', [(4, 'gpu_occupe'), (7, 'pause')])
async def test_demandes_refus_et_file_continue(tmp_path, processus, code, motif):
    from test_demandes import creer_service, terminer

    service, jobs, _ = creer_service(tmp_path)
    outil, _ = service.outils['test.echo']
    outil.moteur = 'gpu'
    verrou = VerrouGpu()
    jobs.arbiter.verrou = verrou
    jobs.arbiter.engines['gpu'] = SimpleNamespace(start=AsyncMock(), free=AsyncMock())
    processus.reponses['acquire'] = [(code, 0), (0, 0)]
    premier = service.creer('creation_llm', 'test.echo', {'texte': 'un'})
    second = service.creer('worldmodel', 'test.echo', {'texte': 'deux'})
    await terminer(service, jobs)
    assert service.get(premier)['etat'] == 'echec'
    assert service.get(premier)['motif_code'] == motif
    assert service.get(second)['etat'] == 'livre'
    notes = [args[args.index('--note') + 1] for args in processus.appels if args[2] == 'acquire']
    assert 'creation_llm' in notes[0] and 'test.echo' in notes[0]
    assert 'worldmodel' in notes[1] and 'test.echo' in notes[1]
    assert note_demande.get() == ''
    await jobs.close()
    await jobs.arbiter.close()


def test_reglage_env_et_arret_application(settings, processus, monkeypatch):
    from test_chat import FakeOllama
    from test_jobs import FakeMonitor

    monkeypatch.setenv('VERTIA_VERROU_GPU', '1')
    monkeypatch.setenv('VERTIA_VERROU_GPU_ATTENTE_S', '123')
    config = Settings.from_env(local_config=settings.local_config)
    assert config.verrou_gpu and config.verrou_gpu_attente_s == 123
    verrou = VerrouGpu()
    engine = SimpleNamespace(start=AsyncMock(), free=AsyncMock())
    app = create_app(replace(settings, verrou_gpu=True), overrides={
        'ollama': FakeOllama(), 'monitor': FakeMonitor(), 'engines': {'comfy': engine}, 'verrou_gpu': verrou})
    with TestClient(app) as client:
        services = app.state.services
        client.portal.call(services.arbiter.execute, 'comfy', AsyncMock())
        assert verrou.detenu
    assert not verrou.detenu and services.arbiter._prolongation is None
    assert processus.commandes().count('release') == 1


def test_prechargement_ollama_coupe_par_variable(monkeypatch):
    from vertia.config import Settings
    monkeypatch.delenv('VERTIA_PRELOAD_OLLAMA', raising=False)
    assert Settings.from_env().preload_ollama is True
    monkeypatch.setenv('VERTIA_PRELOAD_OLLAMA', '0')
    assert Settings.from_env().preload_ollama is False


@pytest.mark.asyncio
async def test_jeton_pris_avant_la_garde_memoire(processus):
    verrou = VerrouGpu(attente_s=60)
    ordre = []

    async def garde(*args, **kwargs):
        ordre.append(('garde', verrou.detenu))

    moteur = SimpleNamespace(memory=MemoryNeeds(vram_mb=4096), start=AsyncMock(), free=AsyncMock())
    arbiter = GpuArbiter({'gpu': moteur}, SimpleNamespace(check=garde), idle_seconds=1, verrou=verrou)

    async def travail():
        return 'ok'

    assert await arbiter.execute('gpu', travail) == 'ok'
    assert ordre == [('garde', True)]
    await arbiter.close()
