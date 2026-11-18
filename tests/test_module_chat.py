from dataclasses import replace
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
import httpx
import pytest

from test_api_v1 import attendre
from test_jobs import FakeMonitor
from vertia.app import create_app
from vertia.chemins import ROOT, resoudre_chemins
from vertia.engines.base import EngineError
from vertia.engines.ollama import OllamaClient
from vertia.modules.registry import RegistreModules
from vertia.tools.base import ParameterError
from modules.chat.outil import OutilChat


class FakeOllama(OllamaClient):
    def __init__(self, num_ctx=1024):
        self.requetes = []
        self.texte = '  Bonjour **local**.\n'
        self.modeles = [{'name': 'factice:latest', 'digest': 'sha256:factice'}]
        self.charges = [{'name': 'autre'}]
        self.verifier = lambda: None
        self.statut = 200
        super().__init__('http://ollama.test', num_ctx, httpx.AsyncClient(
            base_url='http://ollama.test', transport=httpx.MockTransport(self.repondre)))

    def repondre(self, request):
        body = json.loads(request.content) if request.content else None
        self.requetes.append((request.url.path, body))
        if request.url.path == '/api/ps':
            return httpx.Response(200, json={'models': self.charges})
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': self.modeles})
        if request.url.path == '/api/generate':
            self.charges = [m for m in self.charges if m['name'] != body['model']]
            return httpx.Response(200, json={'done': True})
        assert request.url.path == '/api/chat'
        self.verifier()
        return httpx.Response(self.statut, json=dict(
            model=body['model'], message=dict(role='assistant', content=self.texte),
            done=True, prompt_eval_count=42, eval_count=7))


@pytest.fixture
async def contexte(settings, tmp_path):
    fake = FakeOllama()
    config = replace(settings, default_model='factice', num_ctx=1024)
    outil = OutilChat(config, resoudre_chemins(tmp_path, environ={}), {'ollama': SimpleNamespace(client=fake)})
    try:
        yield SimpleNamespace(fake=fake, outil=outil, settings=config)
    finally:
        await fake.close()


@pytest.mark.parametrize('params', [
    {}, {'prompt': ''}, {'prompt': ' \n'}, {'prompt': 'x' * 32001}, {'prompt': 1},
    {'modele': ''}, {'modele': '-model'}, {'modele': 'a b'}, {'modele': 'a\n'},
    {'modele': 'x' * 129}, {'modele': 1}, {'systeme': 'x' * 8001}, {'systeme': None},
    {'historique': {}}, {'historique': 'texte'}, {'historique': [None]},
    {'historique': [{}]}, {'historique': [{'role': 'system', 'contenu': 'x'}]},
    {'historique': [{'role': 'user', 'contenu': 1}]},
    {'historique': [{'role': 'user', 'contenu': 'x', 'extra': True}]},
    {'historique': [{'role': 'assistant', 'contenu': 'x' * 32001}]},
    {'historique': [{'role': 'user', 'contenu': ''}] * 51},
    {'temperature': -0.1}, {'temperature': 2.1}, {'temperature': '1'}, {'temperature': True},
    {'temperature': float('nan')}, {'temperature': float('inf')},
    {'num_predict': 0}, {'num_predict': 8193}, {'num_predict': '1'}, {'num_predict': True},
    {'num_predict': 1.5}, {'seed': -1}, {'seed': 2**31}, {'seed': True}, {'seed': '1'},
    {'seed': 1.5}, {'extra': 'interdit'},
])
async def test_validation_stricte(contexte, params):
    complet = dict(prompt='Bonjour') if params else {}
    complet.update(params)
    with pytest.raises(ParameterError):
        contexte.outil.valider(complet)
    assert not contexte.fake.requetes


async def test_defauts_et_bornes(contexte):
    params = contexte.outil.valider(dict(prompt=' Bonjour '))
    assert params == dict(prompt=' Bonjour ', modele='factice', systeme='', historique=None,
                          temperature=None, num_predict=None, seed=None)
    for borne in [dict(temperature=0, num_predict=1, seed=0),
                  dict(temperature=2, num_predict=8192, seed=2**31 - 1)]:
        assert contexte.outil.valider(dict(prompt='x' * 32000, systeme='x' * 8000,
            modele='a' * 128, historique=[dict(role='assistant', contenu='x' * 32000)] * 50, **borne))
    assert contexte.outil.valider(dict(prompt='x', modele='registry.example:5000/org/model:Q4_K-M'))


