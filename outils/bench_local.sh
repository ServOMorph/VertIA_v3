#!/usr/bin/env bash
# Benchmark des modeles Ollama locaux : un jeton GPU de 45 min par modele, rendu entre deux modeles.
cd "$(dirname "$0")/.." || exit 1
PY=.venv/Scripts/python.exe
for modele in gemma4:12b qwen3.5:latest qwen2.5-coder:7b gemma4:12b-32k; do
  $PY _orchestration/vram_lock.py acquire vertia --gb 8 --minutes 45 --wait --timeout 3600 --note "benchmark agents local : $modele" || { echo "acquire refuse pour $modele"; continue; }
  $PY outils/bench_agents.py --agents "oc:ollama/$modele" --tasks t1 t2 t3 --parallele 1 --delai-max 420
  ollama stop "$modele" >/dev/null 2>&1
  sleep 8
  $PY _orchestration/vram_lock.py release vertia
done
