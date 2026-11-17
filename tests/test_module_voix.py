from __future__ import annotations

import asyncio
from dataclasses import replace
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import runpy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psutil
import pytest

from test_api_v1 import attendre
from vertia.api import v1
from vertia.app import create_app
from vertia.chemins import ROOT, resoudre_chemins
from vertia.engines.base import EngineError
from vertia.engines.voix import TRAVAILLEURS, VoixEngine, python_travailleur
from vertia.modules.registry import RegistreModules
from vertia.tools.base import ParameterError

FAUX = Path(__file__).parent / 'fixtures/voix_travailleur.py'


def faux_moteur(chemins, **options):
    return VoixEngine(chemins, pythons={n: sys.executable for n in TRAVAILLEURS},
                      scripts={n: FAUX for n in TRAVAILLEURS}, **options)


@pytest.fixture
def contexte(tmp_path):
    chemins = resoudre_chemins(tmp_path, environ={})
    chemins.inbox_dir.mkdir()
    (chemins.inbox_dir / 'source.wav').write_bytes(b'RIFFsource')
    registre = RegistreModules(ROOT / 'modules')
    assert not registre.erreurs
    module = registre.capacites()['voix.generer']
    moteur = faux_moteur(chemins)
    outils = {n: f(None, chemins, {'voix': moteur}) for n, f in module.outils.items()}
    return SimpleNamespace(chemins=chemins, registre=registre, module=module, moteur=moteur,
                           synthese=outils['generer'], transcription=outils['transcrire'])


@pytest.fixture
async def moteur(contexte):
    try:
        yield contexte.moteur
    finally:
        await contexte.moteur.close()


def test_registre_et_sante_passive(contexte, monkeypatch):
    module = contexte.module
    assert module.capacites == ['voix.generer', 'voix.transcrire']
    assert module.lien == '/voix' and list(module.moteurs) == ['voix']
    declaration = sys.modules[module.sante.__module__]
    monkeypatch.setattr(declaration, 'resoudre_chemins', lambda: contexte.chemins)
    avant = set(contexte.chemins.inbox_dir.parent.rglob('*'))
    assert module.sante() == dict(pret=False, venvs_manquants=list(TRAVAILLEURS), poids_manquants=module.poids)
    assert set(contexte.chemins.inbox_dir.parent.rglob('*')) == avant
    for nom in TRAVAILLEURS:
        python = python_travailleur(contexte.chemins, nom)
        python.parent.mkdir(parents=True)
        python.touch()
    for poids in module.poids:
        fichier = contexte.chemins.models_dir / poids
        fichier.parent.mkdir(parents=True, exist_ok=True)
        if poids.startswith('hf/'):
            fichier.mkdir()
        else:
            fichier.touch()
    assert module.sante() == dict(pret=True, venvs_manquants=[], poids_manquants=[])
    assert module.moteurs['voix'](None, contexte.chemins).process is None


@pytest.mark.parametrize('params', [
    {}, {'prompt': ''}, {'prompt': ' '}, {'prompt': 'x' * 2001}, {'prompt': 1},
    {'moteur': 'inconnu'}, {'langue': 'de'}, {'voix': 'FF_siwis'}, {'voix': 'ff_a\n'},
    {'voix': '../voix'}, {'voix': 'ff_' + 'a' * 31}, {'reference': 1},
    {'moteur': 'kokoro', 'reference': 'source.wav'}, {'inconnu': 1},
    {'exageration': 0.24}, {'exageration': 2.01}, {'cfg': -0.01}, {'cfg': 1.01},
    {'temperature': 0.04}, {'temperature': 2.01}, {'vitesse': 0.49}, {'vitesse': 2.01},
    {'seed': -1}, {'seed': True}, {'seed': '1'}, {'seed': 0.5},
    {'cfg': True}, {'cfg': '0.3'}, {'temperature': float('nan')},
])
def test_validation_synthese(contexte, params):
    complet = {} if params == {} else dict(prompt='bonjour')
    complet.update(params)
    with pytest.raises(ParameterError):
        contexte.synthese.valider(complet)
    assert contexte.moteur.process is None


