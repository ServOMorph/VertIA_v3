from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocole import graine, initialiser, servir


def main():
    args, canal = initialiser()
    import soundfile
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    torch.set_num_threads(6)
    model = ChatterboxMultilingualTTS.from_pretrained(device=args.device)

    def traiter(p):
        if p['action'] != 'synthese':
            raise ValueError('Action inconnue.')
        graine(p['seed'])
        wav = model.generate(p['texte'], language_id=p['langue'],
                             audio_prompt_path=p['reference'], exaggeration=p['exageration'],
                             cfg_weight=p['cfg'], temperature=p['temperature'])
        soundfile.write(Path(p['sortie']) / 'voix_1.wav', wav.squeeze().cpu().numpy(), model.sr)
        return ['voix_1.wav']

    servir(canal, traiter)


if __name__ == '__main__':
    main()
