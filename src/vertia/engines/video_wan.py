from __future__ import annotations

from vertia.engines.base import MemoryNeeds


def build_video_graph(p):
    graph = {
        '1': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': 'Wan2.2-TI2V-5B-Q4_K_M.gguf'}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'type': 'wan', 'device': 'default'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'wan2.2_vae.safetensors'}},
        '4': {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['2', 0], 'text': p['prompt']}},
        '5': {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['2', 0], 'text': p['negatif']}},
        '6': {'class_type': 'Wan22ImageToVideoLatent', 'inputs': {
            'vae': ['3', 0], 'width': p['largeur'], 'height': p['hauteur'], 'length': p['images'], 'batch_size': 1}},
        '7': {'class_type': 'ModelSamplingSD3', 'inputs': {'model': ['1', 0], 'shift': 8}},
        '8': {'class_type': 'KSampler', 'inputs': {
            'model': ['7', 0], 'seed': p['seed'], 'steps': p['etapes'], 'cfg': 5,
            'sampler_name': 'uni_pc', 'scheduler': 'simple', 'positive': ['4', 0],
            'negative': ['5', 0], 'latent_image': ['6', 0], 'denoise': 1}},
        '9': {'class_type': 'VAEDecodeTiled', 'inputs': {
            'samples': ['8', 0], 'vae': ['3', 0], 'tile_size': 256, 'overlap': 64,
            'temporal_size': 16, 'temporal_overlap': 8}},
        '10': {'class_type': 'CreateVideo', 'inputs': {'images': ['9', 0], 'fps': 24}},
        '11': {'class_type': 'SaveVideo', 'inputs': {
            'video': ['10', 0], 'filename_prefix': 'VertIA_video',
            'format': 'mp4', 'format.codec': 'h264'}},
    }
    if p.get('references'):
        graph['20'] = {'class_type': 'LoadImage', 'inputs': {'image': p['references'][0]}}
        graph['6']['inputs']['start_image'] = ['20', 0]
    return graph


class WanVideoEngine:
    """Adaptateur Wan ; le cycle de vie appartient au serveur ComfyUI partagé."""

    memory = MemoryNeeds(note='Besoins Wan inconnus ; seuils du serveur ComfyUI partagé appliqués.')

    def __init__(self, comfy):
        self.comfy = comfy

    async def start(self):
        await self.comfy.start()

    async def health(self):
        return await self.comfy.health()

    async def free(self):
        await self.comfy.free()

    async def stop(self):
        await self.comfy.stop()

    async def upload_image(self, data, mime):
        return await self.comfy.upload_image(data, mime)

    async def generate(self, params, progress):
        return await self.comfy.generate_graph(build_video_graph(params), progress, output_node='11', result_key='videos')

    async def preview(self, video):
        return await self.comfy.preview(video, formats={'.mp4': 'video/mp4'}, max_bytes=256 * 1024**2)
