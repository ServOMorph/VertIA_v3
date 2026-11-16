from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    'deplacer_poids', Path(__file__).resolve().parents[1] / 'outils/deplacer_poids.py')
poids = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = poids
spec.loader.exec_module(poids)

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Jonctions et partage de fichiers Windows')


@pytest.fixture
def chemins(tmp_path, monkeypatch):
    source = tmp_path / 'ancien dossier' / 'unet'
    source.mkdir(parents=True)
    (source / 'modele.bin').write_bytes(b'poids de test\x00\xff')
    (source / 'sous dossier').mkdir()
    (source / 'sous dossier' / 'configuration.json').write_text('{}', encoding='utf-8')
    (source / 'vide').mkdir()
    models = tmp_path / 'models'
    monkeypatch.setattr(poids, 'models_dir', lambda: models)
    return SimpleNamespace(source=source, destination=models / 'comfy' / 'unet',
                           journal=models / '_deplacements.jsonl', models=models, racine=tmp_path)


def cli(c, *options):
    return poids.main(['deplacer', str(c.source), str(c.destination), *options])


def contenu(c):
    assert not poids.est_lien(c.source)
    assert (c.source / 'modele.bin').read_bytes() == b'poids de test\x00\xff'
    assert (c.source / 'sous dossier' / 'configuration.json').read_text() == '{}'
    assert (c.source / 'vide').is_dir()


def lignes(c):
    return [json.loads(ligne) for ligne in c.journal.read_text(encoding='utf-8').splitlines()]


def deplacement(c):
    assert cli(c, '--appliquer') == 0
    return lignes(c)[0]


def test_simulation_sans_effet(chemins, capsys):
    c = chemins
    avant = sorted(str(p.relative_to(c.racine)) for p in c.racine.rglob('*'))
    assert cli(c) == 0
    assert sorted(str(p.relative_to(c.racine)) for p in c.racine.rglob('*')) == avant
    contenu(c)
    sortie = capsys.readouterr().out
    assert 'Simulation' in sortie and '2 fichiers' in sortie
    assert 'espace libre' in sortie and 'Jonction à créer' in sortie
    assert 'modele.bin' in sortie


def test_deplacement_et_journal(chemins):
    c = chemins
    entree = deplacement(c)
    poids.verifier_jonction(c.source, c.destination)
    assert (c.source / 'modele.bin').read_bytes() == (c.destination / 'modele.bin').read_bytes()
    assert (c.destination / 'vide').is_dir()
    assert entree['etat'] == 'deplace'
    assert entree['nombre_fichiers'] == 2
    assert entree['taille'] == len(b'poids de test\x00\xff') + 2
    assert entree['empreinte'] == poids.empreinte(c.destination)
    assert entree['source'] == str(c.source) and entree['destination'] == str(c.destination)
    assert entree['id'] and entree['date']


def test_retour_et_simulation(chemins):
    c = chemins
    entree = deplacement(c)
    assert poids.main(['retour', entree['id']]) == 0
    poids.verifier_jonction(c.source, c.destination)
    assert len(lignes(c)) == 1
    assert poids.main(['retour', entree['id'], '--appliquer']) == 0
    contenu(c)
    assert not c.destination.exists()
    assert [ligne['etat'] for ligne in lignes(c)] == ['deplace', 'retabli']
    assert poids.main(['retour', entree['id'], '--appliquer']) == 2


@pytest.mark.parametrize('destination_vide', [False, True])
def test_empreinte_differente_source_intacte(chemins, monkeypatch, destination_vide):
    c = chemins
    if destination_vide:
        c.destination.mkdir(parents=True)
    hacher = poids.hacher_fichier
    monkeypatch.setattr(poids, 'hacher_fichier', lambda p:
                        '0' * 64 if c.destination in p.parents else hacher(p))
    assert cli(c, '--appliquer') == 3
    contenu(c)
    assert c.destination.exists() == destination_vide
    if destination_vide:
        assert not list(c.destination.iterdir())
    assert not c.journal.exists() or c.journal.read_text() == ''


@pytest.mark.parametrize('cote', ['source', 'destination'])
def test_creation_llm_refuse_sans_lecture(chemins, monkeypatch, cote):
    c = chemins
    setattr(c, cote, c.racine / 'CrEaTiOn_LlM' / 'poids')

    def interdit(*args, **kwargs):
        pytest.fail('Le chemin creation_llm ne doit pas être parcouru')

    monkeypatch.setattr(poids, 'inventaire', interdit)
    assert cli(c, '--appliquer') == 2
    assert not c.journal.exists()


def test_source_jonction_refusee(chemins):
    c = chemins
    cible = c.racine / 'cible'
    c.source.rename(cible)
    poids.creer_jonction(c.source, cible)
    assert cli(c, '--appliquer') == 2
    poids.verifier_jonction(c.source, cible)
    assert not c.destination.exists()


