from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from PIL import Image, ImageChops
import pytest

from test_api_v1 import attendre
from test_module_image import FauxMoteurImage, ROOT
from vertia.app import create_app
from vertia.chemins import resoudre_chemins
from vertia.demandes.service import construire
from vertia.engines.comfy_qwen import build_graph, build_graph_retouche
from vertia.modules.registry import RegistreModules
from vertia.tools.base import ParameterError


def octets_image(image, format='PNG', **options):
    buffer = BytesIO()
    image.save(buffer, format=format, **options)
    return buffer.getvalue()


class FauxMoteurRetouche(FauxMoteurImage):
    def __init__(self):
        super().__init__()
        self.uploads = []
        self.contenu = octets_image(Image.new('RGB', (256, 256), (240, 120, 60)))
        self.mime = 'image/png'

    async def upload_image(self, data, mime):
        assert mime == 'image/png'
        with Image.open(BytesIO(data)) as image:
            assert image.format == 'PNG'
            self.uploads.append(image.copy())
        return f'entree_{len(self.uploads)}.png'

    async def generate_graph(self, graph, progress):
        self.appels.append(graph)
        progress(100)
        return {'images': [{'filename': 'factice.png', 'type': 'output'}]}

    async def preview(self, image, formats=None):
        self.previews.append(image)
        assert formats == {'.png': 'image/png'}
        return self.contenu, self.mime


@pytest.fixture
def retouche(tmp_path):
    chemins = resoudre_chemins(tmp_path, environ={})
    chemins.inbox_dir.mkdir()
    source = Image.new('RGB', (640, 384), (10, 30, 50))
    source.paste((60, 80, 100), (0, 0, 320, 384))
    source.save(chemins.inbox_dir / 'source.png')
    masque = Image.new('L', source.size)
    masque.paste(255, (240, 128, 400, 256))
    masque.save(chemins.inbox_dir / 'masque.png')
    moteur = FauxMoteurRetouche()
    registre = RegistreModules(ROOT / 'modules')
    assert not registre.erreurs
    module = registre.capacites()['image.retoucher']
    outil = construire(module.outils['retoucher'], None, chemins, {'comfy': moteur})
    return SimpleNamespace(chemins=chemins, source=source, moteur=moteur, registre=registre, outil=outil)


@pytest.fixture
def retouche_api(settings, retouche):
    engines = {name: SimpleNamespace(start=AsyncMock(), free=AsyncMock()) for name in ('ollama', 'ace')}
    engines['comfy'] = retouche.moteur
    state = dict(gpus=[], ram=dict(percent=1, total_mb=48000, used_mb=100),
                 models=[], processes=[], warnings=[])
    app = create_app(settings, overrides=dict(
        modules=retouche.registre, chemins=retouche.chemins, engines=engines,
        monitor=SimpleNamespace(latest=state, sample=AsyncMock(return_value=state))))
    assert not retouche.registre.erreurs
    assert app.state.services.demandes.outils['image.retoucher'][0].adapter is retouche.moteur
    with TestClient(app) as client:
        yield client, retouche, app


@pytest.mark.parametrize('masque', [None, 'masque.png'])
def test_graphe_retouche(masque):
    params = dict(source='source.png', masque=masque, prompt='retoucher', negatif='flou',
                  force=0.7, etapes=18, seed=42)
    graphe = build_graph_retouche(params)
    assert set(graphe) == set(['1', '2', '3', '4', '5', '6', '9', '11', '12']
                             + (['7', '8'] if masque else []))
    origine = build_graph(dict(params, largeur=512, hauteur=512))
    for noeud in ('1', '2', '3', '4', '11', '12'):
        assert graphe[noeud] == origine[noeud]
    assert graphe['4']['inputs'] == dict(clip=['2', 0], prompt='retoucher', negative_prompt='flou',
                                        vae=['3', 0], resolution=1024)
    assert graphe['5'] == dict(class_type='LoadImage', inputs={'image': 'source.png'})
    assert graphe['6'] == dict(class_type='VAEEncode', inputs={'pixels': ['5', 0], 'vae': ['3', 0]})
    assert graphe['9'] == dict(class_type='KSampler', inputs=dict(
        model=['1', 0], seed=42, steps=18, cfg=1, sampler_name='euler', scheduler='simple',
        positive=['4', 0], negative=['4', 1], latent_image=['8' if masque else '6', 0], denoise=0.7))
    if masque:
        assert graphe['7'] == dict(class_type='LoadImageMask', inputs=dict(image=masque, channel='red'))
        assert graphe['8'] == dict(class_type='SetLatentNoiseMask', inputs=dict(samples=['6', 0], mask=['7', 0]))
    assert params['source'] == 'source.png' and params['masque'] == masque


