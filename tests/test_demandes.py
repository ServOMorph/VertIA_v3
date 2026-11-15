from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from vertia.chemins import resoudre_chemins
from vertia.core.db import Database
from vertia.core.db import MIGRATIONS
from vertia.core.events import EventBus
from vertia.demandes import DemandesService
from vertia.jobs.arbiter import GpuArbiter
from vertia.jobs.queue import JobQueue
from vertia.modules.registry import RegistreModules
from vertia.modules.contrat import Module
from vertia.resources.monitor import MemoryRefused

FIXTURES = Path(__file__).parent / 'fixtures/modules'


def creer_service(tmp_path):
    db = Database(tmp_path / 'test.db')
    db.initialize()
    guard = SimpleNamespace(check=AsyncMock())
    jobs = JobQueue(db, GpuArbiter({}, guard), EventBus())
    registre = RegistreModules(FIXTURES)
    service = DemandesService(db, jobs, registre, None, resoudre_chemins(tmp_path, environ={}))
    return service, jobs, guard


async def terminer(service, jobs):
    if jobs.worker:
        await asyncio.wait_for(asyncio.shield(jobs.worker), 3)
    await asyncio.gather(*service.tasks.values())


@pytest.mark.asyncio
async def test_livraison_retour_plafond_journal_et_analyse(tmp_path):
    service, jobs, _ = creer_service(tmp_path)
    demande_id = service.creer('vertia', 'test.echo', {'texte': 'oui', 'echec_jusqu_a': 2})
    await terminer(service, jobs)
    demande = service.get(demande_id)
    assert demande['etat'] == 'livre' and demande['analyse_requise']
    assert Path(demande['chemins'][0]).read_text() == 'mauvais'
    await service.retour(demande_id, 'a_refaire', 'contenu incorrect')
    await terminer(service, jobs)
    await service.retour(demande_id, 'a_refaire', 'encore incorrect')
    await terminer(service, jobs)
    demande = service.get(demande_id)
    assert Path(demande['chemins'][0]).read_text() == 'oui'
    assert [e['motif'] for e in demande['essais']] == ['', 'contenu incorrect', 'encore incorrect']
    assert all(e['params'] == demande['params'] for e in demande['essais'])
    metadata = json.loads(Path(demande['chemins'][0]).with_suffix('.json').read_text())
    assert metadata['module'] == 'factice' and metadata['version'] == '1.0.0'
    assert metadata['params'] == demande['params'] and metadata['duree'] >= 0
    await service.retour(demande_id, 'a_refaire', 'refus final')
    assert service.get(demande_id)['etat'] == 'plafond'
    events = [json.loads(line) for line in (tmp_path / 'outbox/journal.jsonl').read_text(encoding='utf-8').splitlines()]
    assert events[-1]['evenement'] == 'plafond'
    autre = service.creer('vertia', 'test.echo', {'texte': 'nouveau'})
    assert not service.get(autre)['analyse_requise']
    await terminer(service, jobs)
    await service.retour(autre, 'a_refaire')
    await terminer(service, jobs)
    assert not service.get(autre)['analyse_requise']
    await service.retour(autre, 'a_refaire')
    assert service.get(autre)['analyse_requise']
    await terminer(service, jobs)
    await service.retour(autre, 'valide')
    assert service.get(autre)['etat'] == 'valide'
    with pytest.raises(ValueError):
        await service.retour(autre, 'a_refaire')
    assert all(job['kind'] == 'demande' for job in jobs.list())
    await jobs.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,code', [('gpu', 'gpu_occupe'), ('moteur', 'moteur'), ('pause', 'pause')])
async def test_erreurs_avant_et_pendant_operation(tmp_path, mode, code):
    service, jobs, guard = creer_service(tmp_path)
    if mode == 'gpu':
        guard.check.side_effect = MemoryRefused('Occupé')
    elif mode == 'pause':
        erreur = RuntimeError('Pause')
        erreur.motif_code = 'pause'
        guard.check.side_effect = erreur
    demande_id = service.creer('vertia', 'test.echo', {'texte': 'oui', 'erreur': mode == 'moteur'})
    await terminer(service, jobs)
    demande = service.get(demande_id)
    assert demande['etat'] == 'echec' and demande['motif_code'] == code
    assert demande['essais'][0]['etat'] == 'echec' and not demande['chemins']
    await jobs.close()


@pytest.mark.asyncio
async def test_annulation_attente_et_active(tmp_path):
    service, jobs, _ = creer_service(tmp_path)
    premier = service.creer('vertia', 'test.echo', {'texte': 'un', 'delai': 30})
    second = service.creer('vertia', 'test.echo', {'texte': 'deux'})
    await service.annuler(second)
    for _ in range(100):
        if service.get(premier)['etat'] == 'actif':
            break
        await asyncio.sleep(.01)
    assert service.get(premier)['etat'] == 'actif'
    await service.annuler(premier)
    await terminer(service, jobs)
    assert service.get(premier)['etat'] == service.get(second)['etat'] == 'annule'
    assert not service.get(premier)['chemins']
    await jobs.close()


