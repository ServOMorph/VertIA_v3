from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

from vertia.chemins import resoudre_chemins

ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _path(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    database: Path
    outputs_dir: Path
    ollama_url: str
    default_model: str
    num_ctx: int
    comfy_dir: Path
    comfy_port: int
    acestep_dir: Path
    acestep_port: int
    vram_limit_percent: int
    ram_limit_percent: int
    engine_idle_seconds: int = 300
    local_config: Path = ROOT / ".vertia-local.json"
    ollama_executable: str = ''
    ollama_autostart: bool = True
    resident_vram_reserve_mb: int = 512
    verrou_gpu: bool = True
    preload_ollama: bool = True
    verrou_gpu_attente_s: int = 600

    @classmethod
    def from_env(cls, **overrides: object) -> "Settings":
        load_dotenv(ROOT / ".env")
        chemins = resoudre_chemins(ROOT)
        data_dir = chemins.data_dir
        settings = cls(
            host=_env("VERTIA_HOST", "127.0.0.1"),
            port=int(_env("VERTIA_PORT", "4310")),
            data_dir=data_dir,
            database=_path("VERTIA_DATABASE", data_dir / "vertia.db"),
            outputs_dir=chemins.outputs_dir,
            ollama_url=_env("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            default_model=_env("VERTIA_DEFAULT_MODEL", "gemma4:12b"),
            num_ctx=int(_env("VERTIA_NUM_CTX", "16384")),
            comfy_dir=chemins.comfy_dir,
            comfy_port=int(_env("VERTIA_COMFY_PORT", "8189")),
            acestep_dir=chemins.acestep_dir,
            acestep_port=int(_env("VERTIA_ACESTEP_PORT", "8001")),
            vram_limit_percent=int(_env("VERTIA_VRAM_LIMIT_PERCENT", "92")),
            ram_limit_percent=int(_env("VERTIA_RAM_LIMIT_PERCENT", "90")),
            engine_idle_seconds=max(0, int(_env("VERTIA_ENGINE_IDLE_SECONDS", "300"))),
            ollama_executable=_env('VERTIA_OLLAMA_EXECUTABLE', ''),
            ollama_autostart=_env('VERTIA_OLLAMA_AUTOSTART', 'true').lower() not in {'0', 'false', 'no'},
            resident_vram_reserve_mb=max(128, int(_env('VERTIA_RESIDENT_VRAM_RESERVE_MB', '512'))),
            preload_ollama=_env('VERTIA_PRELOAD_OLLAMA', 'true').lower() not in {'0', 'false', 'no'},
            verrou_gpu=_env('VERTIA_VERROU_GPU', 'true').lower() not in {'0', 'false', 'no'},
            verrou_gpu_attente_s=max(0, int(_env('VERTIA_VERROU_GPU_ATTENTE_S', '600'))),
        )
        config_path = Path(overrides.get("local_config", settings.local_config))
        if config_path.is_file():
            from vertia.setup import SetupConfig
            try:
                saved = SetupConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                raise ValueError(f"Configuration locale illisible : {config_path}. Corrigez ou renommez ce fichier.") from exc
            settings = replace(settings, **saved.settings_values())
        return replace(settings, **overrides) if overrides else settings

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
