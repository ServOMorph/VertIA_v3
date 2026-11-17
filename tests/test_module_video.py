from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from test_api_v1 import attendre
from vertia.app import create_app
from vertia.chemins import ROOT, resoudre_chemins
from vertia.engines.base import EngineError
from vertia.engines.travailleurs import MoteurTravailleurs
from vertia.modules.registry import RegistreModules
from vertia.tools.base import ParameterError

FIXTURES = Path(__file__).parent / 'fixtures'
MP4 = b'\x00\x00\x00\x18ftypmp42factice'


@pytest.fixture
def contexte(tmp_path):
    chemins = resoudre_chemins(tmp_path, environ={})
    chemins.inbox_dir.mkdir()
    Image.new('RGB', (32, 24)).save(chemins.inbox_dir / 'source.png')
    registre = RegistreModules(ROOT / 'modules')
    assert not registre.erreurs
    module = registre.capacites()['video.generer']
    moteur = module.moteurs['video'](None, chemins)
    moteur.pythons['wangp'] = sys.executable
    moteur.scripts['wangp'] = FIXTURES / 'video_travailleur.py'
    outil = module.outils['generer'](None, chemins, {'video': moteur})
    return SimpleNamespace(chemins=chemins, registre=registre, module=module, moteur=moteur, outil=outil)


@pytest.fixture
async def moteur(contexte):
    try:
        yield contexte.moteur
    finally:
        await contexte.moteur.close()


@pytest.mark.parametrize('params', [
    {}, {'prompt': ''}, {'prompt': ' '}, {'prompt': 'x' * 4001}, {'prompt': 1},
    {'mode': 'autre'}, {'mode': None}, {'mode': 'i2v'}, {'mode': 't2v', 'image': 'source.png'},
    {'image': True}, {'negatif': 'x' * 2001}, {'negatif': 1}, {'negatif': None},
    {'seed': -1}, {'seed': 2**31}, {'seed': True}, {'seed': 0.5}, {'seed': '0'},
    {'images': 16}, {'images': 82}, {'images': 18}, {'images': 80}, {'images': True},
    {'images': '81'}, {'images': 81.0}, {'resolution': '480x480'}, {'resolution': None},
    {'etapes': 0}, {'etapes': 51}, {'etapes': '20'}, {'etapes': True}, {'etapes': 1.5},
    {'inconnu': 1},
])
def test_validation(contexte, params):
    complet = dict(prompt='un paysage') if params else {}
    complet.update(params)
    with pytest.raises(ParameterError):
        contexte.outil.valider(complet)
    assert contexte.moteur.process is None


def test_defauts_et_bornes(contexte):
    assert contexte.outil.valider({'prompt': '  paysage  '}) == dict(
        prompt='paysage', mode='t2v', image=None, negatif='', seed=0, images=81,
        resolution='832x480', etapes=None)
    for images in range(17, 82, 4):
        assert contexte.outil.valider(dict(prompt='x' * 4000, negatif='x' * 2000,
                                          images=images, seed=2**31 - 1, etapes=50,
                                          resolution='480x832'))['images'] == images
    assert contexte.outil.valider(dict(prompt='x', etapes=1))['etapes'] == 1


@pytest.mark.parametrize('nom', ['../source.png', '..\\source.png', '/source.png', 'a/b.png',
                                 'a..png', 'a.png:flux', 'été.png', '', 'absent.png', 'source.txt'])
def test_inbox_invalide(contexte, nom):
    with pytest.raises(ParameterError):
        contexte.outil.valider(dict(prompt='x', mode='i2v', image=nom))


@pytest.mark.parametrize('cas', ['lien_dur', 'lien_symbolique', 'trop_grand', 'dossier',
                                 'contenu_invalide', 'format_refuse', 'dimensions'])
