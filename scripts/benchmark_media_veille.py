import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / 'benchmarks' / 'veille'
COMFY = Path('D:/ServOMorph/ComfyUI-Qwen')
PORT = 8199
URL = f'http://127.0.0.1:{PORT}'
sys.path.insert(0, str(RACINE / 'src'))

IMAGES = [
    ('affiche', "Une affiche illustrée de café, tasse de café fumante au centre, fond crème, avec le texte « OUVERT DU LUNDI AU SAMEDI » en grandes lettres lisibles."),
    ('portrait', "Portrait photographique d'une vieille pêcheuse bretonne, lumière naturelle du matin, détails de la peau, fond flou, objectif 85 mm."),
    ('objet', "Photo de produit : une théière en céramique bleue posée sur un fond blanc uni, ombre douce, éclairage de studio."),
]
VIDEOS = [
    ('tasse', "Une tasse de café fumante posée sur une table en bois près d'une fenêtre, lumière du matin, plan fixe."),
    ('foret', "Travelling avant lent dans une forêt de sapins couverte de brume, lumière douce traversant les branches."),
    ('personnage', "Une femme en manteau rouge marche dans une rue pavée sous la pluie, elle ouvre un parapluie, plan moyen."),
]


def vram():
    sortie = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
    return int(sortie[0])


class Sonde(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.pic = 0
        self.actif = True

    def run(self):
        while self.actif:
            try:
                self.pic = max(self.pic, vram())
            except Exception:
                pass
            time.sleep(0.4)


def http(chemin, corps=None):
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(URL + chemin, donnees, {'Content-Type': 'application/json'})
    with urllib.request.urlopen(requete, timeout=60) as reponse:
        return json.load(reponse)


def demarrer(dossier_sortie):
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    temp = SORTIE / 'tmp_comfy'
    temp.mkdir(parents=True, exist_ok=True)
    journal = open(SORTIE / 'comfy_bench.log', 'wb')
    processus = subprocess.Popen(
        [str(COMFY / '.venv/Scripts/python.exe'), '-B', 'main.py', '--port', str(PORT), '--lowvram', '--reserve-vram', '1',
         '--output-directory', str(dossier_sortie), '--temp-directory', str(temp)],
        cwd=COMFY, stdout=journal, stderr=journal, creationflags=subprocess.CREATE_NO_WINDOW)
    debut = time.time()
    while time.time() - debut < 600:
        try:
            http('/system_stats')
            return processus
        except Exception:
            if processus.poll() is not None:
                raise RuntimeError('ComfyUI arrêté au démarrage, voir comfy_bench.log')
            time.sleep(1)
    processus.terminate()
    raise RuntimeError('ComfyUI ne répond pas')


def arreter(processus):
    subprocess.run(['taskkill', '/PID', str(processus.pid), '/T', '/F'], capture_output=True)


def executer(graphe, delai=1500):
    identifiant = http('/prompt', {'prompt': graphe})['prompt_id']
    debut = time.time()
    while time.time() - debut < delai:
        historique = http(f'/history/{identifiant}')
        if identifiant in historique:
            entree = historique[identifiant]
            if entree['status'].get('status_str') != 'success':
                raise RuntimeError(json.dumps(entree['status'], ensure_ascii=False)[:600])
            return entree['outputs']
        time.sleep(1)
    raise RuntimeError('délai dépassé')


def graphe_qwen(prompt, prefixe):
    return {
        '1': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': 'qwen-image-2.1-Q4_K_M.gguf'}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'qwen3vl_8b_bf16.safetensors', 'type': 'qwen_image', 'device': 'default'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'qwen_image_2.1_vae_bf16.safetensors'}},
        '4': {'class_type': 'TextEncodeQwenImage21', 'inputs': {
            'clip': ['2', 0], 'prompt': prompt, 'negative_prompt': '', 'vae': ['3', 0], 'resolution': 1024}},
        '5': {'class_type': 'EmptyLatentImage', 'inputs': {'width': 1024, 'height': 1024, 'batch_size': 1}},
        '9': {'class_type': 'KSampler', 'inputs': {
            'model': ['1', 0], 'seed': 0, 'steps': 25, 'cfg': 1,
            'sampler_name': 'euler', 'scheduler': 'simple', 'positive': ['4', 0],
            'negative': ['4', 1], 'latent_image': ['5', 0], 'denoise': 1}},
        '11': {'class_type': 'VAEDecode', 'inputs': {'samples': ['9', 0], 'vae': ['3', 0]}},
        '12': {'class_type': 'SaveImage', 'inputs': {'images': ['11', 0], 'filename_prefix': prefixe}},
    }


def graphe_zimage(prompt, prefixe):
    return {
        '1': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': 'z_image_turbo-Q4_K_M.gguf'}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'qwen_3_4b_fp8_mixed.safetensors', 'type': 'lumina2', 'device': 'default'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'z_image_ae.safetensors'}},
        '4': {'class_type': 'ModelSamplingAuraFlow', 'inputs': {'model': ['1', 0], 'shift': 3}},
        '5': {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['2', 0], 'text': prompt}},
        '6': {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['5', 0]}},
        '7': {'class_type': 'EmptySD3LatentImage', 'inputs': {'width': 1024, 'height': 1024, 'batch_size': 1}},
        '8': {'class_type': 'KSampler', 'inputs': {'model': ['4', 0], 'seed': 0, 'steps': 8, 'cfg': 1, 'sampler_name': 'euler',
                                                   'scheduler': 'simple', 'positive': ['5', 0], 'negative': ['6', 0],
                                                   'latent_image': ['7', 0], 'denoise': 1}},
        '9': {'class_type': 'VAEDecode', 'inputs': {'samples': ['8', 0], 'vae': ['3', 0]}},
        '12': {'class_type': 'SaveImage', 'inputs': {'images': ['9', 0], 'filename_prefix': prefixe}},
    }


