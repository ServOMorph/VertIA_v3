from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from test_api_v1 import attendre
from vertia.api import v1
from vertia.app import create_app
from vertia.chemins import ROOT, resoudre_chemins
from vertia.engines.base import EngineError
from vertia.engines.travailleurs import MoteurTravailleurs
from vertia.modules.registry import RegistreModules
from vertia.tools.base import ParameterError

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def contexte(tmp_path):
    chemins = resoudre_chemins(tmp_path, environ={})
    chemins.inbox_dir.mkdir()
    (chemins.inbox_dir / 'source.wav').write_bytes(b'RIFFsource')
    registre = RegistreModules(ROOT / 'modules')
    assert not registre.erreurs
    module = registre.capacites()['musique.generer']
    moteur = module.moteurs['musique'](None, chemins)
    moteur.pythons['acestep'] = sys.executable
    moteur.scripts['acestep'] = FIXTURES / 'musique_travailleur.py'
    outil = module.outils['generer'](None, chemins, {'musique': moteur})
    return SimpleNamespace(chemins=chemins, registre=registre, module=module, moteur=moteur, outil=outil)


@pytest.fixture
async def moteur(contexte):
    try:
        yield contexte.moteur
    finally:
        await contexte.moteur.close()


@pytest.mark.parametrize('params', [
    {}, {'prompt': ''}, {'prompt': ' '}, {'prompt': 'x' * 1001}, {'prompt': 1},
    {'paroles': 'x' * 8001}, {'paroles': None}, {'paroles': 1},
    {'instrumental': True, 'paroles': 'texte'}, {'instrumental': None}, {'instrumental': 1},
    {'instrumental': 'true'}, {'langue': 'FR'}, {'langue': 'fra'}, {'langue': 'en\n'},
    {'duree': 9.9}, {'duree': 600.1}, {'duree': True}, {'duree': '30'}, {'duree': float('nan')},
    {'duree': float('inf')}, {'seed': -1}, {'seed': 2**32}, {'seed': True}, {'seed': 0.5},
    {'etapes': 0}, {'etapes': 101}, {'etapes': '8'}, {'etapes': True},
    {'lm': 'false'}, {'lm': 1}, {'ajuster_paroles': None}, {'ajuster_paroles': 0},
    {'tache': ''}, {'tache': 'Cover'}, {'tache': 'x' * 41}, {'tache': 'cover\n'},
    {'force_cover': -0.1}, {'force_cover': 1.1}, {'force_audio': -0.1}, {'force_audio': 1.1},
    {'force_audio': True}, {'force_cover': float('nan')}, {'bpm': 29}, {'bpm': 301},
    {'bpm': True}, {'bpm': 30.5}, {'tonalite': 'x' * 21}, {'tonalite': 1},
    {'mesure': '0/4'}, {'mesure': '4/0'}, {'mesure': '4/100'}, {'mesure': '10'},
    {'mesure': '4/4\n'}, {'mesure': '44'}, {'mesure': 4}, {'inconnu': 1},
    {'reference': 1}, {'source': True},
])
def test_validation(contexte, params):
    complet = {} if not params else dict(prompt='piano')
    complet.update(params)
    with pytest.raises(ParameterError):
        contexte.outil.valider(complet)
    assert contexte.moteur.process is None


def test_defauts_et_bornes(contexte):
    params = contexte.outil.valider({'prompt': '  piano  '})
    assert params['prompt'] == 'piano' and params['paroles'] == '' and params['instrumental'] is True
    assert params['duree'] == 60 and params['etapes'] == 8 and params['seed'] == 0
    assert params['langue'] == 'en' and params['lm'] is False and params['ajuster_paroles'] is True
    assert contexte.outil.valider(dict(prompt='x', paroles='[Verse]\nBonjour'))['instrumental'] is False
    for valeurs in [dict(duree=10, seed=0, etapes=1, force_cover=0, force_audio=0, bpm=30, mesure='1'),
                    dict(duree=600, seed=2**32-1, etapes=100, force_cover=1, force_audio=1,
                         bpm=300, mesure='9/99', langue='unknown')]:
        assert contexte.outil.valider(dict(prompt='x' * 1000, **valeurs))
    assert contexte.outil.valider(dict(prompt='x', paroles='x' * 8000, tache='a' * 40, tonalite='x' * 20))


