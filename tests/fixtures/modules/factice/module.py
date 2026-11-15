from vertia.modules.contrat import Module


class EchoTool:
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


MODULE = Module(nom='factice', activite='outil', titre='Factice', version='1.0.0',
                outils={'echo': EchoTool}, capacites=['test.echo'],
                sante=lambda: {'pret': True})
