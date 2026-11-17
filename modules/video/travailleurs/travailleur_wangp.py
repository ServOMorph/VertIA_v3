import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src/vertia/engines/travailleurs_protocole'))
from protocole import initialiser, servir

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


class GpuMeter(GpuPowerMeter):
    def __init__(self, interval=0.5):
        super().__init__(interval)
        self.vram_max_mib = None

    def _read(self):
        reading = super()._read()
        try:
            out = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5, check=True)
            memory = max(float(line.strip()) for line in out.stdout.splitlines())
            self.vram_max_mib = max(self.vram_max_mib or 0, memory)
        except Exception:
            pass
        return reading


def serialisable(valeur):
    if isinstance(valeur, dict):
        return {str(cle): serialisable(element) for cle, element in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [serialisable(element) for element in valeur]
    try:
        json.dumps(valeur, allow_nan=False)
        return valeur
    except (TypeError, ValueError):
        return str(valeur)


def main():
    _, canal = initialiser()
    wangp = os.environ['VERTIA_WANGP_DIR']
    os.chdir(wangp)
    sys.path.insert(0, wangp)

    import torch
    from shared.api import init

    session = init(console_output=False)

    def traiter(p):
        if p['action'] != 'generation':
            raise ValueError('Action inconnue.')
        mode = p['mode']
        if mode not in ('t2v', 'i2v'):
            raise ValueError('Mode inconnu.')
        debut = time.monotonic()
        meter = GpuMeter()
        meter.start()
        try:
            s = session.get_default_settings(mode)
            if mode == 'i2v':
                if not p.get('image_start'):
                    raise ValueError('Image requise en i2v.')
                s.update({'image_prompt_type': 'S',
                          'image_start': [str(Path(p['image_start']).resolve())]})
            if p.get('negative_prompt'):
                s['negative_prompt'] = p['negative_prompt']
            s.update({'prompt': p['prompt'], 'seed': p['seed'], 'resolution': p['resolution'],
                      'video_length': p['video_length']})
            if p.get('num_inference_steps') is not None:
                s['num_inference_steps'] = p['num_inference_steps']
            result = session.run_task(s)
            if not result.generated_files:
                raise RuntimeError('Aucune sortie : ' + '; '.join(str(e) for e in result.errors))
            origine = Path(result.generated_files[0])
            sortie = Path(p['sortie'])
            video = sortie / 'video_1.mp4'
            shutil.copyfile(origine, video)
            origine.unlink()
        finally:
            mesure = meter.stop() or {}
            gc.collect()
            torch.cuda.empty_cache()
        elapsed = round(time.monotonic() - debut, 1)
        output = dict(path=video.name, format='mp4', size_bytes=video.stat().st_size)
        with video.open('rb') as fichier:
            output['sha256'] = hashlib.file_digest(fichier, 'sha256').hexdigest()
        try:
            revision = subprocess.run(['git', '-C', wangp, 'rev-parse', 'HEAD'], capture_output=True,
                                      text=True, timeout=5, check=True).stdout.strip()
        except Exception:
            revision = 'non disponible'
        metadata = dict(
            params=serialisable(s),
            model='Wan2.1 Text2video 14B' if mode == 't2v' else 'Wan2.1 Image2video 480p 14B',
            model_revision=revision,
            runtime=dict(os=platform.platform(), python=sys.version, torch=str(torch.__version__),
                         cuda_runtime=str(torch.version.cuda), cuda_available=bool(torch.cuda.is_available())),
            output=output, elapsed_s=elapsed, energy_wh_est=mesure.get('energy_wh_est'),
            gpu_util_avg_pct=mesure.get('gpu_util_avg_pct'), vram_max_mib=meter.vram_max_mib)
        (sortie / 'video_1.json').write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        return ['video_1.mp4', 'video_1.json']

    servir(canal, traiter)


if __name__ == '__main__':
    main()