@pytest.mark.parametrize('avec_masque', [True, False])
def test_api_retouche_livraison_pixels_et_essais(retouche_api, avec_masque):
    client, contexte, app = retouche_api
    source = contexte.chemins.inbox_dir / 'source.png'
    avant = {f.name: f.read_bytes() for f in contexte.chemins.inbox_dir.iterdir()}
    params = dict(source=source.name, prompt='  corriger le centre  ', force=0.65, etapes=13, seed=24)
    if avec_masque:
        params['masque'] = 'masque.png'
    capacite = next(c for c in client.get('/api/v1/capacites').json() if c['capacite'] == 'image.retoucher')
    assert set(capacite['parametres']) == {'source', 'masque', 'prompt', 'negatif', 'force', 'etapes', 'seed'}
    response = client.post('/api/v1/demandes', json=dict(
        session='vertia', capacite='image.retoucher', params=params))
    assert response.status_code == 202
    demande_id = response.json()['id']
    demande = attendre(client, demande_id)
    assert demande['etat'] == 'livre', demande
    assert len(demande['chemins']) == 1
    with Image.open(demande['chemins'][0]) as resultat:
        assert resultat.format == 'PNG' and resultat.mode == 'RGB'
        assert resultat.size == contexte.source.size
        assert resultat.getpixel((320, 192)) == (240, 120, 60)
        if avec_masque:
            for boite in [(0, 0, 200, 384), (440, 0, 640, 384), (0, 0, 640, 90), (0, 294, 640, 384)]:
                assert ImageChops.difference(resultat.crop(boite), contexte.source.crop(boite)).getbbox() is None
            bord = resultat.getpixel((240, 192))
            assert 60 < bord[0] < 240
        else:
            assert resultat.getextrema() == ((240, 240), (120, 120), (60, 60))
    moteur = contexte.moteur
    assert len(moteur.appels) == len(moteur.previews) == moteur.demarrages == 1
    assert len(moteur.uploads) == (2 if avec_masque else 1)
    assert moteur.uploads[0].size == (640, 384) and moteur.uploads[0].mode == 'RGB'
    if avec_masque:
        assert moteur.uploads[1].mode == 'L'
        assert moteur.appels[0]['7']['inputs']['image'] == 'entree_2.png'
    assert moteur.appels[0]['5']['inputs']['image'] == 'entree_1.png'
    assert moteur.appels[0]['4']['inputs']['prompt'] == 'corriger le centre'
    assert moteur.appels[0]['9']['inputs']['denoise'] == 0.65
    assert app.state.services.jobs.list()[0]['engine'] == 'comfy'
    assert {f.name: f.read_bytes() for f in contexte.chemins.inbox_dir.iterdir()} == avant
    assert client.post(f'/api/v1/demandes/{demande_id}/retour', json={'verdict': 'a_refaire'}).status_code == 200
    assert attendre(client, demande_id)['etat'] == 'livre'
    assert len(moteur.appels) == len(moteur.previews) == 2


@pytest.mark.parametrize('modification', [
    {'source': None}, {'source': ''}, {'source': '../source.png'}, {'source': '..\\source.png'},
    {'source': '/source.png'}, {'source': 'C:\\source.png'}, {'source': 'a/b.png'},
    {'source': 'a..png'}, {'source': 'x' * 101}, {'source': 'été.png'}, {'source': 'source.png:flux'},
    {'source': 'absent.png'}, {'source': '.'}, {'source': 'dossier.png'},
    {'masque': '../masque.png'}, {'masque': ''}, {'masque': 1}, {'masque': 'absent.png'},
    {'prompt': ''}, {'prompt': ' '}, {'prompt': 'x' * 4001}, {'prompt': 1},
    {'negatif': None}, {'force': 0.29}, {'force': 1.01}, {'force': True}, {'force': '0.8'},
    {'etapes': 0}, {'etapes': 31}, {'etapes': True}, {'etapes': 2.5},
    {'seed': True}, {'seed': '1'}, {'seed': 0.5}, {'inconnu': 1},
])
def test_api_refuse_parametres_avant_moteur(retouche_api, modification):
    client, contexte, app = retouche_api
    (contexte.chemins.inbox_dir / 'dossier.png').mkdir()
    params = dict(source='source.png', prompt='retoucher')
    params.update(modification)
    response = client.post('/api/v1/demandes', json=dict(
        session='vertia', capacite='image.retoucher', params=params))
    assert response.status_code == 422, response.text
    assert not contexte.moteur.appels and not contexte.moteur.uploads and not contexte.moteur.demarrages
    assert not app.state.services.jobs.list()


