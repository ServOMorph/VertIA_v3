from vertia.chemins import resoudre_chemins
from vertia.modules.contrat import Module

from .outil import OutilImage
from .outil_retouche import OutilRetouche

POIDS = [
    'comfy/unet/qwen-image-2.1-Q4_K_M.gguf',
    'comfy/text_encoders/qwen3vl_8b_bf16.safetensors',
    'comfy/vae/qwen_image_2.1_vae_bf16.safetensors',
]


def sante():
    chemins = resoudre_chemins()
    manquants = [poids for poids in POIDS if not (chemins.models_dir / poids).is_file()]
    installation = chemins.comfy_dir.is_dir()
    return {'pret': installation and not manquants,
            'installation': installation, 'poids_manquants': manquants}


MODULE = Module(nom='image', activite='image', titre='Image', version='0.1.0',
                capacites=['image.generer', 'image.retoucher'],
                outils={'generer': OutilImage, 'retoucher': OutilRetouche},
                moteurs={}, besoins={}, poids=POIDS, sante=sante)
