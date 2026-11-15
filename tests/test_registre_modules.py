from pathlib import Path
import shutil

import pytest

from vertia.modules import Module, RegistreModules

FIXTURES = Path(__file__).parent / 'fixtures/modules'


def declaration(root, name, source):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / 'module.py').write_text(source, encoding='utf-8')


def test_decouverte_et_outil_factice():
    registre = RegistreModules(FIXTURES)
    assert registre.erreurs == []
    module, = registre.modules()
    assert module.nom == 'factice'
    assert registre.par_activite('outil') == [module]
    assert registre.par_activite('image') == []
    assert registre.capacites() == {'test.echo': module}
    assert module.outils['echo']().validate({'texte': 'bonjour'}) == {'texte': 'bonjour'}
    assert registre.sante() == {'factice': {'pret': True}}
    registre.capacites().clear()
    assert 'test.echo' in registre.capacites()


@pytest.mark.parametrize('change', [
    {'nom': 'nom-invalide'}, {'nom': 'class'}, {'activite': 'inconnue'},
    {'version': '1.2'}, {'version': '01.2.3'}, {'version': '1.2.3-01'},
    {'capacites': ['echo']}, {'capacites': ['test.echo.extra']},
    {'moteurs': {'test': 42}}, {'sante': None}, {'poids': ['../poids']},
    {'poids': ['/absolu']}, {'poids': [r'C:\poids']}, {'besoins': {'absent': None}},
])
def test_contrat_invalide(change):
    with pytest.raises(ValueError):
        Module(**(dict(nom='test', activite='outil', titre='Test', version='1.2.3') | change))


def test_semver_et_capacite_3d():
    module = Module(nom='test', activite='3d', titre='Test', version='1.2.3-rc.1+build.001',
                    capacites=['3d.depuis_image'], poids=['hf/test/model.bin'])
    assert module.capacites == ['3d.depuis_image']


def test_imports_invalides_isoles_et_doublon(tmp_path):
    shutil.copytree(FIXTURES / 'factice', tmp_path / 'factice')
    declaration(tmp_path, 'a_invalide', 'MODULE = {"nom": "invalide"}')
    declaration(tmp_path, 'b_erreur', 'raise RuntimeError("import impossible")')
    declaration(tmp_path, 'z_doublon', '''MODULE = dict(nom='autre', activite='outil',
titre='Autre', version='1.0.0', capacites=['test.echo'])''')
    registre = RegistreModules(tmp_path)
    assert [module.nom for module in registre.modules()] == ['factice', 'autre']
    assert len(registre.erreurs) == 3
    assert any('a_invalide' in error for error in registre.erreurs)
    assert any('import impossible' in error for error in registre.erreurs)
    assert any('capacité déjà déclarée' in error for error in registre.erreurs)
    assert registre.capacites()['test.echo'].nom == 'factice'


def test_sante_passive_et_erreur_isolee(tmp_path):
    declaration(tmp_path, 'passif', '''from vertia.modules import Module
def interdit(*args, **kwargs):
    raise AssertionError('Fabrique appelée')
MODULE = Module(nom='passif', activite='outil', titre='Passif', version='1.0.0',
                moteurs={'test': interdit}, outils={'test': interdit},
                sante=lambda: {'pret': True})
''')
    declaration(tmp_path, 'erreur', '''from vertia.modules import Module
def diagnostic():
    raise RuntimeError('Diagnostic indisponible')
MODULE = Module(nom='erreur', activite='outil', titre='Erreur', version='1.0.0', sante=diagnostic)
''')
    registre = RegistreModules(tmp_path)
    assert registre.erreurs == []
    assert registre.sante()['passif'] == {'pret': True}
    assert registre.sante()['erreur']['pret'] is False


def test_objet_externe_et_import_relatif(tmp_path):
    declaration(tmp_path, 'objet', '''from dataclasses import dataclass
from .helper import TITRE
@dataclass
class Declaration:
    nom = 'objet'
    activite = 'outil'
    titre = TITRE
    version = '1.0.0'
    moteurs = {}
    outils = {}
    capacites = ['test.objet']
    besoins = {}
    poids = []
    def sante(self):
        return {'pret': True}
MODULE = Declaration()
''')
    (tmp_path / 'objet/helper.py').write_text('TITRE = "Objet"', encoding='utf-8')
    registre = RegistreModules(tmp_path)
    assert registre.erreurs == []
    assert registre.modules()[0].titre == 'Objet'
    assert registre.sante() == {'objet': {'pret': True}}


def test_dossier_absent(tmp_path):
    registre = RegistreModules(tmp_path / 'absent')
    assert registre.modules() == []
    assert registre.erreurs == []