@pytest.mark.parametrize('champ', ['reference', 'source'])
@pytest.mark.parametrize('nom', ['../source.wav', '..\\source.wav', '/source.wav', 'a/b.wav',
                                 'a..wav', 'a.wav:flux', 'été.wav', '', 'absent.wav', 'source.txt'])
def test_inbox_invalide(contexte, champ, nom):
    with pytest.raises(ParameterError):
        contexte.outil.valider(dict(prompt='x', **{champ: nom}))


@pytest.mark.parametrize('cas', ['lien_dur', 'lien_symbolique', 'trop_grand', 'dossier'])
def test_inbox_garde_fous(contexte, cas):
    source = contexte.chemins.inbox_dir / 'source.wav'
    fichier = source.with_name('autre.wav')
    if cas == 'lien_dur':
        os.link(source, fichier)
    elif cas == 'lien_symbolique':
        try:
            fichier.symlink_to(source)
        except OSError:
            pytest.skip('Liens symboliques non autorisés sur cet hôte.')
    elif cas == 'trop_grand':
        with fichier.open('wb') as stream:
            stream.truncate(200 * 1024**2 + 1)
    else:
        fichier.mkdir()
    for champ in ('reference', 'source'):
        with pytest.raises(ParameterError):
            contexte.outil.valider(dict(prompt='x', **{champ: fichier.name}))


async def test_correspondances_et_copies(contexte, moteur, tmp_path):
    fichiers = await contexte.outil.executer(dict(
        prompt=' lofi piano, warm ', paroles='[verse]\nBonjour', langue='fr', duree=30, seed=42,
        etapes=12, lm=True, ajuster_paroles=False, tache='cover', reference='source.wav',
        source='source.wav', force_cover=0.2, force_audio=0.8, bpm=90, tonalite='C minor', mesure='4/4'), tmp_path)
    assert [p.name for p in fichiers] == ['musique_1.wav', 'musique_1.json']
    requete = json.loads((tmp_path / 'requete.json').read_text(encoding='utf-8'))
    assert requete == dict(action='generation', caption='lofi piano, warm', paroles='[verse]\nBonjour',
                          instrumental=False, vocal_language='fr', duration=30, seed=42,
                          inference_steps=12, lm=True, ajuster_paroles=False, task_type='cover',
                          cover_noise_strength=0.2, audio_cover_strength=0.8, bpm=90,
                          keyscale='C minor', timesignature='4/4',
                          reference_audio=str((tmp_path / 'reference.wav').resolve()),
                          src_audio=str((tmp_path / 'source.wav').resolve()), sortie=str(tmp_path.resolve()))
    assert (tmp_path / 'source.wav').read_bytes() == (tmp_path / 'reference.wav').read_bytes() == b'RIFFsource'


@pytest.mark.parametrize('cas', ['absent', 'sans_json', 'wav_vide', 'wav_invalide', 'json_invalide',
                                 'json_liste', 'json_encoding', 'lien'])
async def test_resultats_invalides(contexte, tmp_path, cas):
    contexte.outil.adapter = SimpleNamespace(requete=AsyncMock(return_value=[]))
    if cas != 'absent':
        audio = tmp_path / 'musique_1.wav'
        audio.write_bytes(b'' if cas == 'wav_vide' else b'invalide' if cas == 'wav_invalide' else b'RIFFtest')
        if cas == 'lien':
            cible = tmp_path / 'autre.wav'
            audio.rename(cible)
            try:
                audio.symlink_to(cible)
            except OSError:
                pytest.skip('Liens symboliques non autorisés sur cet hôte.')
        if cas != 'sans_json':
            metadata = tmp_path / 'musique_1.json'
            metadata.write_bytes(b'\xff' if cas == 'json_encoding' else
                                 b'pas json' if cas == 'json_invalide' else
                                 b'[]' if cas == 'json_liste' else b'{}')
    with pytest.raises(EngineError):
        await contexte.outil.executer({'prompt': 'piano'}, tmp_path)