async def test_requete_parametres_et_fichiers(contexte, tmp_path):
    fichiers = await contexte.outil.executer(dict(
        prompt='suite', modele='factice', systeme='Sois précis',
        historique=[dict(role='user', contenu='question'), dict(role='assistant', contenu='réponse')],
        temperature=0.2, num_predict=128, seed=42), tmp_path)
    assert [p.name for p in fichiers] == ['reponse_1.md', 'reponse_1.json']
    assert fichiers[0].read_bytes() == contexte.fake.texte.encode('utf-8')
    requete = next(body for chemin, body in contexte.fake.requetes if chemin == '/api/chat')
    assert requete == dict(model='factice', stream=False, keep_alive=-1, options=dict(
        num_ctx=1024, num_predict=128, temperature=0.2, seed=42), messages=[
            dict(role='system', content='Sois précis'), dict(role='user', content='question'),
            dict(role='assistant', content='réponse'), dict(role='user', content='suite')])
    assert [chemin for chemin, _ in contexte.fake.requetes][:3] == ['/api/ps', '/api/generate', '/api/chat']
    assert contexte.fake.requetes[1][1]['keep_alive'] == 0
    metadata = json.loads(fichiers[1].read_text(encoding='utf-8'))
    assert isinstance(metadata, dict)
    assert metadata['modele'] == 'factice' and metadata['digest'] == 'sha256:factice'
    assert metadata['parametres'] == requete['options']
    assert metadata['prompt_eval_count'] == 42 and metadata['eval_count'] == 7
    assert metadata['elapsed_s'] >= 0


@pytest.mark.parametrize('tags', [[], [{'name': 'autre', 'digest': 'inconnu'}], [{'name': 'factice'}], None])
async def test_digest_optionnel_et_options_par_defaut(contexte, tmp_path, tags):
    contexte.fake.modeles = tags
    if tags is None:
        contexte.fake.models = AsyncMock(side_effect=httpx.ReadTimeout('Indisponible'))
    fichiers = await contexte.outil.executer(dict(prompt='bonjour'), tmp_path)
    metadata = json.loads(fichiers[1].read_text(encoding='utf-8'))
    assert metadata['digest'] == 'non disponible'
    assert metadata['parametres'] == dict(num_ctx=1024, num_predict=256)


@pytest.mark.parametrize('texte', ['', ' \n\t', None, 7])
async def test_reponse_vide_ou_invalide_refusee(contexte, tmp_path, texte):
    contexte.fake.texte = texte
    with pytest.raises(EngineError, match='vide'):
        await contexte.outil.executer(dict(prompt='bonjour'), tmp_path)
    assert not list(tmp_path.glob('reponse_*'))


async def test_erreur_http_sans_reponse_externe(contexte, tmp_path):
    contexte.fake.statut = 500
    with pytest.raises(EngineError, match='requête chat Ollama'):
        await contexte.outil.executer(dict(prompt='bonjour'), tmp_path)
    assert not list(tmp_path.glob('reponse_*'))


@pytest.mark.parametrize('params', [dict(prompt='x' * 3000), dict(prompt='x', systeme='x' * 3000),
    dict(prompt='x', historique=[dict(role='user', contenu='x' * 3000)]), dict(prompt='x', num_predict=1024)])
async def test_contexte_depasse_refuse_avant_ollama(contexte, tmp_path, params):
    with pytest.raises(ParameterError, match='num_ctx'):
        await contexte.outil.executer(params, tmp_path)
    assert not contexte.fake.requetes and not list(tmp_path.glob('reponse_*'))


def test_registre_et_sante_passive(tmp_path, monkeypatch):
    registre = RegistreModules()
    assert not registre.erreurs
    module = registre.capacites()['chat.generer']
    assert (module.nom, module.activite, module.titre, module.version, module.lien) == (
        'chat', 'chat', 'Discussion', '0.1.0', None)
    assert module.capacites == ['chat.generer']
    assert module.moteurs == module.besoins == {} and module.poids == []
    executable = tmp_path / 'ollama.exe'
    from vertia.config import Settings
    envoyer = AsyncMock(side_effect=AssertionError('Réseau interdit'))
    monkeypatch.setattr(httpx.AsyncClient, 'send', envoyer)
    for chemin, present in [('', None), (str(executable), False), (str(executable), True)]:
        if present:
            executable.touch()
        monkeypatch.setattr(Settings, 'from_env', lambda: SimpleNamespace(ollama_executable=chemin))
        avant = set(tmp_path.rglob('*'))
        diagnostic = module.sante()
        assert diagnostic['pret'] is (present is not False)
        assert 'non contacté' in diagnostic['message']
        assert set(tmp_path.rglob('*')) == avant
    envoyer.assert_not_called()


