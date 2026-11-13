from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

import httpx

from vertia.engines.process import ProcessOwner


class OllamaService(ProcessOwner):
    """Supervise le service HTTP local, sans charger de modèle ni prendre le GPU."""

    def __init__(self, url, events, executable='', autostart=True, client=None, launcher=None):
        super().__init__('du service Ollama')
        self.url, self.events = url, events
        self.executable, self.autostart = executable, autostart
        self.client = client or httpx.AsyncClient(
            base_url=url, timeout=httpx.Timeout(2, connect=5), trust_env=False, follow_redirects=False)
        self.launcher = launcher or subprocess.Popen
        self.task = None
        self.state = dict(etat='demarrage', message='Ollama : vérification du service…', modeles_charges=None, revision=0)

    def update(self, state, message, loaded=None):
        value = dict(etat=state, message=message, modeles_charges=loaded)
        if any(self.state.get(key) != item for key, item in value.items()):
            self.state = dict(self.state, **value, revision=self.state['revision'] + 1)
            self.events.publish('ollama.etat', self.state)

    def update_preload(self, status):
        self.state = dict(self.state, prechargement=status, revision=self.state['revision'] + 1)
        self.events.publish('ollama.etat', self.state)

    async def available(self):
        response = await self.client.get('/api/tags')
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as error:
            raise ValueError('Le port configuré ne répond pas comme Ollama.') from error
        if not isinstance(data, dict) or not isinstance(data.get('models'), list):
            raise ValueError('La réponse du service ne correspond pas à Ollama.')

    def command(self):
        if self.executable:
            candidate = Path(self.executable)
            if candidate.is_absolute() and candidate.is_file():
                return str(candidate)
        else:
            found = shutil.which('ollama')
            if found:
                return found
            local = os.environ.get('LOCALAPPDATA')
            if local:
                candidate = Path(local) / 'Programs' / 'Ollama' / 'ollama.exe'
                if candidate.is_file():
                    return str(candidate)
        raise ValueError('Ollama introuvable. Installez Ollama ou renseignez VERTIA_OLLAMA_EXECUTABLE dans .env puis relancez VertIA.')

    def launch(self):
        url = urlsplit(self.url)
        if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', '::1'}
                or url.username or url.password or url.path not in {'', '/'} or url.query or url.fragment):
            raise ValueError('Le démarrage automatique exige une adresse HTTP locale Ollama sans chemin ni identifiants.')
        port = url.port or 80
        env = dict(os.environ, OLLAMA_HOST=url.netloc)
        if not 1 <= port <= 65535:
            raise ValueError('Port Ollama invalide.')
        self.process = self.launcher(
            [self.command(), 'serve'], env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )

    async def ensure(self):
        self.update('demarrage', 'Ollama : vérification du service…')
        try:
            await self.available()
        except httpx.ConnectError:
            if not self.autostart:
                raise ValueError('Ollama indisponible ; le démarrage automatique est désactivé dans .env.')
            self.launch()
            self.update('demarrage', 'Ollama : démarrage automatique en cours…')
            async with asyncio.timeout(30):
                while True:
                    try:
                        await self.available()
                        return
                    except httpx.ConnectError:
                        if self.process.poll() is not None:
                            raise ValueError('Ollama s’est arrêté au démarrage. Vérifiez son installation et le port configuré.')
                        await asyncio.sleep(.5)

    async def inspect(self):
        await self.available()
        try:
            response = await self.client.get('/api/ps')
            response.raise_for_status()
            rows = response.json()['models']
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError('État des modèles invalide.')
            loaded = [row.get('name') or row.get('model') for row in rows]
            if any(not isinstance(name, str) or not name for name in loaded):
                raise ValueError('Noms des modèles invalides.')
        except (httpx.HTTPError, ValueError, KeyError, AttributeError, TypeError):
            self.update('pret', 'Ollama disponible · état des modèles inconnu.')
            return
        self.update('pret', 'Ollama disponible', loaded)

    async def run(self):
        try:
            await self.ensure()
        except ValueError as error:
            self.update('erreur', str(error))
        except TimeoutError:
            self.update('erreur', 'Ollama ne répond pas après 30 secondes. Vérifiez son installation et le port configuré.')
        except (httpx.HTTPError, OSError):
            self.update('erreur', 'Ollama indisponible. Vérifiez l’installation, le port et les réglages, puis relancez VertIA.')
        while True:
            try:
                await self.inspect()
            except (httpx.HTTPError, ValueError, KeyError, AttributeError):
                if self.state['etat'] != 'erreur':
                    self.update('erreur', 'Ollama indisponible. Relancez VertIA pour réessayer le démarrage automatique.')
            await asyncio.sleep(3)

    def start_background(self):
        if self.task is None:
            self.task = asyncio.create_task(self.run())

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        try:
            await self.stop()
        finally:
            await self.client.aclose()