@pytest.mark.asyncio
async def test_reprise_signale_interruption_sans_rejouer(tmp_path):
    service, jobs, _ = creer_service(tmp_path)
    demande_id = service.creer('vertia', 'test.echo', {'texte': 'un'})
    await terminer(service, jobs)
    service.repository.update(demande_id, etat='actif')
    restored = DemandesService(jobs.db, jobs, service.registre, None, resoudre_chemins(tmp_path, environ={}))
    assert restored.get(demande_id)['etat'] == 'echec'
    await jobs.close()


@pytest.mark.asyncio
async def test_livraison_refuse_fichier_hors_travail(tmp_path):
    service, jobs, _ = creer_service(tmp_path)
    outil, _ = service.outils['test.echo']
    externe = tmp_path / 'externe.txt'
    externe.write_text('secret')
    outil.executer = AsyncMock(return_value=[externe])
    demande_id = service.creer('vertia', 'test.echo', {'texte': 'un'})
    await terminer(service, jobs)
    assert service.get(demande_id)['etat'] == 'echec'
    assert not service.get(demande_id)['chemins']
    await jobs.close()


@pytest.mark.asyncio
async def test_retours_concurrents_un_seul_accepte(tmp_path):
    service, jobs, _ = creer_service(tmp_path)
    demande_id = service.creer('vertia', 'test.echo', {'texte': 'un'})
    await terminer(service, jobs)
    results = await asyncio.gather(service.retour(demande_id, 'a_refaire'),
                                   service.retour(demande_id, 'valide'), return_exceptions=True)
    assert sum(isinstance(result, ValueError) for result in results) == 1
    await terminer(service, jobs)
    assert len(service.get(demande_id)['retours']) == 1
    assert len(service.get(demande_id)['essais']) == 2
    await jobs.close()


@pytest.mark.asyncio
async def test_outil_synchrone_et_retention_validees_seulement(tmp_path):
    service, jobs, _ = creer_service(tmp_path)
    outil, _ = service.outils['test.echo']

    def executer(params, dossier):
        fichier = dossier / 'echo.txt'
        fichier.write_text(params['texte'])
        return [fichier]

    outil.executer = executer
    valide = service.creer('vertia', 'test.echo', {'texte': 'un'})
    livre = service.creer('vertia', 'test.echo', {'texte': 'deux'})
    await terminer(service, jobs)
    await service.retour(valide, 'valide')
    with jobs.db.session() as conn:
        conn.execute("UPDATE demandes SET updated=datetime('now','-31 days')")
    service.purger()
    assert not Path(service.get(valide)['chemins'][0]).exists()
    assert Path(service.get(livre)['chemins'][0]).exists()
    assert service.get(valide)['etat'] == 'valide'
    await jobs.close()


def test_migration_demandes_preserve_les_donnees_existantes(tmp_path):
    db = Database(tmp_path / 'ancien.db')
    with db.session() as conn:
        for migration in MIGRATIONS[:-1]:
            conn.executescript(migration)
        conn.execute(f'PRAGMA user_version = {len(MIGRATIONS) - 1}')
        conn.execute("INSERT INTO dossiers(id,nom,system_prompt) VALUES ('f','Ancien','Instructions')")
    assert db.initialize() == len(MIGRATIONS)
    assert db.initialize() == len(MIGRATIONS)
    with db.session() as conn:
        assert conn.execute("SELECT nom FROM dossiers WHERE id='f'").fetchone()[0] == 'Ancien'
        for table in ('demandes', 'essais', 'retours'):
            assert conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


@pytest.mark.asyncio
async def test_fabriques_settings_chemins_et_moteur_module(tmp_path):
    service, jobs, _ = creer_service(tmp_path)
    outil, _ = service.outils['test.echo']
    outil.moteur = 'factice_gpu'
    moteur = SimpleNamespace(start=AsyncMock(), free=AsyncMock())
    settings = object()
    chemins = resoudre_chemins(tmp_path, environ={})

    def fabrique(config, paths):
        assert config is settings and paths is chemins
        return moteur

    module = Module(nom='factice_gpu', activite='outil', titre='Test', version='1.0.0',
                    capacites=['test.echo'], moteurs={'factice_gpu': fabrique}, outils={'echo': outil})
    registre = RegistreModules(tmp_path / 'absent')
    registre._modules[module.nom] = module
    registre._capacites['test.echo'] = module
    service = DemandesService(jobs.db, jobs, registre, settings, chemins)
    assert not registre.erreurs
    demande_id = service.creer('vertia', 'test.echo', {'texte': 'un'})
    await terminer(service, jobs)
    assert service.get(demande_id)['etat'] == 'livre'
    moteur.start.assert_awaited_once()
    assert jobs.list()[0]['engine'] == 'factice_gpu'
    await jobs.close()
