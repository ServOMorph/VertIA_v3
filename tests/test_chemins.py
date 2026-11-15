from dataclasses import FrozenInstanceError

import pytest

from vertia.chemins import resoudre_chemins
from vertia.config import Settings
from vertia.setup import SetupConfig


def ecrire_toml(root, content):
    directory = root / 'config'
    directory.mkdir(exist_ok=True)
    (directory / 'chemins.toml').write_text(content, encoding='utf-8')


def test_defauts_immuables_sans_creation(tmp_path):
    chemins = resoudre_chemins(tmp_path, environ={})
    for name in ('engines', 'models', 'outputs', 'outbox', 'inbox', 'data', 'config'):
        assert getattr(chemins, name + '_dir') == tmp_path / name
    assert chemins.comfy_dir == tmp_path / 'engines/comfyui'
    assert chemins.acestep_dir == tmp_path / 'engines/acestep'
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(FrozenInstanceError):
        chemins.comfy_dir = tmp_path


def test_toml_env_et_override(tmp_path):
    absolute = (tmp_path / 'absolute').as_posix()
    ecrire_toml(tmp_path, f'''[moteurs]
comfyui = "toml/comfy"
acestep = "{absolute}"
[dossiers]
models = "poids"
outputs = "toml/outputs"
outbox = "livraisons"
inbox = "entrees"
''')
    chemins = resoudre_chemins(tmp_path, environ={})
    assert chemins.comfy_dir == tmp_path / 'toml/comfy'
    assert chemins.acestep_dir == tmp_path / 'absolute'
    assert chemins.models_dir == tmp_path / 'poids'
    assert chemins.outputs_dir == tmp_path / 'toml/outputs'
    assert chemins.outbox_dir == tmp_path / 'livraisons'
    assert chemins.inbox_dir == tmp_path / 'entrees'
    env = {'VERTIA_COMFY_DIR': 'env/comfy', 'VERTIA_ACESTEP_DIR': 'env/ace',
           'VERTIA_OUTPUTS_DIR': absolute}
    chemins = resoudre_chemins(tmp_path, environ=env)
    assert chemins.comfy_dir == tmp_path / 'env/comfy'
    assert chemins.acestep_dir == tmp_path / 'env/ace'
    assert chemins.outputs_dir == tmp_path / 'absolute'
    assert resoudre_chemins(tmp_path, environ=env, comfy_dir='override').comfy_dir == tmp_path / 'override'
    assert resoudre_chemins(tmp_path, environ={'VERTIA_COMFY_DIR': '  '}).comfy_dir == tmp_path / 'toml/comfy'


@pytest.mark.parametrize('content', ['[moteurs', '[moteurs]\ncomfyui = 42',
                                      'moteurs = []', '[dossiers]\nmodels = ""'])
def test_toml_invalide(tmp_path, content):
    ecrire_toml(tmp_path, content)
    with pytest.raises(ValueError, match='chemin|Chemin'):
        resoudre_chemins(tmp_path, environ={})


def test_toml_non_lisible(tmp_path, monkeypatch):
    from pathlib import Path
    original = Path.open

    def denied(path, *args, **kwargs):
        if path.name == 'chemins.toml':
            raise PermissionError('interdit')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', denied)
    with pytest.raises(ValueError, match='illisible'):
        resoudre_chemins(tmp_path, environ={})


def test_settings_priorites_completes(tmp_path, monkeypatch):
    import vertia.config as config
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    for name in ('VERTIA_COMFY_DIR', 'VERTIA_ACESTEP_DIR', 'VERTIA_OUTPUTS_DIR'):
        monkeypatch.delenv(name, raising=False)
    local = tmp_path / '.vertia-local.json'
    kwargs = {'local_config': local}
    assert Settings.from_env(**kwargs).comfy_dir == tmp_path / 'engines/comfyui'
    ecrire_toml(tmp_path, '[moteurs]\ncomfyui = "toml/comfy"\nacestep = "toml/ace"')
    settings = Settings.from_env(**kwargs)
    assert settings.comfy_dir == tmp_path / 'toml/comfy'
    assert settings.acestep_dir == tmp_path / 'toml/ace'
    (tmp_path / '.env').write_text('VERTIA_COMFY_DIR=env/comfy\nVERTIA_OUTPUTS_DIR=env/outputs\n', encoding='utf-8')
    # Garder les variables ajoutées par dotenv dans la portée du monkeypatch.
    monkeypatch.setenv('VERTIA_COMFY_DIR', '')
    monkeypatch.delenv('VERTIA_COMFY_DIR')
    monkeypatch.setenv('VERTIA_OUTPUTS_DIR', '')
    monkeypatch.delenv('VERTIA_OUTPUTS_DIR')
    settings = Settings.from_env(**kwargs)
    assert settings.comfy_dir == tmp_path / 'env/comfy'
    assert settings.outputs_dir == tmp_path / 'env/outputs'
    saved = SetupConfig.current(settings).model_copy(update={
        'comfy_dir': str(tmp_path / 'saved/comfy'), 'acestep_dir': str(tmp_path / 'saved/ace')})
    local.write_text(saved.model_dump_json(), encoding='utf-8')
    assert Settings.from_env(**kwargs).comfy_dir == tmp_path / 'saved/comfy'
    assert Settings.from_env(**kwargs).acestep_dir == tmp_path / 'saved/ace'
    assert Settings.from_env(**kwargs, comfy_dir=tmp_path / 'override').comfy_dir == tmp_path / 'override'