@pytest.mark.parametrize('champ', ['source', 'prompt'])
def test_obligatoires(retouche, champ):
    params = dict(source='source.png', prompt='retoucher')
    del params[champ]
    with pytest.raises(ParameterError):
        retouche.outil.valider(params)


@pytest.mark.parametrize('nom,format', [('png.bin', 'PNG'), ('jpeg.png', 'JPEG'), ('webp.jpg', 'WEBP')])
def test_formats_par_contenu_et_defauts(retouche, nom, format):
    image = retouche.chemins.inbox_dir / nom
    image.write_bytes(octets_image(retouche.source, format))
    assert retouche.outil.valider(dict(source=nom, prompt='  retoucher  ')) == dict(
        source=nom, masque=None, prompt='retoucher', negatif='', force=0.85, etapes=25, seed=0)


@pytest.mark.parametrize('champ', ['source', 'masque'])
@pytest.mark.parametrize('cas', ['texte', 'gif', 'tronque', 'crc', 'dimensions', 'volume'])
def test_fichiers_invalides(retouche, champ, cas):
    cible = retouche.chemins.inbox_dir / 'invalide.png'
    if cas == 'texte':
        cible.write_text('pas une image')
    elif cas == 'gif':
        cible.write_bytes(octets_image(retouche.source, 'GIF'))
    elif cas == 'tronque':
        cible.write_bytes(octets_image(retouche.source)[:45])
    elif cas == 'crc':
        contenu = bytearray(octets_image(retouche.source))
        contenu[50] ^= 1
        cible.write_bytes(contenu)
    elif cas == 'volume':
        with cible.open('wb') as fichier:
            fichier.truncate(64 * 1024**2 + 1)
    else:
        Image.new('L', (8001, 1), 255).save(cible)
    params = dict(source='source.png', prompt='retoucher', **({'masque': 'masque.png'} if champ == 'masque' else {}))
    params[champ] = cible.name
    with pytest.raises(ParameterError):
        retouche.outil.valider(params)
    assert not retouche.moteur.appels and not retouche.moteur.uploads


@pytest.mark.parametrize('taille,couleur,accepte', [
    ((326, 192), 255, True), ((327, 192), 255, False),
    ((320, 196), 255, False), ((400, 400), 255, False),
    ((640, 384), 0, False), ((640, 384), 127, False),
])
def test_proportions_et_masque_vide(retouche, taille, couleur, accepte):
    Image.new('L', taille, couleur).save(retouche.chemins.inbox_dir / 'masque.png')
    params = dict(source='source.png', masque='masque.png', prompt='retoucher')
    if accepte:
        assert retouche.outil.valider(params)['masque'] == 'masque.png'
    else:
        with pytest.raises(ParameterError):
            retouche.outil.valider(params)


@pytest.mark.parametrize('lien', ['symbolique', 'physique'])
def test_refuse_lien_hors_inbox(retouche, tmp_path, lien):
    externe = tmp_path / 'hors_inbox.png'
    retouche.source.save(externe)
    cible = retouche.chemins.inbox_dir / 'lien.png'
    try:
        if lien == 'symbolique':
            cible.symlink_to(externe)
        else:
            cible.hardlink_to(externe)
    except OSError:
        if lien == 'physique':
            raise
        # Windows peut interdire la création de liens symboliques sans privilège.
        outil_module = __import__(retouche.outil.__module__, fromlist=['stat'])
        from unittest.mock import patch
        retouche.source.save(cible)
        infos = cible.stat()
        attributs = {nom: getattr(infos, nom) for nom in ('st_mode', 'st_nlink', 'st_size')}
        attributs['st_file_attributes'] = outil_module.stat.FILE_ATTRIBUTE_REPARSE_POINT
        with patch.object(outil_module.Path, 'lstat', return_value=SimpleNamespace(**attributs)):
            with pytest.raises(ParameterError):
                retouche.outil.valider(dict(source=cible.name, prompt='retoucher'))
        return
    for champ in ('source', 'masque'):
        params = dict(source='source.png', prompt='retoucher')
        params[champ] = cible.name
        with pytest.raises(ParameterError):
            retouche.outil.valider(params)
    assert externe.read_bytes() == octets_image(retouche.source)


