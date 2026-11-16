from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import httpx
from websockets.asyncio.client import connect

from vertia.engines.base import EngineError, MemoryNeeds
from vertia.engines.process import ProcessOwner


def build_graph(p):
    graph = {
        '1': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': 'qwen-image-2.1-Q4_K_M.gguf'}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'qwen3vl_8b_bf16.safetensors', 'type': 'qwen_image', 'device': 'default'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'qwen_image_2.1_vae_bf16.safetensors'}},
        '4': {'class_type': 'TextEncodeQwenImage21', 'inputs': {
            'clip': ['2', 0], 'prompt': p['prompt'], 'negative_prompt': p['negatif'], 'vae': ['3', 0], 'resolution': 1024}},
        '5': {'class_type': 'EmptyLatentImage', 'inputs': {'width': p['largeur'], 'height': p['hauteur'], 'batch_size': 1}},
        '9': {'class_type': 'KSampler', 'inputs': {
            'model': ['1', 0], 'seed': p['seed'], 'steps': p['etapes'], 'cfg': 1,
            'sampler_name': 'euler', 'scheduler': 'simple', 'positive': ['4', 0],
            'negative': ['4', 1], 'latent_image': ['5', 0], 'denoise': 1}},
        '11': {'class_type': 'VAEDecode', 'inputs': {'samples': ['9', 0], 'vae': ['3', 0]}},
        '12': {'class_type': 'SaveImage', 'inputs': {'images': ['11', 0], 'filename_prefix': 'VertIA'}},
    }
    for index, name in enumerate(p.get('references', [])):
        node = str(20 + index)
        graph[node] = {'class_type': 'LoadImage', 'inputs': {'image': name}}
        graph['4']['inputs'][f'images.image_{index + 1}'] = [node, 0]
    if p.get('mode') == 'edit':
        del graph['5']
        graph['9']['inputs']['latent_image'] = ['4', 2]
    return graph


def build_graph_retouche(p):
    graph = build_graph(dict(p, largeur=256, hauteur=256, references=[], mode='t2i'))
    graph['5'] = {'class_type': 'LoadImage', 'inputs': {'image': p['source']}}
    graph['6'] = {'class_type': 'VAEEncode', 'inputs': {'pixels': ['5', 0], 'vae': ['3', 0]}}
    latent = ['6', 0]
    if p.get('masque'):
        graph['7'] = {'class_type': 'LoadImageMask', 'inputs': {'image': p['masque'], 'channel': 'red'}}
        graph['8'] = {'class_type': 'SetLatentNoiseMask', 'inputs': {'samples': latent, 'mask': ['7', 0]}}
        latent = ['8', 0]
    graph['9']['inputs'].update(latent_image=latent, denoise=p['force'])
    return graph


