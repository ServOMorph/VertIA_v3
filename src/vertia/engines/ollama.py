from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from vertia.engines.base import MemoryNeeds


class OllamaClient:
    def __init__(self, base_url: str, num_ctx: int, client: httpx.AsyncClient | None = None):
        self.num_ctx = num_ctx
        self.client = client or httpx.AsyncClient(
            base_url=base_url.rstrip('/'), timeout=httpx.Timeout(600, connect=5),
            trust_env=False,
        )

    async def close(self):
        await self.client.aclose()

    async def models(self):
        response = await self.client.get('/api/tags', timeout=3)
        response.raise_for_status()
        return response.json().get('models', [])

    async def loaded_models(self):
        response = await self.client.get('/api/ps', timeout=3)
        response.raise_for_status()
        return response.json().get('models', [])

    async def lifecycle(self, model: str, keep_alive: int):
        response = await self.client.post('/api/generate', json={
            'model': model, 'prompt': '', 'stream': False, 'keep_alive': keep_alive,
            'options': {'num_ctx': self.num_ctx},
        })
        response.raise_for_status()
        return response.json()

    async def load_model(self, model: str):
        return await self.lifecycle(model, -1)

    async def unload_model(self, model: str):
        return await self.lifecycle(model, 0)

    async def prepare_model(self, model: str):
        for loaded in await self.loaded_models():
            name = loaded.get('name') or loaded.get('model')
            if name and name != model:
                await self.unload_model(name)

    async def chat_stream(self, model: str, messages: list[dict], num_predict: int) -> AsyncIterator[dict]:
        async with self.client.stream('POST', '/api/chat', json={
            'model': model, 'messages': messages, 'stream': True, 'keep_alive': -1,
            'options': {'num_ctx': self.num_ctx, 'num_predict': num_predict},
        }) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                if payload.get('error'):
                    raise RuntimeError(str(payload['error']))
                yield payload
                if payload.get('done'):
                    return
            raise RuntimeError('Flux Ollama interrompu avant la fin de la réponse.')


class OllamaEngine:
    memory = MemoryNeeds(note='Dépend du modèle et du contexte sélectionnés.')

    def __init__(self, client):
        self.client = client

    def can_reuse(self, model, state):
        models = state.get('models')
        if not state.get('gpus') or not isinstance(models, list) or len(models) != 1:
            return False
        loaded = models[0]
        if not isinstance(loaded, dict) or not isinstance(model, str):
            return False
        name = loaded.get('name') or loaded.get('model')
        if not isinstance(name, str):
            return False
        def canonical(value):
            return value if ':' in value.rsplit('/', 1)[-1] else value + ':latest'
        context = getattr(self.client, 'num_ctx', None)
        size = loaded.get('size_vram')
        return (canonical(name) == canonical(model) and isinstance(context, int)
                and loaded.get('context_length') == context
                and isinstance(size, (int, float)) and size > 0)

    async def start(self):
        pass

    async def health(self):
        try:
            await self.client.models()
            return True
        except Exception:
            return False

    async def stop(self):
        await self.free()

    async def free(self):
        try:
            models = await self.client.loaded_models()
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return
        for model in models:
            name = model.get('name') or model.get('model')
            if name:
                await self.client.unload_model(name)
