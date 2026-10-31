# Vidéo locale — recherche et benchmark (piste R)

Recherche du 2026-10-31. [V] = vérifié sur source, [E] = estimation / chiffre communautaire.

## Candidats retenus (RTX 4060 8 Go, 48 Go RAM)

| Rang | Modèle | Licence | Téléchargement | Temps attendu |
|---|---|---|---|---|
| 1 | Wan 2.2 TI2V-5B GGUF Q4_K_M (T2V + I2V) | Apache 2.0 [V] | Aucun : déjà dans ComfyUI-Qwen (`unet`, `umt5_xxl_fp8`, `wan2.2_vae`) | 95-179 s en 480² ; 6-15 min en 720p [E] |
| 2 | Wan 2.2 I2V A14B GGUF Q4_K_S + LoRA lightx2v 4 steps | Apache 2.0 [V] | ~18 Go (2 GGUF high/low + wan_2.1_vae + 2 LoRA) | 111 s en 480² 33 images ; 5-10 min en 832×480 81 images [E] |
| 3 | LTX-2.3 distillé GGUF Q4_K_M (avec audio) | LTX Community, gratuit < 10 M$ CA [V] | ~24 Go (GGUF 14,2 Go + Gemma-3 12B GGUF + VAE) ; ComfyUI-GGUF à mettre à jour | ~1 min / vidéo [E] |

Écartés : HunyuanVideo 1.5, FramePack, MiniMax H3 (licences excluant l'UE) ; Wan 2.5/2.6 (API seule) ; CogVideoX, Mochi, Wan 2.1 1.3B (dépassés) ; LTX-2.5 (pas de test 8 Go publié, à surveiller).

## Paramètres de départ
- Wan 5B : ComfyUI `--lowvram --reserve-vram 1`, template natif `video_wan2_2_5B_ti2v`, Unet Loader (GGUF), image sur `start_image` de `Wan22ImageToVideoLatent`, 960×544 puis 1280×704, 49-73 images à 24 fps, uni_pc/simple, 20-30 steps, CFG 5, **VAE Decode (Tiled)**.
- Wan A14B : template `video_wan2_2_14B_i2v`, 2 Unet Loader GGUF + LoraLoaderModelOnly, 832×480, 81 images 16 fps, 4 steps (2 high / 2 low), CFG 1, euler/simple, VAE tuilé.
- LTX-2.3 : `--lowvram --reserve-vram 1 --cache-lru 10`, 6 + 2 steps, sans upscale intégré.

## Sources
- https://docs.comfy.org/tutorials/video/wan/wan2_2
- https://huggingface.co/QuantStack/Wan2.2-TI2V-5B-GGUF
- https://huggingface.co/QuantStack/Wan2.2-I2V-A14B-GGUF
- https://huggingface.co/lightx2v/Wan2.2-Distill-Loras
- https://docs.comfy.org/tutorials/video/ltx/ltx-2-3.md
- https://lilting.ch/en/articles/wan22-comfyui-rtx4060-i2v
- https://aistudynow.com/how-to-run-ltx-2-3-on-an-8gb-gpu-without-oom-errors/
- https://huggingface.co/tencent/HunyuanVideo-1.5/blob/main/LICENSE

## Résultats mesurés

| Date | Modèle | Résolution / images | Steps | Temps | VRAM pic | Qualité (1-5) | Notes |
|---|---|---|---|---|---|---|---|
