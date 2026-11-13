from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess

import httpx

from vertia.engines.base import EngineError, MemoryNeeds
from vertia.engines.process import ProcessOwner


class AceStepEngine(ProcessOwner):
    memory = MemoryNeeds(note='Offload CPU ; besoins RAM et VRAM à mesurer sur le matériel réel.')

    def __init__(self, directory: Path, port: int, client=None, launcher=subprocess.Popen):
        super().__init__('ACE-Step')
        self.directory, self.port = directory, port
        self.client = client or httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', timeout=15, trust_env=False)
        self.launcher = launcher

    async def health(self):
        try:
            response = await self.client.get('/health', timeout=2)
            response.raise_for_status()
            data = response.json().get('data', {})
            return data.get('status') == 'ok' and data.get('service') == 'ACE-Step API'
        except (httpx.HTTPError, ValueError, AttributeError):
            return False

    async def start(self):
        if self.stopping:
            await self.stop()
        if await self.health():
            if not self.owned():
                raise EngineError('ACE-Step est déjà lancé hors de VertIA. Arrêtez cette instance pour réserver le GPU à VertIA.')
            return
        if self.owned():
            await self.stop()
        python = self.directory / '.venv' / 'Scripts' / 'python.exe'
        if not python.is_file() or not (self.directory / 'acestep' / 'api_server.py').is_file():
            raise EngineError('Installation ACE-Step introuvable. Vérifiez VERTIA_ACESTEP_DIR.')
        env = dict(os.environ, ACESTEP_CONFIG_PATH='acestep-v15-turbo', ACESTEP_OFFLOAD_TO_CPU='true',
                   ACESTEP_LM_BACKEND='pt', ACESTEP_INIT_LLM='false', PYTHONDONTWRITEBYTECODE='1')
        self.process = self.launcher(
            [str(python), '-B', 'acestep/api_server.py', '--host', '127.0.0.1', '--port', str(self.port)],
            cwd=self.directory, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            async with asyncio.timeout(600):
                while not await self.health():
                    if self.process.poll() is not None:
                        raise EngineError('ACE-Step s’est arrêté au démarrage. Vérifiez son installation et ses modèles.')
                    await asyncio.sleep(1)
        except BaseException:
            await self.stop()
            raise

    async def free(self):
        if self.process is not None or self.stopping:
            await self.stop()
        elif await self.health():
            raise EngineError('ACE-Step externe ne peut pas être déchargé par API. Arrêtez cette instance avant de changer de moteur.')

    async def generate(self, params, progress):
        if not self.owned():
            raise EngineError('ACE-Step doit être démarré par VertIA avant la génération.')
        complete = False
        try:
            response = await self.client.post('/release_task', json={
                'prompt': params['caption'], 'lyrics': '' if params['instrumental'] else params['paroles'],
                'vocal_language': 'unknown' if params['instrumental'] else params['langue'],
                'audio_duration': params['duree'], 'bpm': params['bpm'],
                'inference_steps': 8, 'batch_size': 1, 'audio_format': 'mp3',
                'thinking': False, 'use_format': False, 'sample_mode': False,
                'lm_backend': 'pt', 'use_cot_caption': False, 'use_cot_language': False,
                'use_random_seed': False, 'seed': params['seed'],
            })
            response.raise_for_status()
            task_id = response.json()['data']['task_id']
            if not isinstance(task_id, str) or not task_id:
                raise ValueError('Identifiant absent.')
            progress(5)
            async with asyncio.timeout(900):
                while True:
                    response = await self.client.post('/query_result', json={'task_id_list': [task_id]})
                    response.raise_for_status()
                    records = response.json()['data']
                    record = next((row for row in records if row.get('task_id') == task_id), None)
                    if record:
                        if record['status'] == 2:
                            raise EngineError('Génération musicale refusée par ACE-Step. Vérifiez ses modèles et paramètres.')
                        rows = json.loads(record['result'])
                        if record['status'] == 1:
                            if len(rows) != 1 or not isinstance(rows[0].get('file'), str) or not rows[0]['file']:
                                raise ValueError('Résultat audio absent.')
                            progress(100)
                            complete = True
                            return {'task_id': task_id, 'audios': [rows[0]['file']]}
                        if rows and isinstance(rows[0], dict):
                            value = rows[0].get('progress')
                            if isinstance(value, (int, float)) and 0 <= value <= 1:
                                progress(max(5, min(95, value * 100)))
                    await asyncio.sleep(1)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, TimeoutError) as exc:
            raise EngineError('ACE-Step indisponible, réponse incompatible ou délai musical dépassé (15 minutes).') from exc
        finally:
            # Aucun endpoint d’annulation : attendre l’arrêt effectif avant de céder le GPU.
            if not complete:
                await self.stop()

    async def preview(self, audio):
        if not isinstance(audio, str) or not audio or len(audio) > 4096:
            raise ValueError('Référence audio invalide.')
        async with self.client.stream('GET', '/v1/audio', params={'path': audio}) as response:
            response.raise_for_status()
            if response.headers.get('content-type', '').split(';')[0] != 'audio/mpeg':
                raise ValueError('ACE-Step n’a pas fourni un MP3.')
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 256 * 1024**2:
                    raise ValueError('Audio supérieur à 256 Mio.')
                chunks.append(chunk)
            return b''.join(chunks), 'audio/mpeg'

    async def close(self):
        await self.stop()
        await self.client.aclose()