def test_jonction_interne_refusee(chemins):
    c = chemins
    cible = c.racine / 'exterieur'
    cible.mkdir()
    temoin = cible / 'intact.bin'
    temoin.write_bytes(b'intact')
    poids.creer_jonction(c.source / 'lien', cible)
    assert cli(c, '--appliquer') == 2
    assert temoin.read_bytes() == b'intact'
    assert not c.destination.exists()


def test_ancetre_jonction_refuse(chemins):
    c = chemins
    cible = c.racine / 'autres models'
    cible.mkdir()
    c.models.mkdir()
    poids.creer_jonction(c.models / 'comfy', cible)
    assert cli(c, '--appliquer') == 2
    assert not list(cible.iterdir())
    contenu(c)


def test_destination_non_vide(chemins):
    c = chemins
    c.destination.mkdir(parents=True)
    (c.destination / 'temoin').write_bytes(b'intact')
    assert cli(c, '--appliquer') == 2
    assert (c.destination / 'temoin').read_bytes() == b'intact'
    contenu(c)


def test_destination_vide_acceptee(chemins):
    c = chemins
    c.destination.mkdir(parents=True)
    deplacement(c)
    poids.verifier_jonction(c.source, c.destination)


def test_espace_insuffisant(chemins, monkeypatch):
    monkeypatch.setattr(shutil, 'disk_usage', lambda p: SimpleNamespace(free=1))
    assert cli(chemins, '--appliquer') == 2
    contenu(chemins)
    assert not chemins.destination.exists()


def test_marge_espace_stricte(chemins, monkeypatch):
    monkeypatch.setattr(shutil, 'disk_usage', lambda p: SimpleNamespace(free=110))
    with pytest.raises(poids.Refus, match='Espace insuffisant'):
        poids.verifier_espace(chemins.destination, 100)


def test_echec_jonction_restaure(chemins, monkeypatch, capsys):
    def echec(*args):
        raise OSError('échec simulé')

    monkeypatch.setattr(poids, 'creer_jonction', echec)
    assert cli(chemins, '--appliquer') == 4
    contenu(chemins)
    assert not chemins.destination.exists()
    assert 'état initial rétabli' in capsys.readouterr().err
    assert chemins.journal.read_text() == ''


def test_fichier_utilise(chemins, capsys):
    with (chemins.source / 'modele.bin').open('ab'):
        assert cli(chemins, '--appliquer') == 2
    assert 'Fichier utilisé' in capsys.readouterr().err
    contenu(chemins)
    assert not chemins.destination.exists()


@pytest.mark.parametrize('cas', ['absente', 'fichier', 'identique', 'enfant', 'parent', 'hors_models'])
def test_controles_chemins(chemins, cas):
    c = chemins
    if cas == 'absente':
        c.source = c.racine / 'absente'
    elif cas == 'fichier':
        c.source = c.source / 'modele.bin'
    elif cas == 'identique':
        c.destination = c.source
    elif cas == 'enfant':
        c.destination = c.source / 'enfant'
    elif cas == 'parent':
        c.destination = c.source.parent
    else:
        c.destination = c.racine / 'hors models'
    assert cli(c, '--appliquer') == 2
    assert not c.journal.exists()


def test_journal_personnalise(chemins):
    c = chemins
    journal = c.racine / 'journaux' / 'mouvements.jsonl'
    assert cli(c, '--appliquer', '--journal', str(journal)) == 0
    entree = json.loads(journal.read_text())
    assert not c.journal.exists()
    assert poids.main(['retour', entree['id'], '--appliquer', '--journal', str(journal)]) == 0
    contenu(c)


@pytest.mark.parametrize('cote', ['source', 'destination'])
def test_journal_interne_refuse(chemins, cote):
    c = chemins
    assert cli(c, '--appliquer', '--journal', str(getattr(c, cote) / 'journal.jsonl')) == 2
    contenu(c)
    assert not c.destination.exists()


def test_echec_copie_nettoie(chemins, monkeypatch):
    copier = shutil.copy2

    def echec(source, destination):
        copier(source, destination)
        raise OSError('copie interrompue')

    monkeypatch.setattr(shutil, 'copy2', echec)
    assert cli(chemins, '--appliquer') == 1
    contenu(chemins)
    assert not chemins.destination.exists()


def test_echec_suppression_source_restaure(chemins, monkeypatch):
    supprimer = poids.supprimer_arbre

    def echec(chemin, proprietaire):
        if chemin == chemins.source:
            (chemin / 'modele.bin').unlink()
            raise OSError('suppression interrompue')
        supprimer(chemin, proprietaire)

    monkeypatch.setattr(poids, 'supprimer_arbre', echec)
    assert cli(chemins, '--appliquer') == 1
    contenu(chemins)
    assert not chemins.destination.exists()


def test_echec_journal_restaure(chemins, monkeypatch):
    def echec(*args):
        raise OSError('journal indisponible')

    monkeypatch.setattr(poids, 'journaliser', echec)
    assert cli(chemins, '--appliquer') == 1
    contenu(chemins)
    assert not chemins.destination.exists()


