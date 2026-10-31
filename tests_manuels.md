# Tests manuels en attente

## Vidéo n°1 — Wan 2.2 TI2V-5B (aucun téléchargement)
1. Fermer Ollama ou décharger les modèles (`ollama ps` doit être vide).
2. Lancer ComfyUI-Qwen en mode basse VRAM :
   ```powershell
   cd D:\ServOMorph\ComfyUI-Qwen
   .\.venv\Scripts\python.exe main.py --port 8189 --lowvram --reserve-vram 1
   ```
3. Ouvrir http://127.0.0.1:8189, menu Workflow > Browse Templates > Video > « Wan 2.2 5B TI2V ».
4. Remplacer « Load Diffusion Model » par « Unet Loader (GGUF) » → `Wan2.2-TI2V-5B-Q4_K_M.gguf`. Vérifier : CLIP = `umt5_xxl_fp8_e4m3fn_scaled`, VAE = `wan2.2_vae`. Remplacer « VAE Decode » par « VAE Decode (Tiled) ».
5. Test A (texte → vidéo) : 960×544, 49 images, 24 fps, 20 steps, CFG 5. Prompt : « a red fox walking through a snowy forest at sunrise, cinematic ».
6. Test B (image → vidéo) : charger une image Qwen existante (`D:\ServOMorph\ComfyUI-Qwen\output\`) sur `start_image`, mêmes réglages.
7. Me donner pour chaque test : temps total, plantage éventuel, note de qualité de 1 à 5 (fluidité, déformations, respect du prompt).
