from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vertia.api.v1 import router
from vertia.modules.contrat import Module
from vertia.modules.registry import RegistreModules


def test_modules_catalogue_passif(tmp_path):
    declaration = tmp_path / 'factice' / 'module.py'
    declaration.parent.mkdir()
    declaration.write_text('''from vertia.modules.contrat import Module
def interdit(*args, **kwargs):
    raise AssertionError("Un moteur ne doit pas être construit")
MODULE = Module(nom="factice", activite="image", titre="Image test", version="1.2.3",
                moteurs={"gpu": interdit}, capacites=["image.generer"],
                lien="http://127.0.0.1:4320", sante=lambda: {"pret": True})
''', encoding='utf-8')
    broken = tmp_path / 'casse' / 'module.py'
    broken.parent.mkdir()
    broken.write_text('raise ValueError("module cassé")', encoding='utf-8')
    registre = RegistreModules(tmp_path)
    registre.sante = Mock(wraps=registre.sante)
    app = FastAPI()
    app.state.services = SimpleNamespace(modules=registre)
    app.include_router(router)
    response = TestClient(app).get('/api/v1/modules')
    assert response.status_code == 200
    data = response.json()
    assert [(a['activite'], a['titre']) for a in data['activites']] == [
        ('image', 'Image'), ('musique', 'Musique'), ('voix', 'Voix'),
        ('video', 'Vidéo'), ('chat', 'Discussion'), ('3d', 'Modélisation 3D'),
        ('animation_3d', 'Animation 3D'), ('worldmodel', 'WorldModel'),
        ('llm', 'LLM'), ('outil', 'Outils'),
    ]
    assert data['activites'][0]['modules'] == [dict(
        nom='factice', titre='Image test', version='1.2.3', capacites=['image.generer'],
        lien='http://127.0.0.1:4320', sante={'pret': True})]
    assert all(a['modules'] == [] for a in data['activites'][1:])
    assert len(data['erreurs']) == 1
    assert 'module cassé' in data['erreurs'][0]
    registre.sante.assert_called_once_with()


def test_module_lien_facultatif_et_diagnostic_en_erreur(tmp_path):
    module = Module(nom='factice', activite='outil', titre='Outil', version='1.0.0')
    assert module.lien is None
    declaration = tmp_path / 'outil' / 'module.py'
    declaration.parent.mkdir()
    declaration.write_text('''from vertia.modules.contrat import Module
def diagnostic():
    raise RuntimeError("diagnostic indisponible")
MODULE = Module(nom="outil", activite="outil", titre="Outil", version="1.0.0", sante=diagnostic)
''', encoding='utf-8')
    app = FastAPI()
    app.state.services = SimpleNamespace(modules=RegistreModules(tmp_path))
    app.include_router(router)
    data = TestClient(app).get('/api/v1/modules').json()
    outil = data['activites'][-1]['modules'][0]
    assert outil['lien'] is None
    assert outil['sante'] == {'pret': False, 'erreur': 'RuntimeError : diagnostic indisponible'}


def test_modules_local_seulement():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app, client=('192.0.2.1', 1234)) as client:
        assert client.get('/api/v1/modules').status_code == 403
