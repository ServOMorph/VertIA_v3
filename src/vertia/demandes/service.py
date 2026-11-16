from __future__ import annotations

import ast
import asyncio
import inspect
import re
import shutil
import time
from pathlib import Path

from vertia.chemins import ROOT
from vertia.demandes.livraison import Livraison
from vertia.demandes.repository import DemandesRepository
from vertia.resources.monitor import MemoryRefused
from vertia.gpu.verrou import GpuOccupe, contextualiser
from vertia.tools.base import ParameterError


def sessions_connues():
    tree = ast.parse((ROOT / '_orchestration/vram_lock.py').read_text(encoding='utf-8-sig'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SESSIONS' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Liste des sessions introuvable.')


def construire(factory, settings, chemins, moteurs=None):
    if not inspect.isclass(factory) and hasattr(factory, 'valider'):
        return factory
    signature = inspect.signature(factory)
    if moteurs is not None:
        try:
            signature.bind(settings, chemins, moteurs)
        except TypeError:
            pass
        else:
            return factory(settings, chemins, moteurs)
    try:
        signature.bind(settings, chemins)
    except TypeError:
        signature.bind()
        return factory()
    return factory(settings, chemins)


class MoteurNul:
    async def start(self):
        pass

    async def free(self):
        pass

    async def stop(self):
        pass

    async def health(self):
        return True


class DemandesService:
    def __init__(self, db, jobs, registre, settings, chemins):
        self.repository = DemandesRepository(db)
        self.jobs, self.registre = jobs, registre
        self.livraison = Livraison(chemins.outbox_dir)
        self.sessions = sessions_connues()
        self.outils = {}
        self.tasks = {}
        self.locks = {}
        for module in registre.modules():
            try:
                for nom, factory in module.moteurs.items():
                    if nom in jobs.arbiter.engines:
                        raise ValueError(f'Moteur déjà enregistré : {nom}.')
                    jobs.arbiter.engines[nom] = construire(factory, settings, chemins)
                for factory in module.outils.values():
                    outil = construire(factory, settings, chemins, jobs.arbiter.engines)
                    capacite = outil.capacite
                    if capacite not in module.capacites or registre.capacites().get(capacite) is not module:
                        raise ValueError('Capacité non déclarée ou en conflit.')
                    if outil.moteur and outil.moteur not in jobs.arbiter.engines:
                        raise ValueError('Moteur de capacité indisponible.')
                    if not callable(outil.valider) or not callable(outil.executer):
                        raise ValueError('Contrat d’outil de capacité incomplet.')
                    self.outils[capacite] = (outil, module)
            except Exception as exc:
                registre.erreurs.append(f'{module.nom} : {type(exc).__name__} : {exc}')
        # Les opérations en mémoire ne sont jamais rejouées implicitement.
        with db.session() as conn:
            ids = [row[0] for row in conn.execute("SELECT id FROM demandes WHERE etat IN ('attente','actif','a_refaire')")]
            conn.execute("UPDATE essais SET etat='echec' WHERE etat IN ('attente','actif')")
        for demande_id in ids:
            self._etat(demande_id, 'echec', motif_code='moteur', erreur='Interruption du serveur.')
        self.purger()

    def purger(self):
        with self.repository.db.session() as conn:
            anciennes = conn.execute("SELECT id,session FROM demandes WHERE etat='valide' "
                                     "AND updated < datetime('now', '-30 days')").fetchall()
        outbox = self.livraison.outbox.resolve()
        for demande in anciennes:
            if not re.fullmatch(r'[a-z0-9_-]{1,40}', demande['session']) or not re.fullmatch(r'[a-f0-9]{32}', demande['id']):
                continue
            dossier = outbox / demande['session'] / demande['id']
            if dossier.is_dir() and dossier.resolve().is_relative_to(outbox):
                shutil.rmtree(dossier)
                self.livraison.journal(demande['id'], 'purge')

    def capacites(self):
        from dataclasses import asdict
        return [dict(capacite=capacite, module=module.nom, version=module.version,
                     parametres=getattr(outil, 'parameters', {}),
                     besoins={nom: asdict(besoin) for nom, besoin in module.besoins.items()})
                for capacite, (outil, module) in self.outils.items()]

    def _etat(self, demande_id, etat, **details):
        self.repository.update(demande_id, etat=etat, **details)
        self.livraison.journal(demande_id, etat, **details)

    def get(self, demande_id):
        return self.repository.get(demande_id)

    def creer(self, session, capacite, params, critere='', essais_max=3):
        if not re.fullmatch(r'[a-z0-9_-]{1,40}', session):
            raise ParameterError('Identifiant de session invalide.')
        if session not in self.sessions:
            raise LookupError('Session inconnue.')
        if capacite not in self.outils:
            raise ParameterError('Capacité indisponible.')
        if type(essais_max) is not int or not 1 <= essais_max <= 5:
            raise ParameterError('Le nombre d’essais doit être compris entre 1 et 5.')
        outil, _ = self.outils[capacite]
        params = outil.valider(dict(params))
        if not isinstance(params, dict):
            raise ParameterError('Les paramètres validés doivent être un objet.')
        demande_id = self.repository.create(session, capacite, params, critere, essais_max)
        self.livraison.journal(demande_id, 'creation', session=session, capacite=capacite,
                              params=params, critere=critere, essais_max=essais_max,
                              analyse_requise=self.get(demande_id)['analyse_requise'])
        self._lancer(demande_id)
        return demande_id

    def _lancer(self, demande_id, motif=''):
        demande = self.get(demande_id)
        outil, module = self.outils[demande['capacite']]
        if not outil.moteur:
            self.jobs.arbiter.engines.setdefault('sans_gpu', MoteurNul())
        numero = self.repository.add_essai(demande_id, demande['params'], module, motif)

        async def operation():
            self._etat(demande_id, 'actif')
            self.repository.essai(demande_id, numero, etat='actif')
            travail = self.livraison.outbox / '.travail' / demande_id / str(numero)
            travail.mkdir(parents=True, exist_ok=True)
            debut = time.monotonic()
            if inspect.iscoroutinefunction(outil.executer):
                fichiers = await outil.executer(dict(demande['params']), travail)
            else:
                execution = asyncio.create_task(asyncio.to_thread(outil.executer, dict(demande['params']), travail))
                try:
                    fichiers = await asyncio.shield(execution)
                except asyncio.CancelledError:
                    await asyncio.gather(execution, return_exceptions=True)
                    raise
                if inspect.isawaitable(fichiers):
                    fichiers = await fichiers
            duree = time.monotonic() - debut
            chemins = self.livraison.livrer(demande, numero, fichiers, travail, module, duree)
            self.repository.essai(demande_id, numero, etat='livre', chemins=chemins, duree=duree)
            self._etat(demande_id, 'livre')

        contextualiser(operation, f"session {demande['session']} ; capacité {demande['capacite']}")
        try:
            job_id = self.jobs.submit('demande', outil.moteur or 'sans_gpu',
                                      payload={'demande_id': demande_id, 'numero': numero}, operation=operation)
        except Exception:
            self.repository.essai(demande_id, numero, etat='echec')
            self._etat(demande_id, 'echec', motif_code='moteur', erreur='Soumission du job impossible.')
            return
        self.repository.essai(demande_id, numero, job_id=job_id)
        future = asyncio.get_running_loop().create_future()
        self.jobs.waiters[job_id] = future

        async def observer():
            try:
                await asyncio.shield(future)
            except asyncio.CancelledError:
                self.repository.essai(demande_id, numero, etat='annule')
                self._etat(demande_id, 'annule')
            except Exception as exc:
                code = 'gpu_occupe' if isinstance(exc, (MemoryRefused, GpuOccupe)) else 'moteur'
                if getattr(exc, 'motif_code', None) == 'pause':
                    code = 'pause'
                self.repository.essai(demande_id, numero, etat='echec')
                self._etat(demande_id, 'echec', motif_code=code, erreur=str(exc))
            finally:
                self.jobs.waiters.pop(job_id, None)

        self.tasks[demande_id] = asyncio.create_task(observer())

    async def retour(self, demande_id, verdict, motif=''):
        async with self.locks.setdefault(demande_id, asyncio.Lock()):
            return await self._retour(demande_id, verdict, motif)

    async def _retour(self, demande_id, verdict, motif):
        demande = self.get(demande_id)
        if verdict not in {'valide', 'a_refaire'}:
            raise ParameterError('Verdict invalide.')
        if demande['etat'] != 'livre':
            raise ValueError('Le retour exige une demande livrée.')
        if task := self.tasks.get(demande_id):
            await task
        numero = len(demande['essais'])
        self.repository.retour(demande_id, numero, verdict, motif)
        self.livraison.journal(demande_id, 'retour', verdict=verdict, motif=motif, numero=numero)
        if verdict == 'valide':
            self._etat(demande_id, 'valide')
        else:
            refus = sum(retour['verdict'] == 'a_refaire' for retour in demande['retours']) + 1
            self.repository.update(demande_id, analyse_requise=int(demande['analyse_requise'] or refus >= 2))
            if refus >= 2:
                self.livraison.journal(demande_id, 'analyse', analyse_requise=True)
            self._etat(demande_id, 'plafond' if numero >= demande['essais_max'] else 'a_refaire')
            if numero < demande['essais_max']:
                self._lancer(demande_id, motif)
        return self.get(demande_id)

    async def annuler(self, demande_id):
        async with self.locks.setdefault(demande_id, asyncio.Lock()):
            return await self._annuler(demande_id)

    async def _annuler(self, demande_id):
        demande = self.get(demande_id)
        if demande['etat'] in {'valide', 'plafond', 'echec', 'annule'}:
            raise ValueError('La demande est déjà terminée.')
        if demande['essais']:
            await self.jobs.cancel(demande['essais'][-1]['job_id'])
        if task := self.tasks.get(demande_id):
            await task
        self._etat(demande_id, 'annule')
        return self.get(demande_id)

    async def close(self):
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
