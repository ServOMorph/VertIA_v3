from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from vertia.resources.monitor import MemoryRefused
from vertia.engines.base import EngineError


class JobQueue:
    def __init__(self, db, arbiter, events):
        self.db, self.arbiter, self.events = db, arbiter, events
        self.handlers = {}
        self.operations = {}
        self.memory_requests = {}
        self.waiters = {}
        self.worker = None
        self.task = None
        self.active = None
        self.closed = False
        with db.session() as conn:
            conn.execute("UPDATE jobs SET status='interrompu', error='Interruption du serveur ; relance explicite nécessaire.' WHERE status='actif'")
            conn.execute("UPDATE jobs SET status='interrompu', error='Cette tâche ne peut pas être rejouée après redémarrage.' WHERE status='attente' AND resumable=0")

    def register(self, kind, handler):
        if kind in self.handlers:
            raise ValueError('Type de job déjà enregistré.')
        self.handlers[kind] = handler

    def list(self):
        with self.db.session() as conn:
            rows = conn.execute('SELECT * FROM jobs ORDER BY created DESC, rowid DESC LIMIT 200').fetchall()
        return [self._decode(row) for row in rows]

    def get(self, job_id):
        with self.db.session() as conn:
            row = conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise LookupError('Tâche introuvable.')
        return self._decode(row)

    @staticmethod
    def _decode(row):
        job = dict(row)
        job['payload'] = json.loads(job['payload'])
        return job

    def update(self, job_id, **values):
        allowed = {'status', 'progress', 'error', 'priority'}
        if not values or not values.keys() <= allowed:
            raise ValueError('Mise à jour de job invalide.')
        with self.db.session() as conn:
            conn.execute('UPDATE jobs SET ' + ','.join(f'{key}=?' for key in values) + ', revision=revision+1, updated=CURRENT_TIMESTAMP WHERE id=?', (*values.values(), job_id))
        self.events.publish('jobs.maj', self.get(job_id))

    def submit(self, kind, engine, payload=None, priority=0, operation=None, memory_request=None):
        if self.closed:
            raise ValueError('La file est arrêtée.')
        if engine not in self.arbiter.engines:
            raise ValueError('Moteur indisponible.')
        if operation is None and kind not in self.handlers:
            raise ValueError('Type de tâche indisponible.')
        with self.db.session() as conn:
            count = conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('attente','actif')").fetchone()[0]
            if count >= 100:
                raise ValueError('La file GPU est pleine. Attendez la fin des tâches.')
            job_id = uuid4().hex
            conn.execute('INSERT INTO jobs(id,kind,engine,payload,priority,resumable) VALUES(?,?,?,?,?,?)',
                         (job_id, kind, engine, json.dumps(payload or {}, ensure_ascii=False), priority, int(operation is None)))
        if operation:
            self.operations[job_id] = operation
        if memory_request is not None:
            self.memory_requests[job_id] = memory_request
        self.events.publish('jobs.maj', self.get(job_id))
        self.start()
        return job_id

    def start(self):
        if not self.closed and (self.worker is None or self.worker.done()):
            self.worker = asyncio.create_task(self._work())

    async def run(self, kind, engine, operation, priority=0, memory_request=None):
        job_id = self.submit(kind, engine, priority=priority, operation=operation, memory_request=memory_request)
        future = asyncio.get_running_loop().create_future()
        self.waiters[job_id] = future
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            await self.cancel(job_id)
            raise
        finally:
            self.waiters.pop(job_id, None)

    async def _work(self):
        while not self.closed:
            with self.db.session() as conn:
                row = conn.execute("SELECT * FROM jobs WHERE status='attente' ORDER BY priority DESC, rowid LIMIT 1").fetchone()
            if row is None:
                return
            job = self._decode(row)
            job_id = job['id']
            operation = self.operations.pop(job_id, None)
            memory_request = self.memory_requests.pop(job_id, None)
            if operation is None:
                handler = self.handlers.get(job['kind'])
                if handler is None:
                    self.update(job_id, status='interrompu', error='Type de tâche non disponible ; reprise différée.')
                    continue
                async def operation(handler=handler, job=job):
                    return await handler(job['payload'], lambda value: self.progress(job['id'], value))
            self.active = job_id
            self.update(job_id, status='actif', error='')
            self.task = asyncio.create_task(self.arbiter.execute(job['engine'], operation, memory_request=memory_request))
            try:
                result = await self.task
            except asyncio.CancelledError:
                self.update(job_id, status='interrompu' if self.closed else 'annule')
                self._settle(job_id, cancelled=True)
            except Exception as exc:
                error = ('Appel Ollama échoué ; consultez la discussion.'
                         if job['kind'] in {'chat', 'resume'} and not isinstance(exc, MemoryRefused) else str(exc))
                if job['kind'] == 'outil' and not isinstance(exc, (MemoryRefused, EngineError)):
                    error = 'Génération échouée ; vérifiez l’installation et les modèles du moteur concerné avant de relancer.'
                self.update(job_id, status='erreur', error=error)
                self._settle(job_id, error=exc)
            else:
                self.update(job_id, status='termine', progress=100)
                self._settle(job_id, result=result)
            finally:
                self.active = self.task = None

    def _settle(self, job_id, result=None, error=None, cancelled=False):
        future = self.waiters.get(job_id)
        if future and not future.done():
            if cancelled:
                future.cancel()
            elif error:
                future.set_exception(error)
            else:
                future.set_result(result)

    def progress(self, job_id, value):
        if self.get(job_id)['status'] == 'actif':
            self.update(job_id, progress=max(0, min(100, float(value))))

    async def cancel(self, job_id):
        job = self.get(job_id)
        if self.active == job_id and self.task:
            task = self.task
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            # Le worker persiste le statut avant le retour de l'annulation.
            await asyncio.sleep(0)
        elif job['status'] == 'attente':
            self.operations.pop(job_id, None)
            self.memory_requests.pop(job_id, None)
            self.update(job_id, status='annule')
            self._settle(job_id, cancelled=True)

    def prioritize(self, job_id, priority):
        if self.get(job_id)['status'] != 'attente':
            raise ValueError('Seules les tâches en attente peuvent changer de priorité.')
        self.update(job_id, priority=priority)

    def retry(self, job_id):
        job = self.get(job_id)
        if job['status'] not in {'erreur', 'interrompu', 'annule'} or not job['resumable'] or job['kind'] not in self.handlers:
            raise ValueError('Cette tâche ne peut pas être relancée ; renvoyez la demande depuis la discussion.')
        return self.submit(job['kind'], job['engine'], job['payload'], job['priority'])

    async def close(self):
        self.closed = True
        if self.task:
            self.task.cancel()
        if self.worker:
            await asyncio.gather(self.worker, return_exceptions=True)
        for job_id in list(self.operations):
            self.update(job_id, status='interrompu', error='Arrêt du serveur.')
            self._settle(job_id, cancelled=True)
        self.operations.clear()
        self.memory_requests.clear()