def test_defauts_et_bornes(contexte):
    assert contexte.synthese.valider({'prompt': '  Bonjour  '}) == dict(
        prompt='Bonjour', moteur='chatterbox', langue='fr', voix='ff_siwis', reference=None,
        exageration=0.5, cfg=0.3, temperature=0.7, vitesse=1.0, seed=0)
    assert contexte.transcription.valider({'source': 'source.wav'}) == dict(
        source='source.wav', modele='large-v3-turbo', langue='fr')
    for valeurs in [dict(exageration=0.25, cfg=0, temperature=0.05, vitesse=0.5),
                    dict(exageration=2, cfg=1, temperature=2, vitesse=2)]:
        assert contexte.synthese.valider(dict(prompt='x', **valeurs))


@pytest.mark.parametrize('params', [
    {}, {'source': None}, {'source': 1}, {'source': ''}, {'source': '../source.wav'},
    {'source': '..\\source.wav'}, {'source': '/source.wav'}, {'source': 'a/b.wav'},
    {'source': 'a..wav'}, {'source': 'été.wav'}, {'source': 'a.wav:flux'},
    {'source': 'absent.wav'}, {'source': 'a.txt'}, {'source': 'a' * 101},
    {'modele': 'large'}, {'langue': 'de'}, {'prompt': 'interdit'}, {'inconnu': 1},
])
def test_validation_transcription(contexte, params):
    complet = {} if params == {} else dict(source='source.wav')
    complet.update(params)
    with pytest.raises(ParameterError):
        contexte.transcription.valider(complet)


@pytest.mark.parametrize('nom', ['../source.wav', 'a.ogg', '', 'inexistant.wav'])
def test_reference_invalide(contexte, nom):
    with pytest.raises(ParameterError):
        contexte.synthese.valider(dict(prompt='x', reference=nom))


@pytest.mark.parametrize('champ,limite', [('source', 200), ('reference', 64)])
def test_limites_audio(contexte, champ, limite):
    chemin = contexte.chemins.inbox_dir / 'grand.wav'
    with chemin.open('wb') as stream:
        stream.truncate(limite * 1024**2 + 1)
    outil = contexte.synthese if champ == 'reference' else contexte.transcription
    with pytest.raises(ParameterError):
        outil.valider(dict(prompt='x', reference=chemin.name) if champ == 'reference' else dict(source=chemin.name))


@pytest.mark.parametrize('type_lien', ['dur', 'symbolique'])
def test_liens_inbox_refuses(contexte, type_lien):
    source = contexte.chemins.inbox_dir / 'source.wav'
    lien = source.with_name('lien.wav')
    if type_lien == 'dur':
        os.link(source, lien)
    else:
        try:
            lien.symlink_to(source)
        except OSError:
            pytest.skip('Création de liens symboliques non autorisée sur cet hôte.')
    for outil, params in [(contexte.synthese, dict(prompt='x', reference=lien.name)),
                          (contexte.transcription, dict(source=lien.name))]:
        with pytest.raises(ParameterError):
            outil.valider(params)


async def test_demarrage_paresseux_et_bascule(moteur, tmp_path):
    await moteur.start()
    assert moteur.process is None and await moteur.health()
    assert moteur.memory.vram_mb is None
    assert await moteur.requete('chatterbox', {'action': 'synthese'}, tmp_path) == ['voix_1.wav']
    premier = moteur.process
    assert premier.poll() is None and await moteur.health()
    await moteur.requete('chatterbox', {'action': 'synthese'}, tmp_path)
    assert moteur.process is premier
    await moteur.requete('whisper', dict(action='transcription', chemin_audio=str(tmp_path / 'voix_1.wav')), tmp_path)
    assert premier.poll() is not None and moteur.process.pid != premier.pid
    assert moteur.travailleur == 'whisper'


