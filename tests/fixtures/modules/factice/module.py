from vertia.modules.contrat import Module
from vertia.tools.base import ParameterError


class EchoTool:
    capacite = 'test.echo'
    moteur = None
    name = 'echo'
    description = 'Renvoie le texte fourni.'
    engine = ''
    parameters = {'type': 'object', 'properties': {'texte': {'type': 'string'}}}

    def matches(self, text):
        return text.startswith('echo ')

    def validate(self, params):
        return {'texte': str(params.get('texte', ''))}

    async def run(self, params, progress):
        return self.validate(params)

    def valider(self, params):
        if not isinstance(params.get('texte'), str) or not params['texte']:
            raise ParameterError('texte est requis et doit être une chaîne non vide.')
        echecs = params.get('echec_jusqu_a', 0)
        if type(echecs) is not int or echecs < 0:
            raise ParameterError('echec_jusqu_a doit être un entier positif ou nul.')
        return dict(params, echec_jusqu_a=echecs)

    async def executer(self, params, dossier):
        import asyncio
        await asyncio.sleep(params.get('delai', 0))
        if params.get('erreur'):
            raise RuntimeError('Échec moteur simulé.')
        fichier = dossier / 'echo.txt'
        numero = int(dossier.name)
        texte = 'mauvais' if numero <= params['echec_jusqu_a'] else params['texte']
        fichier.write_text(texte, encoding='utf-8')
        return [fichier]


MODULE = Module(nom='factice', activite='outil', titre='Factice', version='1.0.0',
                outils={'echo': EchoTool}, capacites=['test.echo'],
                sante=lambda: {'pret': True})
