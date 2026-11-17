from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src/vertia/engines/travailleurs_protocole'))
from protocole import graine, initialiser, servir


def main():
    args, canal = initialiser()
    import numpy
    import soundfile
    from kokoro import KPipeline

    pipelines = {}

    def traiter(p):
        if p['action'] != 'synthese':
            raise ValueError('Action inconnue.')
        graine(p['seed'])
        code = {'fr': 'f', 'en': 'a'}[p['langue']]
        if code not in pipelines:
            pipelines[code] = KPipeline(lang_code=code, device=args.device, repo_id='hexgrad/Kokoro-82M')
        morceaux = []
        for _, _, audio in pipelines[code](p['texte'], voice=p['voix'], speed=p['vitesse']):
            if hasattr(audio, 'cpu'):
                audio = audio.cpu()
            if hasattr(audio, 'numpy'):
                audio = audio.numpy()
            morceaux.append(numpy.asarray(audio))
        soundfile.write(Path(p['sortie']) / 'voix_1.wav', numpy.concatenate(morceaux), 24000)
        return ['voix_1.wav']

    servir(canal, traiter)


if __name__ == '__main__':
    main()
