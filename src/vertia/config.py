from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

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

    @classmethod
    def from_env(cls, **overrides: object) -> "Settings":
        load_dotenv(ROOT / ".env")
        data_dir = _path("VERTIA_DATA_DIR", ROOT / "data")
        settings = cls(
            host=_env("VERTIA_HOST", "127.0.0.1"),
            port=int(_env("VERTIA_PORT", "4310")),
            data_dir=data_dir,
            database=_path("VERTIA_DATABASE", data_dir / "vertia.db"),
            outputs_dir=_path("VERTIA_OUTPUTS_DIR", ROOT / "outputs"),
            ollama_url=_env("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            default_model=_env("VERTIA_DEFAULT_MODEL", "gemma4:12b"),
            num_ctx=int(_env("VERTIA_NUM_CTX", "16384")),
            comfy_dir=_path("VERTIA_COMFY_DIR", Path(r"D:\ServOMorph\ComfyUI-Qwen")),
            comfy_port=int(_env("VERTIA_COMFY_PORT", "8189")),
            acestep_dir=_path("VERTIA_ACESTEP_DIR", Path(r"D:\ServOMorph\ACE-Step-1.5")),
            acestep_port=int(_env("VERTIA_ACESTEP_PORT", "8001")),
            vram_limit_percent=int(_env("VERTIA_VRAM_LIMIT_PERCENT", "92")),
            ram_limit_percent=int(_env("VERTIA_RAM_LIMIT_PERCENT", "90")),
        )
        return replace(settings, **overrides) if overrides else settings

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