@pytest.fixture
def chat_api(settings, tmp_path):
    fake = FakeOllama()
    app = create_app(replace(settings, default_model='factice', num_ctx=1024,
                             preload_ollama=False, engine_idle_seconds=0), overrides=dict(
        ollama=fake, chemins=resoudre_chemins(tmp_path, environ={}), monitor=FakeMonitor(),
        engines={nom: SimpleNamespace(start=AsyncMock(), free=AsyncMock()) for nom in ('ace', 'comfy')}))
    services = app.state.services
    assert not services.modules.erreurs
    assert services.demandes.outils['chat.generer'][0].client is services.ollama is services.chat.ollama

    def verifier():
        assert services.arbiter.active == 'ollama'
        assert services.jobs.active is not None
        assert services.arbiter.lock.locked() and services.arbiter.travaux_actifs == 1

    fake.verifier = verifier
    with TestClient(app) as client:
        yield client, services, fake


def test_boucle_demandes_et_mime_markdown(chat_api):
    client, services, fake = chat_api
    assert 'chat.generer' in {c['capacite'] for c in client.get('/api/v1/capacites').json()}
    activity = next(a for a in client.get('/api/v1/modules').json()['activites'] if a['activite'] == 'chat')
    assert activity['modules'][0]['lien'] is None
    demande_id = client.post('/api/v1/demandes', json=dict(session='vertia', capacite='chat.generer',
                                                         params=dict(prompt='Bonjour'))).json()['id']
    demande = attendre(client, demande_id)
    assert demande['etat'] == 'livre', demande
    assert [Path(p).suffix for p in demande['chemins']] == ['.md', '.json']
    assert services.jobs.get(demande['essais'][0]['job_id'])['engine'] == 'ollama'
    for index, mime in enumerate(['text/markdown; charset=utf-8', 'application/json']):
        fichier = client.get(f'/api/v1/demandes/{demande_id}/fichiers/{index}')
        assert fichier.status_code == 200 and fichier.headers['content-type'] == mime
        assert fichier.content == Path(demande['chemins'][index]).read_bytes()
    assert Path(demande['chemins'][0]).read_text(encoding='utf-8') == fake.texte
    assert isinstance(json.loads(Path(demande['chemins'][1]).read_text(encoding='utf-8')), dict)
    assert client.post(f'/api/v1/demandes/{demande_id}/retour', json={'verdict': 'a_refaire'}).status_code == 200
    assert attendre(client, demande_id)['etat'] == 'livre'
    assert len(services.demandes.get(demande_id)['essais']) == 2


@pytest.mark.parametrize('capacite', ['chat', 'chat.generer'])
def test_cli_chat_en_memoire(chat_api, monkeypatch, capsys, capacite):
    from test_vertia_gen import brancher_cli_en_memoire, cli

    client, _, _ = chat_api
    brancher_cli_en_memoire(monkeypatch, client)
    lanceur = Mock(side_effect=AssertionError('Lancement réel interdit'))
    assert cli.main([capacite, '--session', 'vertia', '--prompt', 'Bonjour',
                     '--param', 'temperature=0.5', 'seed=0'], lanceur=lanceur) == 0
    fichiers = capsys.readouterr().out.splitlines()
    assert len(fichiers) == 2 and all(Path(p).is_file() for p in fichiers)
    assert [Path(p).suffix for p in fichiers] == ['.md', '.json']
    lanceur.assert_not_called()


def test_accueil_discussion_avec_module_declare():
    script = r'''
import fs from 'node:fs';
import assert from 'node:assert/strict';
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.dataset = {}; this.events = {}; }
  append(...nodes) { this.children.push(...nodes); }
  addEventListener(name, action) { this.events[name] = action; }
  setAttribute(name, value) { this[name] = value; }
}
const ids = new Map(['ouvrir-accueil', 'accueil-discussion', 'installation-fermer', 'panel-toggles',
  'accueil-activites', 'accueil-statut', 'accueil-erreurs'].map(id => [id, new Element()]));
globalThis.document = { body: new Element(), getElementById: id => ids.get(id), createElement: tag => new Element(tag) };
globalThis.location = { href: 'http://vertia.test/' };
globalThis.resultat = { activites: [{activite:'chat', titre:'Discussion', modules:[{
  nom:'chat', titre:'Discussion', lien:null, version:'0.1.0', sante:{pret:true}}]}], erreurs:[] };
globalThis.panneaux = [];
let source = fs.readFileSync('src/vertia/static/js/accueil.js', 'utf8')
  .replace('import { api } from "./api.js";', 'const api = async () => globalThis.resultat;')
  .replace('import { setPanel } from "./panels.js";', 'const setPanel = (...args) => globalThis.panneaux.push(args);');
const module = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
module.initAccueil();
await new Promise(resolve => setImmediate(resolve));
const section = ids.get('accueil-activites').children[0];
assert.equal(section.children.length, 2);
const button = section.children[1];
assert.equal(button.tagName, 'button');
button.events.click();
assert.equal(document.body.dataset.vue, 'discussion');
assert.deepEqual(panneaux, [['chat', true]]);
assert.equal(ids.get('ouvrir-accueil')['aria-pressed'], 'false');
'''
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