async def test_lancement_isole(moteur, tmp_path):
    moteur.launcher = Mock(wraps=subprocess.Popen)
    await moteur.requete('kokoro', {'action': 'synthese'}, tmp_path)
    args, options = moteur.launcher.call_args
    assert args[0] == [sys.executable, '-u', '-B', str(FAUX.resolve()), '--device', 'cuda']
    assert options['cwd'] == FAUX.parent
    assert options['stderr'] is moteur._journal and options['stderr'] != subprocess.PIPE
    assert options['env']['HF_HOME'] == str(moteur.chemins.models_dir / 'hf')
    assert options['env']['HF_HUB_OFFLINE'] == options['env']['TRANSFORMERS_OFFLINE'] == '1'
    assert options['env']['VERTIA_WHISPER_DIR'] == str(moteur.chemins.models_dir / 'whisper')
    assert options['env']['PYTHONIOENCODING'] == 'utf-8'
    assert options['creationflags'] == (subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


@pytest.mark.parametrize('mode', ['sans_pret', 'faux_pret'])
async def test_pret_manquant(moteur, tmp_path, monkeypatch, mode):
    monkeypatch.setenv('VERTIA_FAUX_VOIX_MODE', mode)
    moteur.delai_pret = 0.3
    with pytest.raises(EngineError, match='Délai|prêt'):
        await moteur.requete('kokoro', {'action': 'synthese'}, tmp_path)
    assert moteur.process is None and moteur._journal is None


@pytest.mark.parametrize('action,message', [('mort', 'arrêté'), ('illisible', 'illisible'),
                                           ('structure', 'illisible'), ('refus', 'refusé')])
async def test_erreurs_protocole(moteur, tmp_path, action, message):
    with pytest.raises(EngineError, match=message):
        await moteur.requete('kokoro', {'action': action}, tmp_path)
    assert moteur.process is None


async def test_delai_requete(moteur, tmp_path):
    moteur.delai_requete = 0.2
    with pytest.raises(EngineError, match='Délai'):
        await moteur.requete('kokoro', {'action': 'attendre'}, tmp_path)
    assert moteur.process is None


async def test_annulation(moteur, tmp_path):
    task = asyncio.create_task(moteur.requete('kokoro', {'action': 'attendre'}, tmp_path))
    async with asyncio.timeout(10):
        while not (tmp_path / 'entree.marker').exists():
            await asyncio.sleep(.01)
    process = moteur.process
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.poll() is not None and moteur.process is None


async def test_free_tue_arbre(moteur, tmp_path):
    await moteur.requete('kokoro', {'action': 'arbre'}, tmp_path)
    process = moteur.process
    enfant = psutil.Process(int((tmp_path / 'arbre.pid').read_text()))
    try:
        await moteur.free()
        assert process.poll() is not None and not enfant.is_running()
        assert moteur.process is None and await moteur.health()
        await moteur.free()
    finally:
        if enfant.is_running():
            enfant.kill()
            enfant.wait(5)


async def test_verrou_requetes(moteur, tmp_path):
    dossiers = [tmp_path / str(n) for n in range(3)]
    for dossier in dossiers:
        dossier.mkdir()
    await asyncio.gather(*(moteur.requete('kokoro', {'action': 'synthese'}, p) for p in dossiers))
    assert all((p / 'voix_1.wav').read_bytes().startswith(b'RIFF') for p in dossiers)


@pytest.mark.parametrize('nom', ['chatterbox', 'kokoro'])
async def test_outil_synthese(contexte, moteur, tmp_path, nom):
    params = dict(prompt=' Bonjour ', moteur=nom)
    if nom == 'chatterbox':
        params['reference'] = 'source.wav'
    fichiers = await contexte.synthese.executer(params, tmp_path)
    assert [p.name for p in fichiers] == ['voix_1.wav']
    assert fichiers[0].read_bytes().startswith(b'RIFF')
    demande = json.loads((tmp_path / 'requete.json').read_text())
    assert demande['texte'] == 'Bonjour' and demande['action'] == 'synthese'
    if nom == 'chatterbox':
        assert Path(demande['reference']).read_bytes() == b'RIFFsource'
        assert Path(demande['reference']).parent == tmp_path
        assert 'voix' not in demande and 'vitesse' not in demande
    else:
        assert demande['voix'] == 'ff_siwis' and 'reference' not in demande


async def test_reference_par_defaut(contexte, moteur, tmp_path):
    await contexte.synthese.executer({'prompt': 'x'}, tmp_path)
    demande = json.loads((tmp_path / 'requete.json').read_text())
    assert demande['reference'] == str((contexte.chemins.models_dir / 'voix/references/kokoro_ff_siwis.wav').resolve())


async def test_outil_transcription(contexte, moteur, tmp_path):
    fichiers = await contexte.transcription.executer(dict(source='source.wav', langue='auto'), tmp_path)
    assert [p.name for p in fichiers] == ['transcription.txt', 'transcription.json']
    assert fichiers[0].read_text(encoding='utf-8') == 'Bonjour été'
    assert json.loads(fichiers[1].read_text())['langue'] == 'fr'
    demande = json.loads((tmp_path / 'requete.json').read_text())
    assert demande['langue'] is None and demande['modele'] == 'large-v3-turbo'
    assert Path(demande['chemin_audio']).read_bytes() == b'RIFFsource'


@pytest.mark.parametrize('cas', ['absent', 'vide', 'invalide'])
async def test_resultats_synthese_invalides(contexte, tmp_path, cas):
    contexte.synthese.adapter = SimpleNamespace(requete=AsyncMock(return_value=[]))
    if cas != 'absent':
        (tmp_path / 'voix_1.wav').write_bytes(b'' if cas == 'vide' else b'invalide')
    with pytest.raises(EngineError):
        await contexte.synthese.executer({'prompt': 'x'}, tmp_path)


@pytest.fixture
def voix_api(settings, contexte):
    module = replace(contexte.module, moteurs={'voix': lambda s, c: contexte.moteur})
    contexte.registre._modules['voix'] = module
    for capacite in module.capacites:
        contexte.registre._capacites[capacite] = module
    engines = {nom: SimpleNamespace(start=AsyncMock(), free=AsyncMock()) for nom in ('ollama', 'ace', 'comfy')}
    state = dict(gpus=[], ram=dict(percent=1, total_mb=48000, used_mb=100), models=[], processes=[], warnings=[])
    app = create_app(settings, overrides=dict(
        modules=contexte.registre, chemins=contexte.chemins, engines=engines,
        monitor=SimpleNamespace(latest=state, sample=AsyncMock(return_value=state))))
    assert not contexte.registre.erreurs
    with TestClient(app) as client:
        yield client, app, contexte


@pytest.mark.parametrize('capacite,params,noms', [
    ('voix.generer', {'prompt': 'Bonjour'}, ['essai_1.wav']),
    ('voix.transcrire', {'source': 'source.wav'}, ['essai_1_1.txt', 'essai_1_2.json']),
])
def test_boucle_demandes_voix(voix_api, capacite, params, noms):
    client, app, contexte = voix_api
    assert {c['capacite'] for c in client.get('/api/v1/capacites').json()} >= {'voix.generer', 'voix.transcrire'}
    response = client.post('/api/v1/demandes', json=dict(session='vertia', capacite=capacite, params=params))
    assert response.status_code == 202, response.text
    demande_id = response.json()['id']
    demande = attendre(client, demande_id)
    assert demande['etat'] == 'livre', demande
    assert [Path(p).name for p in demande['chemins']] == noms
    assert app.state.services.jobs.list()[0]['engine'] == 'voix'
    for index, path in enumerate(demande['chemins']):
        response = client.get(f'/api/v1/demandes/{demande_id}/fichiers/{index}')
        assert response.status_code == 200 and response.content == Path(path).read_bytes()
    assert client.get(f'/api/v1/demandes/{demande_id}/fichiers/99').status_code == 404
    assert client.get('/voix').status_code == 200
    assert client.get('/modules/voix/static/voix.js').status_code == 200


@pytest.fixture
def fichiers_api(tmp_path):
    outbox = tmp_path / 'outbox'
    outbox.mkdir()
    chemins = []
    app = FastAPI()
    app.include_router(v1.router)
    app.state.services = SimpleNamespace(demandes=SimpleNamespace(
        get=lambda demande_id: {'chemins': chemins}, livraison=SimpleNamespace(outbox=outbox)))
    with TestClient(app) as client:
        yield client, outbox, chemins


@pytest.mark.parametrize('extension,mime', [('wav', 'audio/wav'), ('txt', 'text/plain; charset=utf-8'),
                                          ('json', 'application/json'), ('png', 'image/png')])
def test_fichiers_mime(fichiers_api, extension, mime):
    client, outbox, chemins = fichiers_api
    fichier = outbox / ('test.' + extension)
    fichier.write_bytes(b'contenu')
    chemins.append(str(fichier))
    response = client.get('/api/v1/demandes/abc123/fichiers/0')
    assert response.status_code == 200 and response.headers['content-type'] == mime


@pytest.mark.parametrize('cas', ['hors_outbox', 'traversee', 'lien_dur', 'dossier', 'absent', 'extension'])
def test_fichiers_refuses(fichiers_api, tmp_path, cas):
    client, outbox, chemins = fichiers_api
    fichier = outbox / 'test.wav'
    fichier.write_bytes(b'RIFFtest')
    if cas in {'hors_outbox', 'traversee'}:
        externe = tmp_path / 'externe.wav'
        externe.write_bytes(b'prive')
        fichier = externe if cas == 'hors_outbox' else outbox / '..' / 'externe.wav'
    elif cas == 'lien_dur':
        os.link(fichier, outbox / 'lien.wav')
    elif cas == 'dossier':
        fichier = outbox
    elif cas == 'absent':
        fichier = outbox / 'absent.wav'
    elif cas == 'extension':
        fichier = fichier.rename(outbox / 'test.exe')
    chemins.append(str(fichier))
    assert client.get('/api/v1/demandes/abc/fichiers/0').status_code == 404
    assert client.get('/api/v1/demandes/abc/fichiers/-1').status_code == 404
    assert client.get('/api/v1/demandes/a.b/fichiers/0').status_code == 404


def test_fichier_lien_symbolique_refuse(fichiers_api):
    client, outbox, chemins = fichiers_api
    source = outbox / 'source.wav'
    source.write_bytes(b'RIFFtest')
    lien = outbox / 'lien.wav'
    try:
        lien.symlink_to(source)
    except OSError:
        pytest.skip('Création de liens symboliques non autorisée sur cet hôte.')
    chemins.append(str(lien))
    assert client.get('/api/v1/demandes/abc/fichiers/0').status_code == 404


def test_televersement(voix_api, monkeypatch):
    client, app, contexte = voix_api
    url = '/api/v1/inbox?extension=WAV'
    headers = {'Content-Type': 'application/octet-stream'}
    response = client.post(url, content=b'RIFFaudio', headers=headers)
    assert response.status_code == 200
    nom = response.json()['nom']
    assert nom.startswith('voix_') and nom.endswith('.wav') and len(nom) == 41
    assert (contexte.chemins.inbox_dir / nom).read_bytes() == b'RIFFaudio'
    for extension in ['txt', '../wav', 'exe', 'wav/../../test']:
        assert client.post('/api/v1/inbox', params={'extension': extension}, content=b'x', headers=headers).status_code == 422
    avant = set(contexte.chemins.inbox_dir.iterdir())
    monkeypatch.setattr(v1, 'LIMITE_AUDIO', 4)
    assert client.post(url, content=b'12345', headers=headers).status_code == 413
    assert set(contexte.chemins.inbox_dir.iterdir()) == avant
    assert client.post(url, content=b'1234', headers=headers).status_code == 200
    assert client.post(url, content=b'x', headers={'Content-Type': 'text/plain'}).status_code == 415
    if not v1.MULTIPART_DISPONIBLE:
        assert client.post('/api/v1/inbox', files={'fichier': ('test.wav', b'x')}).status_code == 415


def test_televersement_image(voix_api, monkeypatch):
    client, app, contexte = voix_api
    headers = {'Content-Type': 'application/octet-stream'}
    response = client.post('/api/v1/inbox?extension=PNG', content=b'\x89PNG', headers=headers)
    assert response.status_code == 200
    nom = response.json()['nom']
    assert nom.startswith('image_') and nom.endswith('.png')
    assert (contexte.chemins.inbox_dir / nom).read_bytes() == b'\x89PNG'
    monkeypatch.setattr(v1, 'LIMITE_IMAGE', 4)
    assert client.post('/api/v1/inbox?extension=jpg', content=b'12345', headers=headers).status_code == 413
    assert client.post('/api/v1/inbox?extension=webp', content=b'1234', headers=headers).status_code == 200
    assert client.post('/api/v1/inbox?extension=gif', content=b'x', headers=headers).status_code == 422


@pytest.mark.parametrize('args', [['voix', '--prompt', 'Bonjour'],
                                  ['voix.transcrire', '--param', 'source=source.wav']])
def test_cli_voix_en_memoire(voix_api, monkeypatch, capsys, args):
    from test_vertia_gen import brancher_cli_en_memoire, cli

    client, _, _ = voix_api
    brancher_cli_en_memoire(monkeypatch, client)
    lanceur = Mock(side_effect=AssertionError('Lancement réel interdit'))
    assert cli.main([*args, '--session', 'vertia'], lanceur=lanceur) == 0
    fichiers = capsys.readouterr().out.splitlines()
    assert fichiers and all(Path(f).is_file() for f in fichiers)
    lanceur.assert_not_called()


def executer_script(nom, params, monkeypatch):
    canal = StringIO()
    with monkeypatch.context() as patch:
        patch.setattr(sys, 'path', list(sys.path))
        patch.setattr(sys, 'argv', ['travailleur_' + nom + '.py', '--device', 'cuda'])
        patch.setattr(sys, 'stdin', StringIO(''.join(json.dumps(p) + '\n' for p in params)))
        patch.setattr(sys, 'stdout', canal)
        runpy.run_path(str(ROOT / 'modules/voix/travailleurs' / ('travailleur_' + nom + '.py')), run_name='__main__')
    return [json.loads(ligne) for ligne in canal.getvalue().splitlines()]


@pytest.fixture
def bibliotheques(monkeypatch):
    numpy = SimpleNamespace(random=SimpleNamespace(seed=Mock()), asarray=lambda v: v,
                            concatenate=Mock(return_value=[0, 1]))
    torch = SimpleNamespace(manual_seed=Mock(), set_num_threads=Mock(),
                            cuda=SimpleNamespace(is_available=lambda: True, manual_seed_all=Mock()))

    def ecrire(chemin, audio, frequence):
        print('Sortie de bibliothèque vers stderr')
        Path(chemin).write_bytes(b'RIFFfactice')

    soundfile = SimpleNamespace(write=Mock(side_effect=ecrire))
    for nom, bibliotheque in [('numpy', numpy), ('torch', torch), ('soundfile', soundfile)]:
        monkeypatch.setitem(sys.modules, nom, bibliotheque)
    return SimpleNamespace(numpy=numpy, torch=torch, soundfile=soundfile)


def test_script_chatterbox_sans_modele(contexte, tmp_path, monkeypatch, bibliotheques):
    modele = SimpleNamespace(sr=24000, generate=Mock(return_value=MagicMock()))
    tts = SimpleNamespace(from_pretrained=Mock(return_value=modele))
    monkeypatch.setitem(sys.modules, 'chatterbox.mtl_tts', SimpleNamespace(ChatterboxMultilingualTTS=tts))
    params = dict(action='synthese', texte='Bonjour', langue='fr', seed=42, reference='reference.wav',
                  exageration=0.5, cfg=0.3, temperature=0.7, sortie=str(tmp_path))
    assert executer_script('chatterbox', [params], monkeypatch) == [
        {'pret': True}, {'ok': True, 'fichiers': ['voix_1.wav']}]
    tts.from_pretrained.assert_called_once_with(device='cuda')
    modele.generate.assert_called_once_with('Bonjour', language_id='fr', audio_prompt_path='reference.wav',
                                            exaggeration=0.5, cfg_weight=0.3, temperature=0.7)
    bibliotheques.torch.set_num_threads.assert_called_once_with(6)
    bibliotheques.numpy.random.seed.assert_called_once_with(42)
    bibliotheques.torch.manual_seed.assert_called_once_with(42)
    bibliotheques.torch.cuda.manual_seed_all.assert_called_once_with(42)
    assert (tmp_path / 'voix_1.wav').read_bytes().startswith(b'RIFF')


def test_script_kokoro_cache_et_concatenation(tmp_path, monkeypatch, bibliotheques):
    audio = MagicMock()
    audio.cpu.return_value.numpy.return_value = [0, 1]
    pipe = Mock(side_effect=lambda *a, **k: iter([('', '', audio), ('', '', audio)]))
    pipeline = Mock(return_value=pipe)
    monkeypatch.setitem(sys.modules, 'kokoro', SimpleNamespace(KPipeline=pipeline))
    assert executer_script('kokoro', [], monkeypatch) == [{'pret': True}]
    pipeline.assert_not_called()
    params = dict(action='synthese', texte='Bonjour', langue='fr', voix='ff_siwis', vitesse=1,
                  seed=42, sortie=str(tmp_path))
    reponses = executer_script('kokoro', [params, params, dict(params, langue='en')], monkeypatch)
    assert all(r.get('ok') for r in reponses[1:])
    assert [a.kwargs['lang_code'] for a in pipeline.call_args_list] == ['f', 'a']
    assert all(a.kwargs['device'] == 'cuda' and a.kwargs['repo_id'] == 'hexgrad/Kokoro-82M'
               for a in pipeline.call_args_list)
    bibliotheques.numpy.concatenate.assert_called_with([[0, 1], [0, 1]])
    bibliotheques.soundfile.write.assert_called_with(tmp_path / 'voix_1.wav', [0, 1], 24000)


def test_script_whisper_hors_ligne_et_cache(tmp_path, monkeypatch):
    poids = tmp_path / 'poids'
    poids.mkdir()
    monkeypatch.setenv('VERTIA_WHISPER_DIR', str(poids))
    modele = SimpleNamespace(transcribe=Mock(return_value=dict(
        text='  Bonjour été  ', language='fr', segments=[dict(start=0, end=1.5, text=' été ')])))
    charger = Mock(return_value=modele)
    monkeypatch.setitem(sys.modules, 'whisper', SimpleNamespace(load_model=charger))
    params = dict(action='transcription', modele='tiny', langue=None, chemin_audio='source.wav', sortie=str(tmp_path))
    assert executer_script('whisper', [], monkeypatch) == [{'pret': True}]
    reponses = executer_script('whisper', [params], monkeypatch)
    assert reponses[1]['ok'] is False
    charger.assert_not_called()
    for nom in ['tiny', 'base']:
        (poids / (nom + '.pt')).touch()
    reponses = executer_script('whisper', [params, params, dict(params, modele='base')], monkeypatch)
    assert all(r.get('ok') for r in reponses[1:])
    assert [a.args[0] for a in charger.call_args_list] == ['tiny', 'base']
    charger.assert_called_with('base', device='cuda', download_root=str(poids))
    modele.transcribe.assert_called_with('source.wav', language=None, fp16=True)
    assert (tmp_path / 'transcription.txt').read_text(encoding='utf-8') == 'Bonjour été'
    assert json.loads((tmp_path / 'transcription.json').read_text(encoding='utf-8')) == dict(
        texte='Bonjour été', langue='fr', segments=[dict(debut=0, fin=1.5, texte='été')])