async def test_moteur_generique_et_environnement(contexte, moteur, tmp_path, monkeypatch):
    for nom in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
        monkeypatch.setenv(nom, 'proxy-factice')
    assert isinstance(moteur, MoteurTravailleurs)
    await moteur.start()
    assert moteur.process is None and await moteur.health()
    assert moteur.memory.vram_mb is None
    moteur.launcher = Mock(wraps=subprocess.Popen)
    await contexte.outil.executer({'prompt': 'piano'}, tmp_path)
    process = moteur.process
    await contexte.outil.executer({'prompt': 'piano'}, tmp_path)
    assert moteur.process is process
    env = moteur.launcher.call_args.kwargs['env']
    assert env['VERTIA_ACESTEP_DIR'] == str(contexte.chemins.acestep_dir)
    assert env['PYTHONIOENCODING'] == 'utf-8'
    assert all(nom not in env for nom in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'))
    with pytest.raises(EngineError, match='musique inconnu'):
        await moteur.requete('absent', {}, tmp_path)
    await moteur.free()
    assert process.poll() is not None and moteur.process is None


def test_registre_sante_passive(contexte, monkeypatch):
    module = contexte.module
    assert module.capacites == ['musique.generer'] and module.lien == '/musique'
    assert list(module.moteurs) == ['musique'] and module.activite == 'musique'
    declaration = sys.modules[module.sante.__module__]
    monkeypatch.setattr(declaration, 'resoudre_chemins', lambda: contexte.chemins)
    avant = set(contexte.chemins.inbox_dir.parent.rglob('*'))
    assert module.sante() == dict(pret=False, venvs_manquants=['acestep'],
                                 poids_manquants=module.poids, installation_presente=False)
    assert set(contexte.chemins.inbox_dir.parent.rglob('*')) == avant
    python = declaration.python_travailleur(contexte.chemins)
    python.parent.mkdir(parents=True)
    python.touch()
    (contexte.chemins.acestep_dir / 'acestep').mkdir()
    for nom in module.poids:
        (contexte.chemins.models_dir / nom).mkdir(parents=True)
    assert module.sante() == dict(pret=True, venvs_manquants=[], poids_manquants=[], installation_presente=True)


@pytest.fixture
def musique_api(settings, contexte):
    module = replace(contexte.module, moteurs={'musique': lambda s, c: contexte.moteur})
    contexte.registre._modules['musique'] = module
    contexte.registre._capacites['musique.generer'] = module
    engines = {nom: SimpleNamespace(start=AsyncMock(), free=AsyncMock()) for nom in ('ollama', 'ace', 'comfy')}
    state = dict(gpus=[], ram=dict(percent=1, total_mb=48000, used_mb=100), models=[], processes=[], warnings=[])
    app = create_app(settings, overrides=dict(
        modules=contexte.registre, chemins=contexte.chemins, engines=engines,
        monitor=SimpleNamespace(latest=state, sample=AsyncMock(return_value=state))))
    assert not contexte.registre.erreurs
    with TestClient(app) as client:
        yield client, app, contexte


def test_boucle_demandes_et_page(musique_api):
    client, app, contexte = musique_api
    assert {'voix', 'musique', 'ace'} <= app.state.services.arbiter.engines.keys()
    assert {c['capacite'] for c in client.get('/api/v1/capacites').json()} >= {'voix.generer', 'musique.generer'}
    assert client.get('/musique').status_code == 200
    assert 'musique.generer' in client.get('/modules/musique/static/musique.js').text
    response = client.post('/api/v1/demandes', json=dict(session='vertia', capacite='musique.generer',
                                                      params=dict(prompt='lofi piano, warm', duree=30)))
    assert response.status_code == 202, response.text
    demande_id = response.json()['id']
    demande = attendre(client, demande_id)
    assert demande['etat'] == 'livre', demande
    assert [Path(p).suffix for p in demande['chemins']] == ['.wav', '.json']
    assert app.state.services.jobs.list()[0]['engine'] == 'musique'
    assert 'voix' in app.state.services.arbiter.engines
    for index, mime in enumerate(['audio/wav', 'application/json']):
        fichier = client.get(f'/api/v1/demandes/{demande_id}/fichiers/{index}')
        assert fichier.status_code == 200 and fichier.headers['content-type'] == mime
        assert fichier.content == Path(demande['chemins'][index]).read_bytes()
    assert client.get('/voix').status_code == 200


def test_cli_musique_en_memoire(musique_api, monkeypatch, capsys):
    from test_vertia_gen import brancher_cli_en_memoire, cli

    client, _, _ = musique_api
    brancher_cli_en_memoire(monkeypatch, client)
    lanceur = Mock(side_effect=AssertionError('Lancement réel interdit'))
    assert cli.main(['musique', '--session', 'vertia', '--prompt', 'lofi piano, warm',
                     '--param', 'duree=30'], lanceur=lanceur) == 0
    fichiers = capsys.readouterr().out.splitlines()
    assert len(fichiers) == 2 and all(Path(p).is_file() for p in fichiers)
    assert Path(fichiers[0]).read_bytes().startswith(b'RIFF')
    assert isinstance(json.loads(Path(fichiers[1]).read_text(encoding='utf-8')), dict)
    lanceur.assert_not_called()


async def test_bascule_arbitre(contexte, moteur, tmp_path):
    from vertia.engines.voix import TRAVAILLEURS, VoixEngine
    from vertia.jobs.arbiter import GpuArbiter

    voix = VoixEngine(contexte.chemins, pythons={n: sys.executable for n in TRAVAILLEURS},
                      scripts={n: FIXTURES / 'voix_travailleur.py' for n in TRAVAILLEURS})
    arbitre = GpuArbiter({'voix': voix, 'musique': moteur}, SimpleNamespace(check=AsyncMock()))
    try:
        await arbitre.execute('voix', lambda: voix.requete('kokoro', {'action': 'synthese'}, tmp_path))
        ancien = voix.process
        await arbitre.execute('musique', lambda: contexte.outil.executer({'prompt': 'piano'}, tmp_path))
        assert ancien.poll() is not None and voix.process is None and arbitre.active == 'musique'
        ancien = moteur.process
        await arbitre.execute('voix', lambda: voix.requete('kokoro', {'action': 'synthese'}, tmp_path))
        assert ancien.poll() is not None and moteur.process is None and arbitre.active == 'voix'
    finally:
        await arbitre.free()


@pytest.mark.parametrize('extension,mime', [('mp3', 'audio/mpeg'), ('flac', 'audio/flac')])
def test_mime_audio(tmp_path, extension, mime):
    fichier = tmp_path / ('audio.' + extension)
    fichier.write_bytes(b'audio factice')
    app = FastAPI()
    app.include_router(v1.router)
    app.state.services = SimpleNamespace(demandes=SimpleNamespace(
        get=lambda identifiant: {'chemins': [str(fichier)]}, livraison=SimpleNamespace(outbox=tmp_path)))
    with TestClient(app) as client:
        response = client.get('/api/v1/demandes/abc123/fichiers/0')
        assert response.status_code == 200 and response.headers['content-type'] == mime


@pytest.fixture
def ace_factice(tmp_path, monkeypatch):
    ace = tmp_path / 'installation'
    ace.mkdir()
    monkeypatch.setenv('VERTIA_ACESTEP_DIR', str(ace))
    monkeypatch.setenv('VERTIA_FAUX_ACE_TRACE', str(tmp_path / 'trace.jsonl'))
    monkeypatch.setenv('VERTIA_FFMPEG', 'ffmpeg-factice')
    monkeypatch.setenv('PYTHONPATH', str(FIXTURES / 'musique_bibliotheques'))
    monkeypatch.setenv('PYTHONDONTWRITEBYTECODE', '1')
    monkeypatch.setenv('PYTHONIOENCODING', 'utf-8')
    return ace


def executer_ace(tmp_path, params):
    entrees = []
    for index, valeurs in enumerate(params):
        sortie = tmp_path / f'sortie_{index}'
        sortie.mkdir()
        requete = dict(action='generation', caption='piano', paroles='', instrumental=True,
                       vocal_language='en', duration=30, seed=42, inference_steps=8,
                       lm=False, ajuster_paroles=True, sortie=str(sortie))
        requete.update(valeurs)
        entrees.append(requete)
    resultat = subprocess.run(
        [sys.executable, '-u', '-B', str(ROOT / 'modules/musique/travailleurs/travailleur_acestep.py')],
        input=''.join(json.dumps(p) + '\n' for p in entrees), capture_output=True, text=True,
        encoding='utf-8', timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    reponses = [json.loads(ligne) for ligne in resultat.stdout.splitlines()]
    trace = tmp_path / 'trace.jsonl'
    appels = [json.loads(ligne) for ligne in trace.read_text(encoding='utf-8').splitlines()] if trace.exists() else []
    return resultat, reponses, appels


def test_travailleur_initialisation_et_lm_paresseux(ace_factice, tmp_path, monkeypatch):
    monkeypatch.setenv('HTTP_PROXY', 'proxy-factice')
    resultat, reponses, appels = executer_ace(tmp_path, [{}, {'lm': True}, {'lm': True}, {}])
    assert resultat.returncode == 0, resultat.stderr
    assert reponses == [{'pret': True}] + [{'ok': True, 'fichiers': ['musique_1.wav', 'musique_1.json']}] * 4
    assert appels[0] == dict(action='dit', kwargs=dict(
        project_root=str(ace_factice), config_path='acestep-v15-turbo', device='auto', offload_to_cpu=True),
        cwd=str(ace_factice), proxies={})
    assert appels[1] == {'action': 'llm_vide'}
    lm = [a for a in appels if a['action'] == 'lm']
    assert lm == [dict(action='lm', kwargs=dict(
        checkpoint_dir=str(ace_factice / 'checkpoints'), lm_model_path='acestep-5Hz-lm-0.6B',
        backend='pt', device='auto', offload_to_cpu=True, dtype=None))]
    generations = [a for a in appels if a['action'] == 'generation']
    assert [a['params']['thinking'] for a in generations] == [False, True, True, False]
    assert [a['action'] for a in appels].index('generation') < [a['action'] for a in appels].index('lm')
    assert len([a for a in appels if a['action'] == 'empty_cache']) == 4
    for index, appel in enumerate(generations):
        assert appel['config'] == dict(batch_size=1, audio_format='wav', use_random_seed=False)
        assert appel['save_dir'] == str(tmp_path / f'sortie_{index}' / 'ace')
        params = appel['params']
        assert params == dict(instruction='instruction par défaut', task_type='text2music', thinking=index in (1, 2),
                              caption='piano', lyrics='[Instrumental]', instrumental=True,
                              vocal_language='en', duration=30, inference_steps=8, guidance_scale=1.0, seed=42)
        audio = tmp_path / f'sortie_{index}/musique_1.wav'
        metadata = json.loads((audio.with_suffix('.json')).read_text(encoding='utf-8'))
        assert metadata['params'] == params
        assert metadata['model'] == 'ACE-Step 1.5 turbo' + (' + LM 0.6B' if index in (1, 2) else '')
        assert metadata['model_revision'] == 'revision-factice'
        assert metadata['runtime']['torch'] == 'torch-factice'
        assert metadata['runtime']['cuda_runtime'] == 'cuda-factice'
        assert metadata['output']['sha256'] == hashlib.sha256(audio.read_bytes()).hexdigest()
        assert metadata['output']['size_bytes'] == audio.stat().st_size
        assert metadata['output']['sample_rate'] == 24000 and metadata['output']['channels'] == 1
        assert metadata['output']['frames'] == 32 and metadata['output']['duration_seconds'] == 32/24000
        assert metadata['elapsed_s'] >= 0
        assert 'energy_wh_est' in metadata and 'gpu_util_avg_pct' in metadata


def test_travailleur_tache_audio_et_paroles(ace_factice, tmp_path):
    source = tmp_path / 'source.mp3'
    source.write_bytes(b'mp3 factice')
    paroles = '[Intro]\na\n[Verse]\nb\n[Chorus]\nc\n[Bridge]\nd\n[Outro]\ne'
    options = dict(instrumental=False, paroles=paroles, vocal_language='fr', duration=30,
                   task_type='cover', reference_audio=str(source), src_audio=str(source),
                   cover_noise_strength=0.2, audio_cover_strength=0.8, bpm=90, keyscale='C minor', timesignature='4/4')
    resultat, reponses, appels = executer_ace(tmp_path, [options, dict(options, ajuster_paroles=False)])
    assert resultat.returncode == 0 and all(r.get('ok') for r in reponses[1:]), resultat.stderr
    generations = [a['params'] for a in appels if a['action'] == 'generation']
    assert generations[0]['lyrics'] == '[Intro]\na\n\n[Verse]\nb\n\n[Outro]\ne\n'
    assert generations[1]['lyrics'] == paroles
    for index, params in enumerate(generations):
        assert params['task_type'] == 'cover' and params['instruction'] == 'instruction cover factice'
        for cle in ('cover_noise_strength', 'audio_cover_strength', 'bpm', 'keyscale', 'timesignature'):
            assert params[cle] == options[cle]
        assert params['src_audio'] == params['reference_audio']
        assert Path(params['src_audio']).is_relative_to(tmp_path / f'sortie_{index}')
        assert Path(params['src_audio']).read_bytes() == b'RIFFconverti'
    conversions = [a['args'] for a in appels if a['action'] == 'ffmpeg']
    assert len(conversions) == 2
    assert all(args[:-1] == ['ffmpeg-factice', '-y', '-loglevel', 'error', '-i', str(source),
                             '-vn', '-ac', '2', '-ar', '48000'] for args in conversions)


@pytest.mark.parametrize('caption', ['echec', 'absent'])
def test_travailleur_echec_generation(ace_factice, tmp_path, caption):
    resultat, reponses, appels = executer_ace(tmp_path, [{'caption': caption}])
    assert resultat.returncode == 0
    assert reponses == [{'pret': True}, {'ok': False, 'erreur': 'Échec du traitement.'}]
    assert not (tmp_path / 'sortie_0/musique_1.json').exists()
    assert any(a['action'] == 'empty_cache' for a in appels)


def test_travailleur_echec_initialisation(ace_factice, tmp_path, monkeypatch):
    monkeypatch.setenv('VERTIA_FAUX_ACE_INIT_ECHEC', '1')
    resultat, reponses, appels = executer_ace(tmp_path, [])
    assert resultat.returncode == 1 and not reponses
    assert 'DiT init failed' in resultat.stderr
    assert [a['action'] for a in appels] == ['dit']


def test_travailleur_echec_lm(ace_factice, tmp_path, monkeypatch):
    monkeypatch.setenv('VERTIA_FAUX_ACE_LM_ECHEC', '1')
    resultat, reponses, appels = executer_ace(tmp_path, [{'lm': True}, {}])
    assert resultat.returncode == 0 and reponses[1]['ok'] is False and reponses[2]['ok'] is True
    assert len([a for a in appels if a['action'] == 'generation']) == 1


def test_travailleur_traces_sans_sonde_ni_git(ace_factice, tmp_path, monkeypatch):
    monkeypatch.setenv('VERTIA_FAUX_ACE_SONDE_ECHEC', '1')
    monkeypatch.setenv('VERTIA_FAUX_ACE_REVISION_ECHEC', '1')
    resultat, reponses, _ = executer_ace(tmp_path, [{}])
    assert resultat.returncode == 0 and reponses[1]['ok'] is True
    metadata = json.loads((tmp_path / 'sortie_0/musique_1.json').read_text(encoding='utf-8'))
    assert metadata['model_revision'] == 'non disponible'
    assert metadata['output']['audio_probe_error'] == 'Sonde factice indisponible'