def test_retour_empreinte_changee_refuse(chemins):
    c = chemins
    entree = deplacement(c)
    (c.destination / 'modele.bin').write_bytes(b'modifie')
    assert poids.main(['retour', entree['id'], '--appliquer']) == 3
    poids.verifier_jonction(c.source, c.destination)
    assert len(lignes(c)) == 1


def test_retour_mauvaise_jonction_refuse(chemins):
    c = chemins
    entree = deplacement(c)
    poids.supprimer_jonction(c.source, c.destination)
    autre = c.racine / 'autre'
    autre.mkdir()
    poids.creer_jonction(c.source, autre)
    assert poids.main(['retour', entree['id'], '--appliquer']) == 2
    poids.verifier_jonction(c.source, autre)
    assert c.destination.is_dir()


def test_retour_empreinte_copie_differente_recree_jonction(chemins, monkeypatch):
    c = chemins
    entree = deplacement(c)
    hacher = poids.hacher_fichier
    monkeypatch.setattr(poids, 'hacher_fichier', lambda p:
                        '0' * 64 if c.source in p.parents else hacher(p))
    assert poids.main(['retour', entree['id'], '--appliquer']) == 3
    poids.verifier_jonction(c.source, c.destination)
    assert len(lignes(c)) == 1


def test_retour_suppression_partielle_repare(chemins, monkeypatch):
    c = chemins
    entree = deplacement(c)
    supprimer = poids.supprimer_arbre

    def echec(chemin, proprietaire):
        if chemin == c.destination:
            (chemin / 'modele.bin').unlink()
            raise OSError('suppression interrompue')
        supprimer(chemin, proprietaire)

    monkeypatch.setattr(poids, 'supprimer_arbre', echec)
    assert poids.main(['retour', entree['id'], '--appliquer']) == 1
    poids.verifier_jonction(c.source, c.destination)
    assert (c.destination / 'modele.bin').read_bytes() == b'poids de test\x00\xff'
    assert len(lignes(c)) == 1


def test_journal_inconnu_ou_invalide(chemins):
    c = chemins
    assert poids.main(['retour', 'inconnu']) == 2
    c.journal.parent.mkdir(parents=True)
    c.journal.write_text('{invalide', encoding='utf-8')
    assert poids.main(['retour', 'inconnu']) == 2


def test_suppression_refuse_jonction(chemins):
    c = chemins
    deplacement(c)
    with pytest.raises(poids.Refus, match='Jonction ou lien'):
        poids.supprimer_arbre(c.source, c.source)
    assert (c.destination / 'modele.bin').read_bytes() == b'poids de test\x00\xff'


def test_creation_llm_avant_normalisation(chemins):
    with pytest.raises(poids.Refus, match='creation_llm'):
        poids.normaliser(str(chemins.racine / 'creation_llm' / '..' / 'autre'))


def test_metacaractere_cmd_refuse_avant_copie(chemins):
    c = chemins
    c.destination = c.destination.with_name('poids%PATH%')
    assert cli(c, '--appliquer') == 2
    contenu(c)
    assert not c.journal.exists()


def test_jonction_creee_puis_erreur_restaure(chemins, monkeypatch):
    creer = poids.creer_jonction

    def echec(source, destination):
        creer(source, destination)
        raise OSError('échec après création')

    monkeypatch.setattr(poids, 'creer_jonction', echec)
    assert cli(chemins, '--appliquer') == 4
    contenu(chemins)
    assert not chemins.destination.exists()


@pytest.mark.parametrize('commande', ['deplacer', 'retour'])
def test_fsync_journal_echec_sans_ligne_partielle(chemins, monkeypatch, commande):
    c = chemins
    entree = deplacement(c) if commande == 'retour' else None

    def echec(*args):
        raise OSError('fsync simulé')

    monkeypatch.setattr(os, 'fsync', echec)
    if commande == 'retour':
        assert poids.main(['retour', entree['id'], '--appliquer']) == 1
        poids.verifier_jonction(c.source, c.destination)
        assert lignes(c) == [entree]
    else:
        assert cli(c, '--appliquer') == 1
        contenu(c)
        assert not c.destination.exists()
        assert c.journal.read_text() == ''


def test_source_changee_apres_hachage_preservee(chemins, monkeypatch):
    c = chemins
    comparer = poids.comparer
    nouveau = b'valeur nouvelle et plus longue'

    def modifier(source, destination):
        signature = comparer(source, destination)
        (source / 'modele.bin').write_bytes(nouveau)
        return signature

    monkeypatch.setattr(poids, 'comparer', modifier)
    assert cli(c, '--appliquer') == 2
    assert (c.source / 'modele.bin').read_bytes() == nouveau
    assert not poids.est_lien(c.source)
    assert not c.destination.exists()


def test_dossier_vide_deplacement_et_retour(chemins):
    c = chemins
    (c.source / 'modele.bin').unlink()
    (c.source / 'sous dossier' / 'configuration.json').unlink()
    entree = deplacement(c)
    assert entree['nombre_fichiers'] == 0 and entree['taille'] == 0
    assert poids.main(['retour', entree['id'], '--appliquer']) == 0
    assert not poids.est_lien(c.source)
    assert (c.source / 'vide').is_dir()
