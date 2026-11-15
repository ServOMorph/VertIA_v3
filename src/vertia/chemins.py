from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Chemins:
    engines_dir: Path
    models_dir: Path
    outputs_dir: Path
    outbox_dir: Path
    inbox_dir: Path
    data_dir: Path
    config_dir: Path
    comfy_dir: Path
    acestep_dir: Path


def resoudre_chemins(
    root: Path = ROOT,
    *,
    environ: Mapping[str, str] | None = None,
    **overrides: str | Path,
) -> Chemins:
    root = Path(root).resolve()

    def chemin(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    values = {name + '_dir': root / name for name in
              ('engines', 'models', 'outputs', 'outbox', 'inbox', 'data', 'config')}
    values.update(comfy_dir=root / 'engines/comfyui', acestep_dir=root / 'engines/acestep')
    config = root / 'config/chemins.toml'
    try:
        with config.open('rb') as stream:
            document = tomllib.load(stream)
    except FileNotFoundError:
        if config.exists():
            raise ValueError(f'Configuration des chemins illisible : {config}.')
        document = {}
    except (OSError, ValueError) as exc:
        raise ValueError(f'Configuration des chemins illisible : {config}.') from exc
    for section, names in (
        ('moteurs', {'comfyui': 'comfy_dir', 'acestep': 'acestep_dir'}),
        ('dossiers', {name: name + '_dir' for name in
                      ('models', 'outputs', 'outbox', 'inbox', 'data', 'config', 'engines')}),
    ):
        entries = document.get(section, {})
        if not isinstance(entries, dict):
            raise ValueError(f'Configuration des chemins invalide : [{section}] dans {config}.')
        for key, target in names.items():
            if key in entries:
                value = entries[key]
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f'Chemin invalide : {section}.{key} dans {config}.')
                values[target] = chemin(value)
    env = os.environ if environ is None else environ
    for variable, target in (
        ('VERTIA_COMFY_DIR', 'comfy_dir'), ('VERTIA_ACESTEP_DIR', 'acestep_dir'),
        ('VERTIA_OUTPUTS_DIR', 'outputs_dir'), ('VERTIA_DATA_DIR', 'data_dir'),
    ):
        if raw := env.get(variable, '').strip():
            values[target] = chemin(raw)
    result = Chemins(**values)
    unknown = overrides.keys() - {field.name for field in fields(Chemins)}
    if unknown:
        raise TypeError(f'Chemins inconnus : {", ".join(sorted(unknown))}')
    return replace(result, **{key: chemin(value) for key, value in overrides.items()})
