from pathlib import Path

from vertia.tools.base import ParameterError
from vertia.tools.image import ImageTool


class OutilImage:
    capacite = 'image.generer'
    moteur = 'comfy'
    parameters = dict(ImageTool.parameters, mode='t2i uniquement',
                      references='aucune référence', masque='aucun masque')

    def __init__(self, settings, chemins, moteurs):
        self.adapter = moteurs[self.moteur]
        self.validation = ImageTool(self.adapter)

    def valider(self, params):
        try:
            result = self.validation.validate(params)
            if result['mode'] != 't2i' or result['references'] or result['masque'] is not None:
                raise ValueError('image.generer accepte uniquement t2i, sans référence ni masque.')
            return result
        except ValueError as exc:
            raise ParameterError(str(exc)) from exc

    async def executer(self, params, dossier: Path) -> list[Path]:
        result = await self.adapter.generate(self.valider(params), lambda progression: None)
        fichiers = []
        for index, image in enumerate(result.get('images', []), 1):
            data, mime = await self.adapter.preview(image, formats={'.png': 'image/png'})
            if mime != 'image/png' or not data:
                raise ValueError('Le moteur doit produire une image PNG non vide.')
            fichier = dossier / f'image_{index}.png'
            fichier.write_bytes(data)
            fichiers.append(fichier)
        return fichiers
