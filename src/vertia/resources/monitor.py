from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess

import psutil


def command(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=4,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                          check=True).stdout


def parse_gpus(text):
    gpus = []
    for line in text.strip().splitlines():
        values = line.split(',')
        if len(values) != 4:
            continue
        def number(value):
            try:
                return float(value.strip())
            except ValueError:
                return None
        used, total, utilization, temperature = map(number, values)
        if used is not None and total and total > 0:
            gpus.append(dict(used_mb=used, total_mb=total, percent=100 * used / total,
                             utilization=utilization, temperature=temperature))
    return gpus


def parse_processes(text):
    rows = json.loads(text or '[]') or []
    if isinstance(rows, dict):
        rows = [rows]
    totals = {}
    for row in rows:
        match = re.search(r'pid_(\d+)_', row.get('Name') or row.get('InstanceName') or '', re.I)
        if match:
            pid = int(match[1])
            totals[pid] = totals.get(pid, 0) + max(0, float(row.get('LocalUsage', 0)))
    return [dict(pid=pid, used_mb=value / 1024 ** 2) for pid, value in sorted(totals.items()) if value]


class ResourceMonitor:
    def __init__(self, ollama, runner=command):
        self.ollama = ollama
        self.runner = runner
        self.latest = dict(gpus=[], processes=[], ram=None, models=[], warnings=['Mesure en attente.'])
        self.lock = asyncio.Lock()

    def _hardware(self):
        memory = psutil.virtual_memory()
        result = dict(gpus=[], processes=[], ram=dict(
            used_mb=(memory.total - memory.available) / 1024 ** 2,
            total_mb=memory.total / 1024 ** 2, percent=memory.percent), warnings=[])
        try:
            result['gpus'] = parse_gpus(self.runner([
                'nvidia-smi', '--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu',
                '--format=csv,noheader,nounits']))
            if not result['gpus']:
                result['warnings'].append('Mesure VRAM indisponible.')
        except (OSError, subprocess.SubprocessError, ValueError):
            result['warnings'].append('Mesure VRAM indisponible (nvidia-smi).')
        if os.name == 'nt':
            try:
                result['processes'] = parse_processes(self.runner([
                    'powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                    'Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory '
                    '| Select-Object Name,LocalUsage | ConvertTo-Json -Compress']))
            except (OSError, subprocess.SubprocessError, ValueError, TypeError):
                result['warnings'].append('VRAM par processus indisponible (compteurs Windows).')
        return result

    async def sample(self):
        async with self.lock:
            result = await asyncio.to_thread(self._hardware)
            try:
                result['models'] = await asyncio.wait_for(self.ollama.loaded_models(), 3)
            except Exception:
                result['models'] = []
                result['warnings'].append('Liste des modèles Ollama indisponible.')
            self.latest = result
            return result


class MemoryRefused(RuntimeError):
    pass


class MemoryGuard:
    def __init__(self, monitor, vram_limit, ram_limit, resident_reserve_mb=512):
        if not 1 <= vram_limit <= 100 or not 1 <= ram_limit <= 100:
            raise ValueError('Les seuils mémoire doivent être compris entre 1 et 100 %.')
        self.monitor, self.vram_limit, self.ram_limit = monitor, vram_limit, ram_limit
        if resident_reserve_mb < 128:
            raise ValueError('La réserve VRAM doit être au moins de 128 Mio.')
        self.resident_reserve_mb = resident_reserve_mb

    async def check(self, needs=None, *, reuse=None):
        state = await self.monitor.sample()
        if state['ram'] is None:
            raise MemoryRefused('Mémoire RAM non mesurable : tâche refusée. Réessayez après vérification du système.')
        if state['ram']['percent'] >= self.ram_limit:
            raise MemoryRefused(f"RAM à {state['ram']['percent']:.0f} % (limite {self.ram_limit} %). Fermez des applications puis réessayez.")
        resident = reuse is not None and reuse(state)
        if resident:
            for gpu in state['gpus']:
                reserve = max(self.resident_reserve_mb, gpu['total_mb'] * .03)
                free = max(0, gpu['total_mb'] - gpu['used_mb'])
                if free < reserve:
                    raise MemoryRefused(f'VRAM presque saturée malgré le modèle déjà chargé : {free:.0f} Mio libres, réserve requise {reserve:.0f} Mio. Fermez une application GPU ou choisissez un modèle/contexte plus petit.')
        elif any(gpu['percent'] >= self.vram_limit for gpu in state['gpus']):
            raise MemoryRefused(f'VRAM au-dessus de la limite de {self.vram_limit} %. Déchargez les modèles ou fermez une application GPU puis réessayez.')
        if needs and needs.ram_mb and state['ram']['total_mb'] * self.ram_limit / 100 - state['ram']['used_mb'] < needs.ram_mb:
            raise MemoryRefused(f'RAM disponible insuffisante : au moins {needs.ram_mb} Mo nécessaires. Fermez des applications puis réessayez.')
        if needs and needs.vram_mb and state['gpus'] and not any(
                gpu['total_mb'] * self.vram_limit / 100 - gpu['used_mb'] >= needs.vram_mb for gpu in state['gpus']):
            raise MemoryRefused(f'VRAM disponible insuffisante : au moins {needs.vram_mb} Mo nécessaires.')
