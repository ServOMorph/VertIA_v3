import base64
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import httpx
from PIL import Image
import pytest

import vertia_gen
from modules.image.outil_analyse import OutilAnalyse, SYSTEME
from modules.image.vision import analyser_dialogue, cadre_reperage, extraire_boite, zone_vers_source
from vertia.app import create_app
from vertia.chemins import resoudre_chemins
from vertia.engines.base import EngineError
from vertia.tools.base import ParameterError


@pytest.mark.parametrize('taille', [(768, 768), (1200, 750), (750, 1200), (4000, 1000), (300, 300)])
def test_cadre_reperage(taille):
    largeur, hauteur = cadre_reperage(*taille)
    assert largeur % 28 == hauteur % 28 == 0
    assert 850_000 <= largeur * hauteur <= 1_000_000
    assert largeur / hauteur == pytest.approx(taille[0] / taille[1], rel=0.02)


def test_conversion_vers_source():
    source = (1200, 750)
    cadre = cadre_reperage(*source)
    boite = [480, 60, 720, 135]
    axes = zip(boite, cadre * 2, source * 2)
    assert zone_vers_source([n * dest / orig for n, dest, orig in axes], cadre, source) == boite
    assert zone_vers_source([-200, -5, 2000, 4000], cadre, source) == [0, 0, *source]
    assert zone_vers_source([0, 0, 4, 4], (1000, 1000), (750, 750)) is None
    assert zone_vers_source([0, 0, 4, 4], (100, 100), (100, 100)) == [0, 0, 4, 4]


@pytest.mark.parametrize('boite', [
    None, [10, 0, 10, 20], [10, 0, 5, 20], [0, 0, 10], [0, 0, '10', 20],
    [False, 0, 10, 20], [0, 0, float('nan'), 20], [0, 0, 10, float('inf')],
])
def test_boites_invalides(boite):
    assert zone_vers_source(boite, (100, 100), (100, 100)) is None


@pytest.mark.parametrize('texte, attendu', [
    ('```json\n[{"bbox_2d": [1, 2, 3, 4], "label": "porte"}]\n```', [1, 2, 3, 4]),
    ('[1.5, 2, 30, 40]', [1.5, 2, 30, 40]),
    ('Préambule [1, 2, 3, 4], puis {"bbox_2d": [5, 6, 7, 8]}', [5, 6, 7, 8]),
    ('[{"bbox_2d": [1, 2, 3, 4]}, {"bbox_2d": [5, 6, 7, 8]}]', [1, 2, 3, 4]),
    ('There are none.', None),
    ('[{"bbox_2d": [1, 2, 30, 40,]}]', None),
    ('[false, 2, 3, 4]', None),
])
def test_extraire_boite(texte, attendu):
    assert extraire_boite(texte) == attendu


def test_dialogue_borne_les_champs_et_le_nombre_de_propositions():
    candidate = dict(titre=' ' + 't' * 121, cible='c' * 201, prompt='p' * 1001, autre='ignoré')
    texte = json.dumps(dict(reponse='é' * 4001, propositions=[None, {}, candidate] + [candidate] * 4))
    reponse, propositions = analyser_dialogue(texte)
    assert reponse == 'é' * 4000
    assert propositions == [dict(titre='t' * 120, cible='c' * 200, prompt='p' * 1000,
                                 type='objet', zone=None)] * 4


class FauxOllama:
    def __init__(self, textes):
        self.client = self
        self.textes = iter(textes)
        self.appels = []

    async def prepare_model(self, modele):
        self.appels.append(('prepare', modele))

    async def post(self, url, *, json):
        self.appels.append((url, json))
        return httpx.Response(200, json={'message': {'content': next(self.textes)}},
                              request=httpx.Request('POST', 'http://ollama.test' + url))


DIALOGUE = json.dumps(dict(reponse=' Deux idées. ', ignore='inconnu', propositions=[
    dict(titre=' Porte bleue ', cible=' door ', prompt=' blue door ', type='objetre', ignore=3),
    dict(titre='Sans cible', prompt='prompt'),
    dict(titre=' ', cible='door', prompt='prompt'),
    dict(titre='Nuage', cible='sky above the tower', prompt='small cloud', type='emplacement'),
]))


@pytest.fixture
def contexte(tmp_path):
    chemins = resoudre_chemins(tmp_path, environ={})
    chemins.inbox_dir.mkdir()
    Image.new('RGB', (1200, 750), 'blue').save(chemins.inbox_dir / 'source.png')
    return chemins


def construire_analyse(chemins, *textes):
    ollama = FauxOllama(textes)
    return OutilAnalyse(None, chemins, {'ollama': SimpleNamespace(client=ollama)}), ollama


def taille_image_message(message):
    assert len(message['images']) == 1
    with Image.open(BytesIO(base64.b64decode(message['images'][0]))) as image:
        return image.size


