from __future__ import annotations

import asyncio

from vertia.resources.monitor import MemoryRefused


class OllamaPreload:
    """Précharge une seule fois le modèle par défaut, via la file GPU."""

    def __init__(self, service, client, jobs, model):
        self.service, self.client, self.jobs, self.model = service, client, jobs, model
        self.task = None

    def status(self, state, message):
        self.service.update_preload(dict(etat=state, modele=self.model, message=message))

    async def run(self):
        try:
            while self.service.state['etat'] != 'pret':
                await asyncio.sleep(.2)
            models = await self.client.models()
            if self.model not in {item.get('name') or item.get('model') for item in models}:
                self.status('erreur', f'Préchargement impossible : {self.model} n’est pas installé. Choisissez un modèle installé dans Accueil et réglages, puis redémarrez VertIA.')
                return
            self.status('attente', f'{self.model} : préchargement en attente du GPU…')

            async def load():
                self.status('chargement', f'{self.model} : chargement en cours…')
                await self.client.prepare_model(self.model)
                loading = asyncio.create_task(self.client.load_model(self.model))
                cancelled = False
                while not loading.done():
                    try:
                        await asyncio.shield(loading)
                    except asyncio.CancelledError:
                        cancelled = True
                        self.status('chargement', f'{self.model} : annulation en attente de la fin du chargement…')
                loading.result()
                if cancelled:
                    await self.client.unload_model(self.model)
                    raise asyncio.CancelledError

            await self.jobs.run('prechargement_ollama', 'ollama', load, priority=100, memory_request=self.model)
            self.status('termine', '')
            await self.service.inspect()
        except asyncio.CancelledError:
            self.status('annule', 'Préchargement annulé. Le modèle sera chargé à la prochaine demande.')
            raise
        except MemoryRefused as error:
            self.status('erreur', f'Préchargement refusé : {error}')
        except Exception:
            self.status('erreur', f'Préchargement de {self.model} impossible. Consultez Mémoire et file, ou réessayez en envoyant votre message.')

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self.run())

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