class ComfyQwenEngine(ProcessOwner):
    memory = MemoryNeeds(ram_mb=17000, note='Minimum du seul encodeur ; consommation totale et VRAM à mesurer.')

    def __init__(self, directory: Path, port: int, client=None, websocket=connect, launcher=subprocess.Popen):
        super().__init__('ComfyUI')
        self.directory, self.port = directory, port
        self.url = f'http://127.0.0.1:{port}'
        self.client = client or httpx.AsyncClient(base_url=self.url, timeout=10, trust_env=False)
        self.websocket, self.launcher = websocket, launcher
        self.prompt_id = None

    async def health(self):
        try:
            response = await self.client.get('/system_stats', timeout=2)
            response.raise_for_status()
            return isinstance(response.json().get('system'), dict)
        except (httpx.HTTPError, ValueError, AttributeError):
            return False

    async def queue(self):
        response = await self.client.get('/queue')
        response.raise_for_status()
        return response.json()

    async def ensure_idle(self):
        state = await self.queue()
        if state.get('queue_running') or state.get('queue_pending'):
            raise EngineError('ComfyUI exécute déjà une tâche. Attendez sa fin avant de changer de moteur.')

    def check_patch(self):
        patch = self.directory / 'correctifs' / 'ComfyUI-GGUF-qwen-image-2.1.patch'
        result = subprocess.run([
            'git', '-C', str(self.directory / 'custom_nodes' / 'ComfyUI-GGUF'),
            'apply', '--reverse', '--check', str(patch)], capture_output=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode:
            raise EngineError('Correctif Qwen absent ou non vérifiable. Appliquez correctifs/appliquer.bat manuellement dans ComfyUI ; VertIA ne modifie pas ce dossier.')

    async def start(self):
        if self.stopping:
            await self.stop()
        if self.prompt_id:
            raise EngineError('La fin du précédent prompt ComfyUI reste à confirmer. Libérez le moteur avant de réessayer.')
        if await self.health():
            await self.ensure_idle()
            return
        if self.owned():
            await self.stop()
        python = self.directory / '.venv' / 'Scripts' / 'python.exe'
        if not python.is_file() or not (self.directory / 'main.py').is_file():
            raise EngineError('Installation ComfyUI introuvable. Vérifiez VERTIA_COMFY_DIR.')
        await asyncio.to_thread(self.check_patch)
        self.process = self.launcher(
            [str(python), '-B', 'main.py', '--port', str(self.port), '--lowvram', '--reserve-vram', '1'], cwd=self.directory,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            async with asyncio.timeout(600):
                while not await self.health():
                    if self.process.poll() is not None:
                        raise EngineError('ComfyUI s’est arrêté au démarrage. Vérifiez son installation.')
                    await asyncio.sleep(1)
        except BaseException:
            await self.stop()
            raise

    async def free(self):
        if self.stopping:
            await self.stop()
        if self.prompt_id:
            await self.cancel_prompt(self.prompt_id)
            self.prompt_id = None
        if await self.health():
            await self.ensure_idle()
            response = await self.client.post('/free', json={'unload_models': True, 'free_memory': True})
            response.raise_for_status()
            # /free est asynchrone ; arrêter notre propre processus garantit sa libération.
            if self.process:
                await self.stop()
            else:
                async with asyncio.timeout(30):
                    while True:
                        stats = await self.client.get('/system_stats')
                        stats.raise_for_status()
                        devices = stats.json().get('devices')
                        if not devices:
                            raise EngineError('Libération VRAM ComfyUI non mesurable ; changement de moteur refusé.')
                        gpu = [d for d in devices if d.get('type') != 'cpu']
                        if not gpu:
                            raise EngineError('Libération VRAM ComfyUI non mesurable ; changement de moteur refusé.')
                        if all(isinstance(d.get('torch_vram_total'), (int, float)) and d['torch_vram_total'] <= 64 * 1024**2 for d in gpu):
                            break
                        await asyncio.sleep(.2)
        elif self.process is not None:
            await self.stop()

    async def preview(self, image, formats=None, max_bytes=32 * 1024**2):
        formats = formats or {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
        name, folder = image.get('filename', ''), image.get('subfolder', '')
        if not name or '/' in name or '\\' in name or ':' in name or '..' in Path(folder).parts or Path(folder).is_absolute():
            raise ValueError('Référence média invalide.')
        if image.get('type') != 'output':
            raise ValueError('Seuls les médias générés sont accessibles.')
        try:
            async with self.client.stream('GET', '/view', params={'filename': name, 'subfolder': folder, 'type': 'output'}) as response:
                response.raise_for_status()
                mime = response.headers.get('content-type', '').split(';')[0]
                if mime not in formats.values():
                    raise ValueError('Format média non pris en charge.')
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > max_bytes:
                        raise ValueError('Média trop volumineux.')
                    data.extend(chunk)
                return bytes(data), mime
        except httpx.HTTPError:
            # Lecture seule des résultats existants lorsque notre processus est arrêté.
            def read_output():
                root = (self.directory / 'output').resolve()
                path = (root / folder / name).resolve()
                media_type = formats.get(path.suffix.lower())
                if not path.is_relative_to(root) or not media_type or path.stat().st_size > max_bytes:
                    raise ValueError('Média inaccessible ou trop volumineux.')
                with path.open('rb') as source:
                    data = source.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise ValueError('Média trop volumineux.')
                return data, media_type
            try:
                return await asyncio.to_thread(read_output)
            except OSError as exc:
                raise ValueError('Résultat ComfyUI introuvable sur disque.') from exc

    async def close(self):
        await self.stop()
        await self.client.aclose()

    async def upload_image(self, data, mime):
        suffix = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}.get(mime)
        if not suffix or len(data) > 32 * 1024**2:
            raise EngineError('Image de référence incompatible ou supérieure à 32 Mio.')
        name = 'VertIA_' + uuid4().hex + suffix
        response = await self.client.post('/upload/image', files={'image': (name, data, mime)},
                                          data={'type': 'input', 'overwrite': 'false'}, timeout=60)
        response.raise_for_status()
        result = response.json()
        if result.get('name') != name or result.get('subfolder', '') or result.get('type') != 'input':
            raise EngineError('ComfyUI n’a pas confirmé l’image de référence.')
        return name

    async def cancel_prompt(self, prompt_id):
        response = await self.client.post('/queue', json={'delete': [prompt_id]})
        response.raise_for_status()
        response = await self.client.post('/interrupt', json={'prompt_id': prompt_id})
        response.raise_for_status()
        async with asyncio.timeout(30):
            while True:
                state = await self.queue()
                if not any(row[1] == prompt_id for key in ('queue_running', 'queue_pending') for row in state.get(key, [])):
                    return
                await asyncio.sleep(.2)

    async def generate(self, params, progress):
        return await self.generate_graph(build_graph(params), progress)

    async def generate_graph(self, graph, progress, output_node='12', result_key='images'):
        client_id = uuid4().hex
        prompt_id = None
        complete = False
        try:
            async with self.websocket(f'ws://127.0.0.1:{self.port}/ws?clientId={client_id}', open_timeout=10) as ws:
                prompt_id = self.prompt_id = str(uuid4())
                response = await self.client.post('/prompt', json={'prompt': graph, 'client_id': client_id, 'prompt_id': prompt_id})
                response.raise_for_status()
                if response.json().get('prompt_id') != prompt_id:
                    raise EngineError('ComfyUI n’a pas conservé l’identifiant de tâche ; version incompatible.')
                deadline = time.monotonic() + 1800
                while time.monotonic() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 1)
                    except TimeoutError:
                        raw = None
                    if isinstance(raw, str):
                        event = json.loads(raw)
                        data = event.get('data', {})
                        if data.get('prompt_id') == prompt_id:
                            if event['type'] in {'execution_error', 'execution_interrupted'}:
                                raise EngineError('Génération interrompue ou en erreur. Consultez ComfyUI.')
                            if event['type'] == 'progress' and data.get('max', 0) > 0:
                                progress(min(95, 100 * data['value'] / data['max']))
                    history = await self.client.get(f'/history/{prompt_id}')
                    history.raise_for_status()
                    record = history.json().get(prompt_id)
                    if record:
                        if record.get('status', {}).get('status_str') == 'error':
                            raise EngineError('ComfyUI a refusé la génération. Consultez son historique.')
                        images = record.get('outputs', {}).get(output_node, {}).get('images', [])
                        if not images:
                            raise EngineError('ComfyUI n’a renvoyé aucun média.')
                        complete = True
                        progress(100)
                        return {'prompt_id': prompt_id, result_key: images}
                raise EngineError('Délai ComfyUI dépassé (30 minutes).')
        finally:
            if prompt_id and not complete:
                # Ne pas rendre le GPU à la file avant la fin effective de notre prompt.
                await self.cancel_prompt(prompt_id)
            self.prompt_id = None
