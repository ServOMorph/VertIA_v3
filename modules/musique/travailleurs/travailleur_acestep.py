import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src/vertia/engines/travailleurs_protocole'))
from protocole import initialiser, servir

SECTION_SECONDS = 14.5


IDLE_W = 10.0


class GpuPowerMeter:
    def __init__(self, interval=0.5):
        self.interval = interval
        self.samples = []
        self._stop = threading.Event()
        self._thread = None

    def _read(self):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,power.limit", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5)
            util, limit = [float(x) for x in out.stdout.strip().splitlines()[0].split(",")]
            self.limit_w = limit
            return IDLE_W + (limit - IDLE_W) * util / 100.0, util
        except Exception:
            return None

    def _run(self):
        last = time.time()
        while not self._stop.is_set():
            reading = self._read()
            now = time.time()
            if reading is not None:
                self.samples.append((reading[0], now - last, reading[1]))
            last = now
            self._stop.wait(self.interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        total_s = sum(dt for _, dt, _ in self.samples)
        if not self.samples or total_s <= 0:
            return None
        wh = sum(w * dt for w, dt, _ in self.samples) / 3600.0
        return {"energy_wh_est": round(wh, 3),
                "gpu_util_avg_pct": round(sum(u * dt for _, dt, u in self.samples) / total_s, 1)}


def fit_lyrics(text, duration):
    sections = [p for p in re.split(r"(?m)^(?=\[)", text) if p.strip()]
    if len(sections) <= 3:
        return text
    target = max(3, min(len(sections), round(duration / SECTION_SECONDS)))
    if target >= len(sections):
        return text
    kept = sections[:target - 1] + [sections[-1]]
    return "\n".join(p.strip("\n") + "\n" for p in kept)


def prepare_audio(path, sortie, start=None, dur=None):
    src = os.path.abspath(path)
    if not os.path.isfile(src):
        raise ValueError(f'Audio introuvable : {src}')
    refs = Path(sortie) / 'refs'
    refs.mkdir(exist_ok=True)
    tag = hashlib.sha1(f"{src}|{start}|{dur}|{os.path.getmtime(src)}".encode()).hexdigest()[:10]
    dst = str(refs / f"{Path(src).stem[:40]}_{tag}.wav")
    if not os.path.isfile(dst):
        ffmpeg = os.environ.get('VERTIA_FFMPEG') or shutil.which('ffmpeg')
        if not ffmpeg:
            raise ValueError('ffmpeg introuvable.')
        cmd = [ffmpeg, '-y', '-loglevel', 'error']
        if start:
            cmd += ['-ss', str(start)]
        if dur:
            cmd += ['-t', str(dur)]
        cmd += ['-i', src, '-vn', '-ac', '2', '-ar', '48000', dst]
        subprocess.run(cmd, check=True)
    return dst


def object_values(value):
    fields = getattr(value, '__dataclass_fields__', None)
    if fields:
        return {name: getattr(value, name) for name in fields}
    return dict(vars(value))


def main():
    _, canal = initialiser()
    ace = os.environ['VERTIA_ACESTEP_DIR']
    os.chdir(ace)
    sys.path.insert(0, ace)
    for nom in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
        os.environ.pop(nom, None)

    import torch
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler
    from acestep.inference import GenerationParams, GenerationConfig, generate_music
    from acestep.constants import TASK_INSTRUCTIONS

    dit = AceStepHandler()
    msg, ok = dit.initialize_service(
        project_root=ace, config_path='acestep-v15-turbo', device='auto', offload_to_cpu=True)
    if not ok:
        sys.exit(f'DiT init failed: {msg}')
    llm = LLMHandler()
    lm_pret = False

    def traiter(p):
        nonlocal lm_pret
        if p['action'] != 'generation':
            raise ValueError('Action inconnue.')
        lm = p['lm']
        if lm and not lm_pret:
            msg, ok = llm.initialize(
                checkpoint_dir=os.path.join(ace, 'checkpoints'),
                lm_model_path='acestep-5Hz-lm-0.6B', backend='pt', device='auto',
                offload_to_cpu=True, dtype=None)
            if not ok:
                raise RuntimeError(f'LLM init failed: {msg}')
            lm_pret = True
        paroles = p['paroles']
        if p['instrumental'] and not paroles.strip():
            paroles = '[Instrumental]'
        elif p['ajuster_paroles']:
            paroles = fit_lyrics(paroles, p['duration'])
        params = GenerationParams(
            task_type='text2music', thinking=lm, caption=p['caption'], lyrics=paroles,
            instrumental=p['instrumental'], vocal_language=p['vocal_language'],
            duration=p['duration'], inference_steps=p['inference_steps'],
            guidance_scale=1.0, seed=p['seed'])
        if p.get('task_type'):
            params.task_type = str(p['task_type'])
            params.instruction = TASK_INSTRUCTIONS.get(params.task_type, params.instruction)
        sortie = Path(p['sortie'])
        for cle in ('reference_audio', 'src_audio'):
            if p.get(cle):
                setattr(params, cle, prepare_audio(p[cle], sortie))
        for cle in ('cover_noise_strength', 'audio_cover_strength', 'bpm', 'keyscale', 'timesignature'):
            if p.get(cle) is not None:
                setattr(params, cle, p[cle])
        config = GenerationConfig(batch_size=1, audio_format='wav', use_random_seed=False)
        sauvegarde = sortie / 'ace'
        sauvegarde.mkdir(exist_ok=True)
        debut = time.time()
        meter = GpuPowerMeter()
        meter.start()
        try:
            res = generate_music(dit, llm, params=params, config=config, save_dir=str(sauvegarde))
            path = res.audios[0]['path'] if res.success and res.audios else ''
            if not path or not os.path.isfile(path):
                raise RuntimeError(res.status_message or 'Aucun fichier produit.')
            audio = sortie / 'musique_1.wav'
            shutil.copyfile(path, audio)
        finally:
            mesure = meter.stop() or {}
            gc.collect()
            torch.cuda.empty_cache()
        elapsed = round(time.time() - debut, 1)
        output = dict(path=audio.name, format='wav', size_bytes=audio.stat().st_size)
        with audio.open('rb') as fichier:
            output['sha256'] = hashlib.file_digest(fichier, 'sha256').hexdigest()
        try:
            import torchaudio
            info = torchaudio.info(str(audio))
            output.update(sample_rate=int(info.sample_rate), channels=int(info.num_channels),
                          frames=int(info.num_frames), duration_seconds=info.num_frames / info.sample_rate)
        except Exception as exc:
            output['audio_probe_error'] = str(exc)
        try:
            revision = subprocess.run(['git', '-C', ace, 'rev-parse', 'HEAD'], capture_output=True,
                                      text=True, timeout=5, check=True).stdout.strip()
        except Exception:
            revision = 'non disponible'
        metadata = dict(
            params=object_values(params), generation_config=object_values(config),
            model='ACE-Step 1.5 turbo' + (' + LM 0.6B' if lm else ''), model_revision=revision,
            runtime=dict(os=platform.platform(), python=sys.version, torch=str(torch.__version__),
                         cuda_runtime=str(torch.version.cuda), cuda_available=bool(torch.cuda.is_available()),
                         device_selection='auto', offload_to_cpu=True),
            output=output, elapsed_s=elapsed, energy_wh_est=mesure.get('energy_wh_est'),
            gpu_util_avg_pct=mesure.get('gpu_util_avg_pct'))
        (sortie / 'musique_1.json').write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        return ['musique_1.wav', 'musique_1.json']

    servir(canal, traiter)


if __name__ == '__main__':
    main()
