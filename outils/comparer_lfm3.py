"""Comparaison LFM3 (llama.cpp) et modèles Ollama sur des tâches VertIA en français.

Prérequis : le jeton GPU est détenu par la session vertia (vram_lock.py acquire), ce script ne le prend pas.
python outils/comparer_lfm3.py [--texte] [--vision] [--sortie _docs/lfm3_resultats.json]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LLAMA = ROOT / 'engines' / 'llamacpp' / 'llama-server.exe'
POIDS = ROOT / 'models' / 'llamacpp' / 'lfm3'
PORT = 8087

PROMPTS = [
    ('titre', "Donne un titre de conversation de 5 mots maximum pour ce message d'utilisateur, sans guillemets : "
              "« Peux-tu m'expliquer comment mettre en place une sauvegarde automatique de mes photos sur un disque externe ? »"),
    ('resume', "Résume en deux phrases : « VertIA est un portail unique pour l'IA locale. Il regroupe la génération d'images, "
               "de musique, de voix et de vidéo, ainsi qu'un chat. Le portail décide quel moteur utilise le GPU, car la carte "
               "n'a que 8 Go de mémoire et un seul modèle lourd peut tourner à la fois. Les autres projets l'appellent par "
               "une ligne de commande. »"),
    ('json', "Extrais en JSON strict (clés : nom, ville, date, montant) les informations de ce texte, sans commentaire : "
             "« Facture émise à Lyon le 12 mars 2026 pour Mme Camille Roux, montant total 1 249,90 euros. »"),
    ('outil', "Tu disposes de trois outils : image_qwen (créer ou modifier une image), musique_ace (créer un morceau), "
              "video_wan (créer une vidéo). Réponds uniquement par le nom de l'outil adapté à cette demande : "
              "« Fais-moi un jingle joyeux de 20 secondes pour ma boulangerie. »"),
    ('prompt_image', "Réécris en anglais, en une phrase descriptive détaillée pour un modèle de génération d'image : "
                     "« une vieille maison de pêcheur au bord de la mer, au lever du soleil, style aquarelle ». Réponds par la phrase seule."),
    ('connaissance', "Quelle est la capitale de l'Australie et en quelle année Canberra a-t-elle été désignée capitale ? Réponse courte."),
    ('raisonnement', "Un train part à 14h20 et arrive à 17h05. Un second part à 15h10 et met 15 minutes de moins. "
                     "À quelle heure arrive le second ? Donne le calcul puis la réponse."),
    ('consigne', "Écris exactement trois phrases en français, chacune de moins de dix mots, sur la pluie. Numérote-les 1, 2, 3."),
]


def requete(url, donnees=None, timeout=300):
    corps = None if donnees is None else json.dumps(donnees).encode()
    req = urllib.request.Request(url, data=corps, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def vram_mib():
    r = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                       capture_output=True, text=True)
    return int(r.stdout.strip().splitlines()[0])


def demarrer_llama(modele, mmproj=None, ctx=4096):
    commande = [str(LLAMA), '-m', str(modele), '-ngl', '99', '-c', str(ctx), '--port', str(PORT), '--host', '127.0.0.1']
    if mmproj:
        commande += ['--mmproj', str(mmproj)]
    log = open(ROOT / 'outputs' / 'lfm3_llama.log', 'w', encoding='utf-8')
    proc = subprocess.Popen(commande, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    debut = time.time()
    while time.time() - debut < 180:
        if proc.poll() is not None:
            raise RuntimeError('llama-server arrêté : voir outputs/lfm3_llama.log')
        try:
            if requete(f'http://127.0.0.1:{PORT}/health', timeout=2).get('status') == 'ok':
                return proc
        except Exception:
            time.sleep(1)
    proc.kill()
    raise RuntimeError('llama-server ne répond pas')


def arreter(proc):
    subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
    time.sleep(3)


def chat_llama(messages, max_tokens=400, sans_reflexion=False):
    t0 = time.time()
    r = requete(f'http://127.0.0.1:{PORT}/v1/chat/completions',
                dict(messages=messages, temperature=0.1, max_tokens=max_tokens,
                     **({'chat_template_kwargs': {'enable_thinking': False}} if sans_reflexion else {})))
    duree = time.time() - t0
    t = r.get('timings', {})
    msg = r['choices'][0]['message']
    return dict(texte=msg.get('content') or '', reflexion=(msg.get('reasoning_content') or '')[:1500], duree_s=round(duree, 2),
                tokens=r['usage']['completion_tokens'], tps=round(t.get('predicted_per_second', 0), 1),
                prompt_tps=round(t.get('prompt_per_second', 0), 1))


def chat_ollama(modele, messages, images=None, max_tokens=400):
    msgs = [dict(m) for m in messages]
    if images:
        msgs[-1]['images'] = images
    t0 = time.time()
    r = requete('http://127.0.0.1:11434/api/chat', dict(
        model=modele, messages=msgs, stream=False, think=False, keep_alive='5m',
        options=dict(temperature=0.1, num_predict=max_tokens, num_ctx=4096)))
    duree = time.time() - t0
    tps = r['eval_count'] / (r['eval_duration'] / 1e9) if r.get('eval_duration') else 0
    return dict(texte=r['message']['content'], duree_s=round(duree, 2), tokens=r['eval_count'], tps=round(tps, 1),
                prompt_tps=round(r['prompt_eval_count'] / (r['prompt_eval_duration'] / 1e9), 1)
                if r.get('prompt_eval_duration') else 0)


def liberer_ollama(modele):
    try:
        requete('http://127.0.0.1:11434/api/generate', dict(model=modele, keep_alive=0), timeout=60)
    except Exception:
        pass
    time.sleep(3)


def texte(resultats, tokens_lfm=1500, avec_ollama=True, sans_reflexion=False):
    modele = POIDS / 'LFM3-1.7B' / 'LFM3-1.7B-Q4_K_M.gguf'
    proc = demarrer_llama(modele)
    try:
        sortie = []
        for nom, prompt in PROMPTS:
            r = chat_llama([dict(role='user', content=prompt)], tokens_lfm, sans_reflexion)
            sortie.append(dict(prompt=nom, **r))
        resultats['lfm3_1.7b_sans_reflexion' if sans_reflexion else 'lfm3_1.7b'] = dict(vram_mib=vram_mib(), essais=sortie)
    finally:
        arreter(proc)
    if not avec_ollama:
        return
    modele = 'gemma4:12b'
    liberer_ollama(modele)
    sortie = []
    for nom, prompt in PROMPTS:
        r = chat_ollama(modele, [dict(role='user', content=prompt)])
        sortie.append(dict(prompt=nom, **r))
    resultats[modele] = dict(vram_mib=vram_mib(), essais=sortie)
    liberer_ollama(modele)


def images_test():
    from PIL import Image, ImageDraw, ImageFont
    voiture = ROOT / 'outputs' / 'creation_3d' / 'vehicule_voiture_3-4_seed20261115.png'
    img = Image.new('RGB', (900, 420), 'white')
    d = ImageDraw.Draw(img)
    police = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 34)
    for i, ligne in enumerate(['Facture n° 2026-118', 'Client : Camille Roux, Lyon', 'Date : 12 mars 2026',
                               'Papier A4 x 3 : 18,00 €', 'Total TTC : 1 249,90 €']):
        d.text((40, 40 + i * 70), ligne, fill='black', font=police)
    texte_png = ROOT / 'outputs' / 'lfm3_ocr_test.png'
    img.save(texte_png)
    return [(voiture, 'description', "Décris cette image en français en deux phrases."),
            (texte_png, 'ocr', "Recopie fidèlement le texte de cette image, ligne par ligne.")]


def b64(chemin):
    return base64.b64encode(Path(chemin).read_bytes()).decode()


def vision(resultats):
    cas = images_test()
    modele = POIDS / 'LFM3-VL-2B' / 'LFM3-VL-2B-Q4_K_M.gguf'
    mmproj = POIDS / 'LFM3-VL-2B' / 'mmproj-LFM3-VL-2B-Q8_0.gguf'
    proc = demarrer_llama(modele, mmproj)
    try:
        sortie = []
        for chemin, nom, prompt in cas:
            contenu = [dict(type='image_url', image_url=dict(url='data:image/png;base64,' + b64(chemin))),
                       dict(type='text', text=prompt)]
            sortie.append(dict(prompt=nom, **chat_llama([dict(role='user', content=contenu)], 500)))
        resultats['lfm3_vl_2b'] = dict(vram_mib=vram_mib(), essais=sortie)
    finally:
        arreter(proc)
    modele = 'qwen2.5vl:latest'
    liberer_ollama(modele)
    sortie = []
    for chemin, nom, prompt in cas:
        sortie.append(dict(prompt=nom, **chat_ollama(modele, [dict(role='user', content=prompt)], [b64(chemin)], 500)))
    resultats[modele] = dict(vram_mib=vram_mib(), essais=sortie)
    liberer_ollama(modele)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--texte', action='store_true')
    p.add_argument('--vision', action='store_true')
    p.add_argument('--sans-ollama', action='store_true')
    p.add_argument('--sans-reflexion', action='store_true')
    p.add_argument('--sortie', default=str(ROOT / '_docs' / 'lfm3_resultats.json'))
    a = p.parse_args()
    sortie = Path(a.sortie)
    resultats = json.loads(sortie.read_text(encoding='utf-8')) if sortie.exists() else {}
    (ROOT / 'outputs').mkdir(exist_ok=True)
    for actif, fonction in ((a.texte, lambda r: texte(r, avec_ollama=not a.sans_ollama, sans_reflexion=a.sans_reflexion)), (a.vision, vision)):
        if actif:
            fonction(resultats)
            sortie.write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding='utf-8')
    for modele, donnees in resultats.items():
        tps = [e['tps'] for e in donnees['essais']]
        print(modele, 'VRAM', donnees['vram_mib'], 'MiB', 'tps moyen', round(sum(tps) / len(tps), 1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