def test_inbox_garde_fous(contexte, cas):
    source = contexte.chemins.inbox_dir / 'source.png'
    fichier = source.with_name('autre.png')
    if cas == 'lien_dur':
        os.link(source, fichier)
    elif cas == 'lien_symbolique':
        try:
            fichier.symlink_to(source)
        except OSError:
            pytest.skip('Liens symboliques non autorisés sur cet hôte.')
    elif cas == 'trop_grand':
        with fichier.open('wb') as stream:
            stream.truncate(50 * 1024**2 + 1)
    elif cas == 'dossier':
        fichier.mkdir()
    elif cas == 'contenu_invalide':
        fichier.write_bytes(b'pas une image')
    elif cas == 'format_refuse':
        Image.new('RGB', (32, 24)).save(fichier, format='BMP')
    else:
        Image.new('RGB', (8001, 1)).save(fichier)
    with pytest.raises(ParameterError):
        contexte.outil.valider(dict(prompt='x', mode='i2v', image=fichier.name))


@pytest.mark.parametrize('extension,format_image', [('png', 'PNG'), ('jpg', 'JPEG'),
                                                  ('jpeg', 'JPEG'), ('webp', 'WEBP')])
async def test_correspondances_et_copie(contexte, moteur, tmp_path, extension, format_image):
    source = contexte.chemins.inbox_dir / ('entree.' + extension)
    Image.new('RGB', (32, 24)).save(source, format=format_image)
    fichiers = await contexte.outil.executer(dict(
        prompt=' paysage ', mode='i2v', image=source.name, negatif='flou', seed=42,
        images=17, resolution='480x832', etapes=12), tmp_path)
    assert [p.name for p in fichiers] == ['video_1.mp4', 'video_1.json']
    copie = tmp_path / ('image.' + extension)
    assert copie.read_bytes() == source.read_bytes()
    requete = json.loads((tmp_path / 'requete.json').read_text(encoding='utf-8'))
    assert requete == dict(action='generation', prompt='paysage', mode='i2v', negative_prompt='flou',
                          seed=42, video_length=17, resolution='480x832', num_inference_steps=12,
                          image_start=str(copie.resolve()), sortie=str(tmp_path.resolve()))


async def test_moteur_generique_et_defauts(contexte, moteur, tmp_path):
    assert isinstance(moteur, MoteurTravailleurs)
    assert (moteur.delai_pret, moteur.delai_requete) == (1200, 7200)
    assert moteur.memory.vram_mb is None
    assert moteur.environnement == dict(VERTIA_WANGP_DIR=str(contexte.chemins.engines_dir / 'wangp'),
                                        PYTHONIOENCODING='utf-8')
    await moteur.start()
    assert moteur.process is None
    await contexte.outil.executer({'prompt': 'x'}, tmp_path)
    process = moteur.process
    await contexte.outil.executer({'prompt': 'x'}, tmp_path)
    assert process is moteur.process
    requete = json.loads((tmp_path / 'requete.json').read_text(encoding='utf-8'))
    assert requete == dict(action='generation', prompt='x', mode='t2v', negative_prompt='',
                          seed=0, video_length=81, resolution='832x480', sortie=str(tmp_path.resolve()))
    await moteur.free()
    assert moteur.process is None and process.poll() is not None


@pytest.mark.parametrize('cas', ['absent', 'sans_json', 'mp4_vide', 'mp4_invalide', 'ftyp_trop_loin',
                                 'json_invalide', 'json_liste', 'json_encoding', 'lien'])
async def test_resultats_invalides(contexte, tmp_path, cas):
    contexte.outil.adapter = SimpleNamespace(requete=AsyncMock(return_value=[]))
    if cas != 'absent':
        video = tmp_path / 'video_1.mp4'
        contenu = {'mp4_vide': b'', 'mp4_invalide': b'invalide', 'ftyp_trop_loin': b'x' * 12 + b'ftyp'}
        video.write_bytes(contenu.get(cas, MP4))
        if cas == 'lien':
            cible = tmp_path / 'autre.mp4'
            video.rename(cible)
            try:
                video.symlink_to(cible)
            except OSError:
                pytest.skip('Liens symboliques non autorisés sur cet hôte.')
        if cas != 'sans_json':
            (tmp_path / 'video_1.json').write_bytes(
                b'\xff' if cas == 'json_encoding' else b'pas json' if cas == 'json_invalide' else
                b'[]' if cas == 'json_liste' else b'{}')
    with pytest.raises(EngineError):
        await contexte.outil.executer({'prompt': 'x'}, tmp_path)