def graphe_wan(prompt, prefixe):
    return {
        '1': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': 'Wan2.2-TI2V-5B-Q4_K_M.gguf'}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'type': 'wan', 'device': 'default'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'wan2.2_vae.safetensors'}},
        '4': {'class_type': 'ModelSamplingSD3', 'inputs': {'model': ['1', 0], 'shift': 8}},
        '5': {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['2', 0], 'text': prompt}},
        '6': {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['2', 0], 'text': 'flou, déformé, artefacts, texte, filigrane'}},
        '7': {'class_type': 'Wan22ImageToVideoLatent', 'inputs': {'vae': ['3', 0], 'width': 832, 'height': 480, 'length': 17, 'batch_size': 1}},
        '8': {'class_type': 'KSampler', 'inputs': {'model': ['4', 0], 'seed': 0, 'steps': 20, 'cfg': 5, 'sampler_name': 'uni_pc',
                                                   'scheduler': 'simple', 'positive': ['5', 0], 'negative': ['6', 0],
                                                   'latent_image': ['7', 0], 'denoise': 1}},
        '9': {'class_type': 'VAEDecode', 'inputs': {'samples': ['8', 0], 'vae': ['3', 0]}},
        '10': {'class_type': 'CreateVideo', 'inputs': {'images': ['9', 0], 'fps': 24}},
        '12': {'class_type': 'SaveVideo', 'inputs': {'video': ['10', 0], 'filename_prefix': prefixe, 'format': 'mp4', 'codec': 'h264'}},
    }


LOTS = {
    'image': ('image', IMAGES, [('qwen-image-2.1', graphe_qwen), ('z-image-turbo', graphe_zimage)]),
    'video': ('video', VIDEOS, [('wan2.2-5b', graphe_wan)]),
}


def main():
    analyse = argparse.ArgumentParser()
    analyse.add_argument('lot', choices=LOTS)
    analyse.add_argument('--modeles', nargs='*')
    options = analyse.parse_args()
    nom, cas, modeles = LOTS[options.lot]
    if options.modeles:
        modeles = [m for m in modeles if m[0] in options.modeles]
    dossier = SORTIE / nom
    fichier = SORTIE / f'resultats_{nom}.json'
    resultats = json.loads(fichier.read_text(encoding='utf-8')) if fichier.exists() else {}
    processus = demarrer(dossier)
    try:
        base = vram()
        for modele, constructeur in modeles:
            lignes = []
            for identifiant, prompt in cas:
                sonde = Sonde()
                sonde.start()
                debut = time.time()
                try:
                    sorties = executer(constructeur(prompt, f'{modele}_{identifiant}'))
                    erreur = None
                except Exception as exc:
                    sorties, erreur = {}, str(exc)
                duree = time.time() - debut
                sonde.actif = False
                lignes.append({'cas': identifiant, 'duree_s': round(duree, 1), 'pic_vram_mib': sonde.pic,
                               'vram_ajoutee_mib': sonde.pic - base, 'erreur': erreur,
                               'sorties': json.loads(json.dumps(sorties))})
                print(modele, identifiant, round(duree, 1), 's', sonde.pic, 'MiB', erreur or 'ok', flush=True)
                resultats[modele] = {'base_mib': base, 'cas': lignes}
                fichier.write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding='utf-8')
    finally:
        arreter(processus)


main()
