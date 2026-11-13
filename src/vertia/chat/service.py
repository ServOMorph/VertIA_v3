from __future__ import annotations

import asyncio
import logging
from collections import deque
from uuid import uuid4

import httpx

from vertia.chat.context import ContextBuilder
from vertia.chat.repository import ChatRepository
from vertia.core.events import EventBus

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, repository: ChatRepository, ollama, events: EventBus, num_ctx: int, jobs=None):
        self.repository = repository
        self.ollama = ollama
        self.events = events
        self.context = ContextBuilder(num_ctx)
        self.pending: deque[dict] = deque()
        self.active: dict | None = None
        self.worker: asyncio.Task | None = None
        self.task: asyncio.Task | None = None
        self.maintenance: str | None = None
        self.summary_cancelled = False
        self.summaries: dict[str, tuple[list[dict], int]] = {}
        self.closed = False
        self.chunks: list[str] = []
        self.jobs = jobs
        self.orchestrator = None

    def messages(self, conv_id):
        messages = self.repository.messages(conv_id)
        if self.active and self.active['conversation_id'] == conv_id:
            for message in messages:
                if message['id'] == self.active['message_id']:
                    message['contenu'] = ''.join(self.chunks)
        return messages

    def busy(self, conv_id):
        return (self.active is not None and self.active['conversation_id'] == conv_id
                or any(j['conversation_id'] == conv_id for j in self.pending)
                or self.maintenance == conv_id)

    def state(self):
        return {'actif': self.active, 'attente': list(self.pending), 'resume': self.maintenance}

    def notify(self):
        self.events.publish('chat.file', self.state())

    def submit(self, conv_id: str, content: str):
        if self.closed:
            raise ValueError('Le chat est arrêté.')
        if len(self.pending) >= 100:
            raise ValueError('La file est pleine. Attendez la fin des messages en cours.')
        conv = self.repository.conversation(conv_id)
        if conv is None:
            raise LookupError('Conversation introuvable.')
        folder = self.repository.folder(conv['dossier_id']) if conv['dossier_id'] else None
        self.context.build(conv['modele'], folder['system_prompt'] if folder else '', [], content, conv['resume'])
        user_id = self.repository.append(conv_id, 'user', content, 'attente')
        assistant_id = self.repository.append(conv_id, 'assistant', '', 'attente')
        job = dict(id=uuid4().hex, conversation_id=conv_id, user_id=user_id, message_id=assistant_id)
        self.pending.append(job)
        if conv['titre'] == 'Nouvelle discussion':
            self.repository.update_conversation(conv_id, titre=' '.join(content.split()[:6])[:80])
        if self.maintenance and self.task:
            self.task.cancel()
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._work())
        self.notify()
        return job

    async def _work(self):
        while not self.closed:
            if self.pending:
                job = self.pending.popleft()
                self.chunks = []
                self.active = job
                self.task = asyncio.create_task(self._generate(job))
                self.notify()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
                finally:
                    self.active = None
                    self.task = None
                    self.notify()
            elif self.summaries:
                conv_id, (history, target) = self.summaries.popitem()
                self.maintenance = conv_id
                self.summary_cancelled = False
                self.task = asyncio.create_task(self._summarize(conv_id, history, target))
                self.notify()
                try:
                    await self.task
                except asyncio.CancelledError:
                    if not self.closed and not self.summary_cancelled:
                        self.summaries[conv_id] = (history, target)
                except Exception:
                    logger.exception('Échec du résumé de conversation')
                    self.events.publish('chat.avertissement', {'conversation_id': conv_id, 'erreur': 'Résumé non actualisé ; les échanges restent consultables dans la discussion.'})
                finally:
                    self.maintenance = None
                    self.task = None
                    self.notify()
            else:
                return

    async def _generate(self, job):
        conv_id = job['conversation_id']
        chunks = self.chunks
        offset = 0
        status, error = 'termine', ''
        user = next(m for m in self.repository.messages(conv_id) if m['id'] == job['user_id'])
        self.repository.finish(conv_id, user['id'], user['contenu'], 'actif')
        self.repository.finish(conv_id, job['message_id'], '', 'actif')
        try:
            conv = self.repository.conversation(conv_id)
            folder = self.repository.folder(conv['dossier_id']) if conv['dossier_id'] else None
            history = self.repository.history(conv_id, user['id'])
            count = conv['resume_count']
            instruction = self.orchestrator.instruction(user['contenu']) if self.orchestrator else ''
            system = (folder['system_prompt'] if folder else '') + '\n' + instruction
            window = self.context.build(conv['modele'], system,
                                        history[count:], user['contenu'], conv['resume'])
            if window.omitted:
                self.summaries[conv_id] = (history, count + window.omitted)
            async def generate():
                nonlocal offset
                plan = []
                await self.ollama.prepare_model(conv['modele'])
                async for payload in self.ollama.chat_stream(conv['modele'], window.messages, self.context.response_margin):
                    chunk = payload.get('message', {}).get('content', '')
                    if chunk:
                        if instruction:
                            plan.append(chunk)
                        else:
                            chunks.append(chunk)
                            self.events.publish('chat.delta', {**job, 'contenu': chunk, 'offset': offset})
                            offset += len(chunk)
                    if payload.get('done'):
                        self.context.calibrate(conv['modele'], window.estimated, payload.get('prompt_eval_count', 0))
                if instruction:
                    text = self.orchestrator.propose(conv_id, job['message_id'], ''.join(plan), user['contenu'])
                    chunks.append(text)
                    self.events.publish('chat.delta', {**job, 'contenu': text, 'offset': 0})
            if self.jobs:
                await self.jobs.run('chat', 'ollama', generate, memory_request=conv['modele'])
            else:
                await generate()
        except asyncio.CancelledError:
            status = 'arrete'
            raise
        except Exception as exc:
            status = 'erreur'
            error = ('Ollama est indisponible ou la requête a échoué.' if isinstance(exc, httpx.HTTPError) else str(exc))
            logger.exception('Échec du chat')
        finally:
            self.repository.finish(conv_id, user['id'], user['contenu'], 'termine' if status in {'termine', 'arrete'} else status)
            self.repository.finish(conv_id, job['message_id'], ''.join(chunks), status, error)
            self.events.publish('chat.fin', {**job, 'statut': status, 'erreur': error})

    async def _summarize(self, conv_id: str, history: list[dict], target: int):
        conv = self.repository.conversation(conv_id)
        if conv is None:
            return
        count, summary = conv['resume_count'], conv['resume']
        instruction = 'Actualise le résumé en français : conserve les faits, décisions et contraintes. Réponds uniquement par le résumé, en 150 mots maximum.'
        while count < target:
            batch = []
            window = None
            for index in range(count, target, 2):
                candidate = batch + history[index:index + 2]
                text = '\n'.join(m['role'] + ': ' + m['contenu'] for m in candidate)
                try:
                    candidate_window = self.context.build(conv['modele'], instruction, [], text, summary)
                except ValueError:
                    break
                batch, window = candidate, candidate_window
            if not batch:
                batch = history[count:count + 2]
                text = '\n'.join(m['role'] + ': ' + m['contenu'] for m in batch)
                # Un échange peut être plus grand que l'entrée disponible du résumé.
                while text:
                    low, high, best = 1, len(text), 0
                    while low <= high:
                        middle = (low + high) // 2
                        try:
                            candidate = self.context.build(conv['modele'], instruction, [], text[:middle], summary)
                        except ValueError:
                            high = middle - 1
                        else:
                            best, window = middle, candidate
                            low = middle + 1
                    if best == 0:
                        raise ValueError('Le résumé ne laisse plus de place aux échanges suivants.')
                    summary = await self._complete_summary(conv['modele'], window)
                    text = text[best:]
            else:
                summary = await self._complete_summary(conv['modele'], window)
            count += len(batch)
            self.repository.update_conversation(conv_id, resume=summary, resume_count=count)

    async def _complete_summary(self, model, window):
        if self.jobs:
            return await self.jobs.run('resume', 'ollama', lambda: self._stream_summary(model, window), priority=-10,
                                       memory_request=model)
        return await self._stream_summary(model, window)

    async def _stream_summary(self, model, window):
        chunks = []
        await self.ollama.prepare_model(model)
        async for payload in self.ollama.chat_stream(model, window.messages, min(256, self.context.response_margin)):
            chunks.append(payload.get('message', {}).get('content', ''))
            if payload.get('done'):
                self.context.calibrate(model, window.estimated, payload.get('prompt_eval_count', 0))
        summary = ''.join(chunks).strip()
        if not summary:
            raise ValueError('Résumé vide.')
        return summary

    async def stop(self, conv_id: str):
        removed = [j for j in self.pending if j['conversation_id'] == conv_id]
        self.pending = deque(j for j in self.pending if j['conversation_id'] != conv_id)
        for job in removed:
            messages = self.repository.messages(conv_id)
            user = next(m for m in messages if m['id'] == job['user_id'])
            self.repository.finish(conv_id, user['id'], user['contenu'], 'annule')
            self.repository.finish(conv_id, job['message_id'], '', 'annule')
            self.events.publish('chat.fin', {**job, 'statut': 'annule', 'erreur': ''})
        if self.active and self.active['conversation_id'] == conv_id and self.task:
            task = self.task
            # Laisser le coroutine entrer dans son try/finally avant l'annulation.
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.summaries.pop(conv_id, None)
        if self.maintenance == conv_id and self.task:
            self.summary_cancelled = True
            task = self.task
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.notify()

    async def close(self):
        self.closed = True
        for conv_id in {j['conversation_id'] for j in self.pending} | ({self.active['conversation_id']} if self.active else set()):
            await self.stop(conv_id)
        if self.task:
            self.task.cancel()
        if self.worker:
            await asyncio.gather(self.worker, return_exceptions=True)
        await self.ollama.close()
        self.repository.ephemeral.clear()
