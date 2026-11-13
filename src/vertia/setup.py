from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SetupConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ollama_url: str = Field(max_length=200)
    default_model: str = Field(min_length=1, max_length=200)
    comfy_dir: str = Field(min_length=1, max_length=1000)
    comfy_port: int = Field(ge=1024, le=65535)
    acestep_dir: str = Field(min_length=1, max_length=1000)
    acestep_port: int = Field(ge=1024, le=65535)

    @field_validator('ollama_url')
    @classmethod
    def local_url(cls, value):
        url = urlsplit(value)
        if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', '::1'}
                or url.username or url.password or url.path not in {'', '/'} or url.query or url.fragment):
            raise ValueError('Utilisez une adresse HTTP locale, par exemple http://127.0.0.1:11434.')
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError('Port Ollama invalide.')
        return value.rstrip('/')

    @field_validator('default_model', 'comfy_dir', 'acestep_dir')
    @classmethod
    def clean_text(cls, value, info):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError('Renseignez une valeur sans caractère de contrôle.')
        if info.field_name.endswith('_dir') and not Path(value).is_absolute():
            raise ValueError('Renseignez un chemin absolu.')
        return value

    def settings_values(self):
        return dict(self.model_dump(), comfy_dir=Path(self.comfy_dir), acestep_dir=Path(self.acestep_dir))

    @property
    def ollama_port(self):
        return urlsplit(self.ollama_url).port or 80

    @model_validator(mode='after')
    def distinct_ports(self):
        if len({self.ollama_port, self.comfy_port, self.acestep_port}) != 3:
            raise ValueError('Ollama, ComfyUI et ACE-Step doivent utiliser des ports différents.')
        return self

    @classmethod
    def current(cls, settings):
        return cls(**{name: str(getattr(settings, name)) if name.endswith('_dir') else getattr(settings, name)
                      for name in cls.model_fields})


def save_config(path: Path, config: SetupConfig):
    temporary = path.with_name(f'{path.name}.{uuid4().hex}.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            stream.write(config.model_dump_json(indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def disk_check(directory, files):
    missing = [name for name in files if not (directory / name).is_file()]
    return {'present': not missing, 'manquants': missing}


async def diagnose(config: SetupConfig, client):
    async def probe(url, kind):
        try:
            response = await client.get(url, timeout=2)
            response.raise_for_status()
            data = response.json()
            if kind == 'ollama':
                models = [row['name'] for row in data['models'] if isinstance(row.get('name'), str)]
                return {'joignable': True, 'modeles': models,
                        'modele_choisi_present': config.default_model in models}
            valid = (isinstance(data.get('system'), dict) if kind == 'comfy'
                     else data.get('data', {}).get('service') == 'ACE-Step API'
                     and data.get('data', {}).get('status') == 'ok')
            return {'joignable': bool(valid)}
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            return {'joignable': False}

    ollama, comfy, ace = await asyncio.gather(
        probe(config.ollama_url + '/api/tags', 'ollama'),
        probe(f'http://127.0.0.1:{config.comfy_port}/system_stats', 'comfy'),
        probe(f'http://127.0.0.1:{config.acestep_port}/health', 'ace'))
    directory = Path(config.comfy_dir)
    comfy['installation'] = disk_check(directory, ['.venv/Scripts/python.exe', 'main.py',
                                                   'custom_nodes/ComfyUI-GGUF/nodes.py'])
    comfy['image'] = disk_check(directory, [
        'models/unet/qwen-image-2.1-Q4_K_M.gguf',
        'models/text_encoders/qwen3vl_8b_bf16.safetensors',
        'models/vae/qwen_image_2.1_vae_bf16.safetensors'])
    comfy['video'] = disk_check(directory, [
        'models/unet/Wan2.2-TI2V-5B-Q4_K_M.gguf',
        'models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors',
        'models/vae/wan2.2_vae.safetensors'])
    ace['installation'] = disk_check(Path(config.acestep_dir), [
        '.venv/Scripts/python.exe', 'acestep/api_server.py'])
    ace['checkpoint_present'] = (Path(config.acestep_dir) / 'checkpoints/acestep-v15-turbo/config.json').is_file()
    return {'ollama': ollama, 'comfy': comfy, 'ace': ace,
            'limite': 'Présence des fichiers et réponses HTTP uniquement : poids, dépendances, correctifs, mémoire et génération restent à tester.'}
