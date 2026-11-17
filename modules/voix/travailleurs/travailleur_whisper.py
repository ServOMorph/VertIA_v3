import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src/vertia/engines/travailleurs_protocole'))
from protocole import initialiser, servir

MODELES = {'tiny', 'base', 'small', 'medium', 'large-v3', 'large-v3-turbo'}


def main():
    args, canal = initialiser()
    import whisper

    model, nom = None, None

    def traiter(p):
        nonlocal model, nom
        if p['action'] != 'transcription':
            raise ValueError('Action inconnue.')
        dossier = Path(os.environ['VERTIA_WHISPER_DIR'])
        modele = p['modele']
        if modele not in MODELES or not (dossier / f'{modele}.pt').is_file():
            raise ValueError('Poids Whisper absents.')
        if nom != modele:
            model = None
            model = whisper.load_model(modele, device=args.device, download_root=str(dossier))
            nom = modele
        resultat = model.transcribe(p['chemin_audio'], language=p['langue'] or None,
                                    fp16=args.device == 'cuda')
        texte = resultat['text'].strip()
        sortie = Path(p['sortie'])
        (sortie / 'transcription.txt').write_text(texte, encoding='utf-8')
        document = dict(texte=texte, langue=resultat.get('language'), segments=[
            dict(debut=s['start'], fin=s['end'], texte=s['text'].strip())
            for s in resultat.get('segments', [])])
        (sortie / 'transcription.json').write_text(
            json.dumps(document, ensure_ascii=False), encoding='utf-8')
        return ['transcription.txt', 'transcription.json']

    servir(canal, traiter)


if __name__ == '__main__':
    main()