@pytest.mark.asyncio
@pytest.mark.parametrize('taille', [(2000, 1500), (1536, 1024), (8000, 128), (128, 8000), (64, 32), (777, 333)])
async def test_taille_travail_bornee_et_resultat_original(retouche, tmp_path, taille):
    Image.new('RGB', taille, 'blue').save(retouche.chemins.inbox_dir / 'source.png')
    fichiers = await retouche.outil.executer(dict(source='source.png', prompt='retoucher'), tmp_path)
    largeur, hauteur = retouche.moteur.uploads[0].size
    assert largeur >= 256 and hauteur >= 256
    assert largeur % 32 == hauteur % 32 == 0
    assert largeur * hauteur <= 1_500_000
    if 256**2 * max(taille) / min(taille) <= 1_500_000:
        assert largeur / hauteur == pytest.approx(taille[0] / taille[1], rel=0.04)
    assert fichiers == [tmp_path / 'retouche_1.png']
    with Image.open(fichiers[0]) as image:
        assert image.size == taille
    assert len(retouche.moteur.appels) == 1


@pytest.mark.asyncio
async def test_masque_luminance_alpha_ignore_redimensionne(retouche, tmp_path):
    masque = Image.new('RGBA', (320, 192), (127, 127, 127, 255))
    masque.paste((128, 128, 128, 0), (120, 64, 200, 128))
    masque.save(retouche.chemins.inbox_dir / 'masque.png')
    await retouche.outil.executer(dict(source='source.png', masque='masque.png', prompt='retoucher'), tmp_path)
    envoye = retouche.moteur.uploads[1]
    assert envoye.size == retouche.source.size and envoye.mode == 'L'
    assert envoye.getpixel((0, 0)) == 0
    assert envoye.getpixel((320, 192)) == 255
    with Image.open(tmp_path / 'retouche_1.png') as image:
        assert image.getpixel((320, 192)) == (240, 120, 60)
        assert image.getpixel((0, 0)) == retouche.source.getpixel((0, 0))


@pytest.mark.asyncio
async def test_orientation_exif_et_rvb(retouche, tmp_path):
    image = Image.new('RGB', (384, 640), 'blue')
    image.paste('red', (0, 0, 384, 320))
    exif = Image.Exif()
    exif[274] = 6
    image.save(retouche.chemins.inbox_dir / 'source.jpg', exif=exif)
    await retouche.outil.executer(dict(source='source.jpg', prompt='retoucher'), tmp_path)
    envoye = retouche.moteur.uploads[0]
    assert envoye.size == (640, 384) and envoye.mode == 'RGB'
    assert envoye.getpixel((500, 100))[0] > 240
    assert envoye.getpixel((100, 100))[2] > 240
    with Image.open(tmp_path / 'retouche_1.png') as resultat:
        assert resultat.size == (640, 384)


@pytest.mark.asyncio
async def test_revalide_avant_execution(retouche, tmp_path):
    params = retouche.outil.valider(dict(source='source.png', prompt='retoucher'))
    (retouche.chemins.inbox_dir / 'source.png').write_text('fichier remplacé')
    with pytest.raises(ParameterError):
        await retouche.outil.executer(params, tmp_path)
    assert not retouche.moteur.uploads and not retouche.moteur.appels


@pytest.mark.asyncio
@pytest.mark.parametrize('contenu,mime', [(b'', 'image/png'), (b'invalide', 'image/jpeg'),
                                        (octets_image(Image.new('RGB', (16, 16)), 'JPEG'), 'image/png')])
async def test_resultat_moteur_invalide(retouche, tmp_path, contenu, mime):
    retouche.moteur.contenu, retouche.moteur.mime = contenu, mime
    with pytest.raises(ValueError):
        await retouche.outil.executer(dict(source='source.png', prompt='retoucher'), tmp_path)
    assert not (tmp_path / 'retouche_1.png').exists()
    assert len(retouche.moteur.appels) == 1