async def test_analyse_avec_reperage(contexte, tmp_path):
    outil, ollama = construire_analyse(contexte, DIALOGUE, '[0, 0, 2000, 2000]', 'There are none.')
    params = dict(source='source.png', prompt='Que proposes-tu ?', historique=[
        dict(role='user', contenu='Bonjour'), dict(role='assistant', contenu='Salut')])
    fichiers = await outil.executer(outil.valider(params), tmp_path)
    assert fichiers == [tmp_path / 'analyse_1.json']
    assert [appel[0] for appel in ollama.appels] == ['prepare', '/api/chat', 'prepare', '/api/chat', '/api/chat']
    assert ollama.appels[0][1] == 'gemma4:12b'
    assert ollama.appels[2][1] == 'qwen2.5vl:latest'

    dialogue = ollama.appels[1][1]
    messages = dialogue.pop('messages')
    assert dialogue == dict(model='gemma4:12b', stream=False, keep_alive=300, format='json',
                            options=dict(num_ctx=8192, temperature=0.2))
    assert messages[:-1] == [dict(role='system', content=SYSTEME), dict(role='user', content='Bonjour'),
                             dict(role='assistant', content='Salut')]
    assert messages[-1]['role'] == 'user' and messages[-1]['content'] == params['prompt']
    assert taille_image_message(messages[-1]) == (896, 560)

    for (_, reperage), cible in zip(ollama.appels[3:], ['door', 'sky above the tower']):
        messages = reperage.pop('messages')
        assert reperage == dict(model='qwen2.5vl:latest', stream=False, keep_alive=300,
                                options=dict(temperature=0))
        message, = messages
        assert message['role'] == 'user'
        assert message['content'] == f'Locate {cible} in the image, output its bbox coordinates using JSON format.'
        assert taille_image_message(message) == cadre_reperage(1200, 750)

    texte = fichiers[0].read_text(encoding='utf-8')
    assert 'Deux idées.' in texte
    resultat = json.loads(texte)
    durees = resultat.pop('durees_s')
    assert durees.keys() == {'dialogue', 'reperage'}
    assert all(isinstance(duree, float) and duree >= 0 for duree in durees.values())
    assert resultat == dict(reponse='Deux idées.', taille=[1200, 750],
                           modeles=dict(dialogue='gemma4:12b', reperage='qwen2.5vl:latest'), propositions=[
        dict(titre='Porte bleue', cible='door', prompt='blue door', type='objet', zone=[0, 0, 1200, 750]),
        dict(titre='Nuage', cible='sky above the tower', prompt='small cloud', type='emplacement', zone=None),
    ])


@pytest.mark.parametrize('reperer, texte, nombre', [(False, DIALOGUE, 2), (True, '{}', 0)])
async def test_analyse_sans_appel_qwen(contexte, tmp_path, reperer, texte, nombre):
    outil, ollama = construire_analyse(contexte, texte)
    fichier, = await outil.executer(dict(source='source.png', prompt='?', reperer=reperer,
                                         modele_dialogue='local/gemma:autre', modele_reperage='qwen:autre'), tmp_path)
    assert len(ollama.appels) == 2
    assert ollama.appels[0] == ('prepare', 'local/gemma:autre')
    resultat = json.loads(fichier.read_text(encoding='utf-8'))
    assert resultat['modeles'] == dict(dialogue='local/gemma:autre', reperage='qwen:autre')
    assert len(resultat['propositions']) == nombre
    assert all(p['zone'] is None for p in resultat['propositions'])
    assert resultat['durees_s']['reperage'] == 0.0


@pytest.mark.parametrize('texte, erreur', [('pas du json', 'JSON.*illisible'), ('[]', 'JSON.*objet')])
async def test_echec_dialogue(contexte, tmp_path, texte, erreur):
    outil, ollama = construire_analyse(contexte, texte)
    with pytest.raises(EngineError, match=erreur):
        await outil.executer(dict(source='source.png', prompt='?'), tmp_path)
    assert len(ollama.appels) == 2
    assert not (tmp_path / 'analyse_1.json').exists()


@pytest.mark.parametrize('invalide', [
    dict(source='../source.png'), dict(source='inconnue.png'), dict(source=42), dict(prompt=' '),
    dict(prompt='q' * 4001), dict(reperer='false'), dict(modele_dialogue='bad model'),
    dict(modele_reperage='-qwen'), dict(inconnu='champ'),
    dict(historique=[dict(role='system', contenu='?')]),
    dict(historique=[dict(role='assistant', contenu='a' * 8001)]),
    dict(historique=[dict(role='user', contenu='?')] * 21),
    dict(historique=[dict(role='user', contenu='?', images=[])]),
])
async def test_parametres_invalides(contexte, tmp_path, invalide):
    outil, ollama = construire_analyse(contexte)
    params = dict(dict(source='source.png', prompt='?'), **invalide)
    with pytest.raises(ParameterError):
        outil.valider(params)
    with pytest.raises(ParameterError):
        await outil.executer(params, tmp_path)
    assert not ollama.appels


def test_cli_livre_le_json_via_la_file_ollama(contexte, settings, monkeypatch, capsys):
    ollama = FauxOllama([DIALOGUE, 'There are none.', 'There are none.'])
    moteurs = {nom: SimpleNamespace(start=AsyncMock(), free=AsyncMock())
               for nom in ('ollama', 'comfy', 'ace')}
    moteurs['ollama'].client = ollama
    etat = dict(gpus=[], ram=dict(percent=1, total_mb=48000, used_mb=100),
                models=[], processes=[], warnings=[])
    app = create_app(settings, overrides=dict(chemins=contexte, engines=moteurs,
        monitor=SimpleNamespace(latest=etat, sample=AsyncMock(return_value=etat))))
    with TestClient(app) as client:
        def requete(self, chemin, body=None, timeout=5):
            url = '/api/v1' + chemin
            resultat = client.get(url) if body is None else client.post(url, json=body)
            assert resultat.is_success, resultat.text
            return resultat.json()

        assert 'image.analyser' in {c['capacite'] for c in client.get('/api/v1/capacites').json()}
        monkeypatch.setattr(vertia_gen.Client, 'requete', requete)
        assert vertia_gen.main(['image.analyser', '--session', 'vertia', '--prompt', 'Que proposes-tu ?',
                                '--param', 'source=source.png', '--timeout', '5']) == 0
        assert app.state.services.jobs.list()[0]['engine'] == 'ollama'
    sortie = capsys.readouterr()
    chemin, = sortie.out.splitlines()
    fichier = Path(chemin)
    assert json.loads(fichier.read_text(encoding='utf-8'))['reponse'] == 'Deux idées.'