def test_registre_sante_passive(contexte, monkeypatch):
    module = contexte.module
    assert module.capacites == ['video.generer'] and module.lien == '/video'
    assert list(module.moteurs) == ['video'] and module.activite == 'video'
    declaration = sys.modules[module.sante.__module__]
    monkeypatch.setattr(declaration, 'resoudre_chemins', lambda: contexte.chemins)
    avant = set(contexte.chemins.inbox_dir.parent.rglob('*'))
    assert module.sante() == dict(pret=False, venvs_manquants=['wangp'],
                                 poids_manquants=['wangp/ckpts'], installation_presente=False)
    assert set(contexte.chemins.inbox_dir.parent.rglob('*')) == avant
    python = declaration.python_travailleur(contexte.chemins)
    assert python == contexte.chemins.engines_dir / 'wangp/env' / (
        'Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    python.parent.mkdir(parents=True)
    python.touch()
    api = contexte.chemins.engines_dir / 'wangp/shared/api.py'
    api.parent.mkdir()
    api.touch()
    (contexte.chemins.models_dir / 'wangp/ckpts').mkdir(parents=True)
    assert module.sante() == dict(pret=True, venvs_manquants=[], poids_manquants=[], installation_presente=True)


@pytest.fixture
def video_api(settings, contexte):
    module = replace(contexte.module, moteurs={'video': lambda s, c: contexte.moteur})
    contexte.registre._modules['video'] = module
    contexte.registre._capacites['video.generer'] = module
    engines = {nom: SimpleNamespace(start=AsyncMock(), free=AsyncMock()) for nom in ('ollama', 'ace', 'comfy')}
    state = dict(gpus=[], ram=dict(percent=1, total_mb=48000, used_mb=100), models=[], processes=[], warnings=[])
    app = create_app(settings, overrides=dict(
        modules=contexte.registre, chemins=contexte.chemins, engines=engines,
        monitor=SimpleNamespace(latest=state, sample=AsyncMock(return_value=state))))
    assert not contexte.registre.erreurs
    with TestClient(app) as client:
        yield client, app, contexte


def test_boucle_demandes_et_page(video_api):
    client, app, _ = video_api
    assert {'musique', 'video', 'comfy'} <= app.state.services.arbiter.engines.keys()
    capacites = {c['capacite']: c['module'] for c in client.get('/api/v1/capacites').json()}
    assert capacites['video.generer'] == 'video' and capacites['musique.generer'] == 'musique'
    page = client.get('/video')
    assert page.status_code == 200 and '<video' in page.text
    assert 'environ 1 h par clip de 81 images' in page.text
    assert 'video.generer' in client.get('/modules/video/static/video.js').text
    assert client.get('/musique').status_code == 200
    response = client.post('/api/v1/demandes', json=dict(session='vertia', capacite='video.generer',
                                                      params=dict(prompt='paysage')))
    assert response.status_code == 202, response.text
    demande_id = response.json()['id']
    demande = attendre(client, demande_id)
    assert demande['etat'] == 'livre', demande
    assert [Path(p).suffix for p in demande['chemins']] == ['.mp4', '.json']
    assert app.state.services.jobs.list()[0]['engine'] == 'video'
    for index, mime in enumerate(['video/mp4', 'application/json']):
        fichier = client.get(f'/api/v1/demandes/{demande_id}/fichiers/{index}')
        assert fichier.status_code == 200 and fichier.headers['content-type'] == mime
        assert fichier.content == Path(demande['chemins'][index]).read_bytes()


def test_cli_alias_video(video_api, monkeypatch, capsys):
    from test_vertia_gen import brancher_cli_en_memoire, cli

    client, app, _ = video_api
    brancher_cli_en_memoire(monkeypatch, client)
    lanceur = Mock(side_effect=AssertionError('Lancement réel interdit'))
    assert cli.main(['video', '--session', 'vertia', '--prompt', 'paysage',
                     '--param', 'mode="t2v"'], lanceur=lanceur) == 0
    chemins = capsys.readouterr().out.splitlines()
    assert len(chemins) == 2 and all(Path(p).is_file() for p in chemins)
    assert b'ftyp' in Path(chemins[0]).read_bytes()[:12]
    assert isinstance(json.loads(Path(chemins[1]).read_text(encoding='utf-8')), dict)
    assert app.state.services.jobs.list()[0]['engine'] == 'video'
    lanceur.assert_not_called()


def test_demande_i2v_depuis_inbox(video_api):
    client, app, contexte = video_api
    response = client.post('/api/v1/demandes', json=dict(
        session='vertia', capacite='video.generer',
        params=dict(prompt='animer le paysage', mode='i2v', image='source.png')))
    assert response.status_code == 202, response.text
    demande = attendre(client, response.json()['id'])
    assert demande['etat'] == 'livre', demande
    metadata = json.loads(Path(demande['chemins'][1]).read_text(encoding='utf-8'))
    copie = Path(metadata['params']['image_start'])
    assert copie.name == 'image.png'
    assert copie.read_bytes() == (contexte.chemins.inbox_dir / 'source.png').read_bytes()
    assert app.state.services.jobs.list()[0]['engine'] == 'video'


async def test_bascule_arbitre_musique_video(contexte, moteur, tmp_path):
    from vertia.jobs.arbiter import GpuArbiter

    module = contexte.registre.capacites()['musique.generer']
    musique = module.moteurs['musique'](None, contexte.chemins)
    musique.pythons['acestep'] = sys.executable
    musique.scripts['acestep'] = FIXTURES / 'musique_travailleur.py'
    arbitre = GpuArbiter({'musique': musique, 'video': moteur}, SimpleNamespace(check=AsyncMock()))
    try:
        await arbitre.execute('musique', lambda: musique.requete('acestep', {'action': 'generation'}, tmp_path))
        ancien = musique.process
        await arbitre.execute('video', lambda: contexte.outil.executer({'prompt': 'x'}, tmp_path))
        assert ancien.poll() is not None and musique.process is None and arbitre.active == 'video'
        ancien = moteur.process
        await arbitre.execute('musique', lambda: musique.requete('acestep', {'action': 'generation'}, tmp_path))
        assert ancien.poll() is not None and moteur.process is None and arbitre.active == 'musique'
    finally:
        await arbitre.free()


@pytest.fixture
def wangp_factice(tmp_path, monkeypatch):
    installation = tmp_path / 'installation'
    installation.mkdir()
    monkeypatch.setenv('VERTIA_WANGP_DIR', str(installation))
    monkeypatch.setenv('VERTIA_FAUX_WANGP_TRACE', str(tmp_path / 'trace.jsonl'))
    monkeypatch.setenv('PYTHONPATH', str(FIXTURES / 'video_bibliotheques'))
    monkeypatch.setenv('PYTHONDONTWRITEBYTECODE', '1')
    monkeypatch.setenv('PYTHONIOENCODING', 'utf-8')
    return installation


def executer_wangp(tmp_path, params):
    entrees = []
    for index, valeurs in enumerate(params):
        sortie = tmp_path / f'sortie_{index}'
        sortie.mkdir()
        requete = dict(action='generation', mode='t2v', prompt='paysage', seed=42,
                       resolution='832x480', video_length=81, negative_prompt='', sortie=str(sortie))
        requete.update(valeurs)
        entrees.append(requete)
    resultat = subprocess.run(
        [sys.executable, '-u', '-B', str(ROOT / 'modules/video/travailleurs/travailleur_wangp.py')],
        input=''.join(json.dumps(p) + '\n' for p in entrees), capture_output=True, text=True,
        encoding='utf-8', timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    reponses = [json.loads(ligne) for ligne in resultat.stdout.splitlines()]
    trace = tmp_path / 'trace.jsonl'
    appels = [json.loads(ligne) for ligne in trace.read_text(encoding='utf-8').splitlines()] if trace.exists() else []
    return resultat, reponses, appels


def test_travailleur_reglages_et_metadonnees(wangp_factice, tmp_path):
    image = tmp_path / 'image.png'
    image.write_bytes(b'image factice')
    options = [{}, dict(mode='i2v', image_start=str(image), negative_prompt='flou',
                        num_inference_steps=12, resolution='480x832', video_length=17, seed=7)]
    resultat, reponses, appels = executer_wangp(tmp_path, options)
    assert resultat.returncode == 0, resultat.stderr
    assert reponses == [{'pret': True}] + [{'ok': True, 'fichiers': ['video_1.mp4', 'video_1.json']}] * 2
    assert appels[0] == dict(action='init', console_output=False, cwd=str(wangp_factice))
    assert len([a for a in appels if a['action'] == 'init']) == 1
    assert [a['mode'] for a in appels if a['action'] == 'defauts'] == ['t2v', 'i2v']
    generations = [a['settings'] for a in appels if a['action'] == 'generation']
    for index, s in enumerate(generations):
        attendu = dict(model_type='t2v' if index == 0 else 'i2v', num_inference_steps=30 if index == 0 else 12,
                       negative_prompt='négatif par défaut' if index == 0 else 'flou',
                       valeur_speciale='chemin-factice', imbrique={'chemin': 'autre'},
                       prompt='paysage', seed=42 if index == 0 else 7,
                       resolution='832x480' if index == 0 else '480x832', video_length=81 if index == 0 else 17)
        if index:
            attendu.update(image_prompt_type='S', image_start=[str(image.resolve())])
        assert s == attendu
        video = tmp_path / f'sortie_{index}/video_1.mp4'
        assert video.read_bytes() == MP4
        metadata = json.loads(video.with_suffix('.json').read_text(encoding='utf-8'))
        assert metadata['params'] == s
        assert metadata['model'] == ('Wan2.1 Text2video 14B' if index == 0 else 'Wan2.1 Image2video 480p 14B')
        assert metadata['model_revision'] == 'revision-factice'
        assert metadata['runtime']['torch'] == 'torch-factice'
        assert metadata['runtime']['cuda_runtime'] == 'cuda-factice'
        assert metadata['runtime']['os'] == 'os-factice' and metadata['runtime']['python']
        assert metadata['output'] == dict(path='video_1.mp4', format='mp4', size_bytes=len(MP4),
                                         sha256=hashlib.sha256(MP4).hexdigest())
        assert metadata['elapsed_s'] >= 0
        assert metadata['energy_wh_est'] >= 0 and metadata['gpu_util_avg_pct'] == 50
        assert metadata['vram_max_mib'] == 2345
    assert not (wangp_factice / 'outputs/origine.mp4').exists()
    assert len([a for a in appels if a['action'] == 'empty_cache']) == 2


@pytest.mark.parametrize('options', [dict(prompt='absent'), dict(prompt='echec'), dict(prompt='introuvable'),
                                     dict(mode='i2v'), dict(mode='inconnu'), dict(action='inconnue')])
def test_travailleur_echecs_et_reprise(wangp_factice, tmp_path, options):
    resultat, reponses, appels = executer_wangp(tmp_path, [options, {}])
    assert resultat.returncode == 0
    assert reponses[1] == dict(ok=False, erreur='Échec du traitement.')
    assert reponses[2]['ok'] is True
    assert not (tmp_path / 'sortie_0/video_1.json').exists()
    if options.get('prompt') == 'absent':
        assert 'Erreur une; Erreur deux' in resultat.stderr
    nettoyages = [a for a in appels if a['action'] == 'empty_cache']
    assert len(nettoyages) == (1 if options.get('mode') == 'inconnu' or 'action' in options else 2)


def test_travailleur_sans_sondes_ni_git(wangp_factice, tmp_path, monkeypatch):
    monkeypatch.setenv('VERTIA_FAUX_WANGP_SONDE_ECHEC', '1')
    monkeypatch.setenv('VERTIA_FAUX_WANGP_REVISION_ECHEC', '1')
    resultat, reponses, _ = executer_wangp(tmp_path, [{}])
    assert resultat.returncode == 0 and reponses[1]['ok'] is True
    metadata = json.loads((tmp_path / 'sortie_0/video_1.json').read_text(encoding='utf-8'))
    assert metadata['model_revision'] == 'non disponible'
    assert metadata['energy_wh_est'] is None and metadata['gpu_util_avg_pct'] is None
    assert metadata['vram_max_mib'] is None


def test_travailleur_echec_initialisation(wangp_factice, tmp_path, monkeypatch):
    monkeypatch.setenv('VERTIA_FAUX_WANGP_INIT_ECHEC', '1')
    resultat, reponses, appels = executer_wangp(tmp_path, [])
    assert resultat.returncode == 1 and not reponses
    assert 'Initialisation factice échouée' in resultat.stderr
    assert [a['action'] for a in appels] == ['init']
