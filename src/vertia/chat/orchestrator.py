from __future__ import annotations

import json
from uuid import uuid4

from vertia.engines.base import EngineError
from vertia.tools.base import ParameterError


class Orchestrator:
    def __init__(self, db, repository, registry, jobs, events, files=None):
        self.db, self.repository, self.registry = db, repository, registry
        self.jobs, self.events = jobs, events
        self.files = files
        self.ephemeral = {}
        jobs.register('outil', self.run)

    def instruction(self, text):
        names = self.registry.candidates(text)
        if not names:
            return ''
        return ('Pour ce message, décide si un outil est demandé. '
                'Une explication, une négation ou une demande de code ne crée aucune action. '
                'Réponds uniquement en JSON, sans Markdown. Pour discuter : {"response":"ta réponse"}. '
                'Pour proposer une action : {"tool":"nom exact de l’outil","parameters":{}} avec les paramètres du schéma. '
                'N’exécute rien. Respecte dimensions, texte à afficher, langue et contraintes demandés. '
                'Respecte les capacités disponibles ; explique toute fonction indisponible sans la remplacer par une autre. '
                'Ne prétends pas lire ou recevoir un fichier ; seuls ses identifiants courts peuvent être fournis. '
                'Outils disponibles : ' + self.registry.schemas(names))

    def propose(self, conv_id, message_id, output, source):
        try:
            data = json.loads(output)
            if not isinstance(data, dict):
                raise ValueError('Objet JSON attendu.')
            if set(data) == {'response'} and isinstance(data['response'], str) and data['response'].strip():
                return data['response']
            if set(data) != {'tool', 'parameters'} or not isinstance(data['parameters'], dict):
                raise ValueError('Structure de carte incorrecte.')
            tool = self.registry.get(data['tool'])
            if tool.name not in self.registry.candidates(source):
                raise ValueError('Outil hors de la demande.')
            params = tool.validate(data['parameters'])
            self.check_references(conv_id, params)
        except ParameterError as exc:
            raise ParameterError('Carte d’action invalide : ' + str(exc)) from None
        except (ValueError, TypeError):
            raise ValueError('Carte d’action invalide : aucune génération lancée. Reformulez la demande avec les paramètres souhaités.') from None
        action = dict(id=uuid4().hex, conversation_id=conv_id, message_id=message_id,
                      tool=tool.name, parameters=params, status='proposee', job_id=None, result={})
        conv = self.repository.conversation(conv_id)
        if conv['ephemere']:
            self.ephemeral[action['id']] = action
        else:
            with self.db.session() as conn:
                conn.execute('INSERT INTO actions(id,conversation_id,message_id,tool,parameters) VALUES(?,?,?,?,?)',
                             (action['id'], conv_id, message_id, tool.name, json.dumps(params, ensure_ascii=False)))
        self.events.publish('actions.maj', action)
        return f"Action proposée [{action['id']} : {tool.name}]. Vérifiez la carte avant de lancer la génération."

    def get(self, action_id):
        if action_id in self.ephemeral:
            return dict(self.ephemeral[action_id])
        with self.db.session() as conn:
            row = conn.execute('SELECT * FROM actions WHERE id=?', (action_id,)).fetchone()
        if not row:
            raise LookupError('Carte introuvable.')
        return dict(row, parameters=json.loads(row['parameters']), result=json.loads(row['result']))

    def list(self, conv_id):
        with self.db.session() as conn:
            ids = [row[0] for row in conn.execute('SELECT id FROM actions WHERE conversation_id=? ORDER BY rowid', (conv_id,))]
        ids += [a['id'] for a in self.ephemeral.values() if a['conversation_id'] == conv_id]
        result = []
        for action_id in ids:
            action = self.get(action_id)
            if action['job_id']:
                with self.db.session() as conn:
                    latest = conn.execute("SELECT id FROM jobs WHERE json_extract(payload,'$.action_id')=? ORDER BY rowid DESC LIMIT 1", (action_id,)).fetchone()
                if latest:
                    action['job_id'] = latest[0]
                action['job'] = self.jobs.get(action['job_id'])
            result.append(action)
        return result

    def update(self, action_id, **values):
        if not values.keys() <= {'parameters', 'status', 'job_id', 'result'}:
            raise ValueError('Champs de carte invalides.')
        if action_id in self.ephemeral:
            self.ephemeral[action_id].update(values)
        else:
            stored = {k: json.dumps(v, ensure_ascii=False) if k in {'parameters', 'result'} else v for k, v in values.items()}
            with self.db.session() as conn:
                conn.execute('UPDATE actions SET ' + ','.join(f'{k}=?' for k in stored) + ' WHERE id=?', (*stored.values(), action_id))
        action = self.get(action_id)
        self.events.publish('actions.maj', action)
        return action

    def edit(self, action_id, params):
        action = self.get(action_id)
        if action['status'] != 'proposee':
            raise ValueError('Cette carte a déjà été validée ou annulée.')
        params = self.registry.get(action['tool']).validate(params)
        self.check_references(action['conversation_id'], params)
        return self.update(action_id, parameters=params)

    def check_references(self, conv_id, params):
        if self.files:
            self.files.references(conv_id, params.get('references', []))

    def cancel(self, action_id):
        if self.get(action_id)['status'] != 'proposee':
            raise ValueError('Utilisez la file Mémoire pour annuler une génération validée.')
        return self.update(action_id, status='annulee')

    def confirm(self, action_id, params):
        action = self.edit(action_id, params)
        tool = self.registry.get(action['tool'])
        conv = self.repository.conversation(action['conversation_id'])
        # Une action éphémère ne doit laisser aucun prompt dans les jobs persistés.
        operation = None
        if conv['ephemere']:
            async def operation():
                return await self.run({'action_id': action_id}, lambda value: self.jobs.progress(self.get(action_id)['job_id'], value))
        job_id = self.jobs.submit('outil', tool.engine, {'action_id': action_id} if not operation else {}, operation=operation)
        return self.update(action_id, status='validee', job_id=job_id)

    async def run(self, payload, progress):
        action = self.get(payload['action_id'])
        self.check_references(action['conversation_id'], action['parameters'])
        tool = self.registry.get(action['tool'])
        result = await tool.run(action['parameters'], progress)
        if self.files and hasattr(tool, 'artifacts'):
            self.update(action['id'], result=result)
            try:
                artifacts = await tool.artifacts(result)
                result['files'] = self.files.save(action, self.jobs.active, artifacts)
            except (OSError, ValueError) as exc:
                raise EngineError('Résultat généré, mais copie locale impossible. Vérifiez le disque et l’aperçu de la carte avant de relancer une génération.') from exc
        self.update(action['id'], result=result)
        return result

    def busy(self, conv_id):
        if any(a.get('job', {}).get('status') in {'attente', 'actif'} for a in self.list(conv_id)):
            return True
        with self.db.session() as conn:
            return conn.execute(
                "SELECT 1 FROM jobs JOIN actions ON actions.id=json_extract(jobs.payload,'$.action_id') "
                "WHERE actions.conversation_id=? AND jobs.status IN ('attente','actif') LIMIT 1",
                (conv_id,),
            ).fetchone() is not None

    def forget(self, conv_id):
        for action_id in [key for key, a in self.ephemeral.items() if a['conversation_id'] == conv_id]:
            del self.ephemeral[action_id]
