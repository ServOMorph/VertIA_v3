from __future__ import annotations

from uuid import uuid4

from vertia.core.db import Database


class ChatRepository:
    def __init__(self, db: Database):
        self.db = db
        self.ephemeral: dict[str, dict] = {}
        with db.session() as conn:
            conn.execute("UPDATE messages SET statut = 'interrompu' WHERE statut IN ('attente', 'actif')")

    def folders(self):
        with self.db.session() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM dossiers ORDER BY epingle DESC, position, nom COLLATE NOCASE')]

    def folder(self, folder_id: str):
        return next((f for f in self.folders() if f['id'] == folder_id), None)

    def create_folder(self, nom: str, system_prompt: str):
        folder = {'id': uuid4().hex, 'nom': nom, 'system_prompt': system_prompt}
        with self.db.session() as conn:
            conn.execute('INSERT INTO dossiers (id, nom, system_prompt) VALUES (:id, :nom, :system_prompt)', folder)
        return self.folder(folder['id'])

    def pin_folder(self, folder_id: str, pinned: bool):
        with self.db.session() as conn:
            conn.execute('UPDATE dossiers SET epingle = ? WHERE id = ?', (pinned, folder_id))
        return self.folder(folder_id)

    def reorder(self, kind: str, ids: list[str]):
        table = {'dossiers': 'dossiers', 'conversations': 'conversations'}[kind]
        available = {item['id'] for item in (self.folders() if kind == 'dossiers' else self.conversations())}
        if len(ids) != len(set(ids)) or set(ids) - available:
            raise ValueError('Liste de classement invalide. Actualisez les discussions.')
        with self.db.session() as conn:
            for position, item_id in enumerate(ids):
                conn.execute(f'UPDATE {table} SET position = ? WHERE id = ?', (position, item_id))
        if kind == 'conversations':
            for position, item_id in enumerate(ids):
                if item_id in self.ephemeral:
                    self.ephemeral[item_id]['position'] = position

    def update_folder(self, folder_id: str, nom: str, system_prompt: str):
        with self.db.session() as conn:
            conn.execute('UPDATE dossiers SET nom = ?, system_prompt = ? WHERE id = ?', (nom, system_prompt, folder_id))
        return self.folder(folder_id)

    def delete_folder(self, folder_id: str):
        with self.db.session() as conn:
            conn.execute('DELETE FROM dossiers WHERE id = ?', (folder_id,))
        for conv in self.ephemeral.values():
            if conv['dossier_id'] == folder_id:
                conv['dossier_id'] = None

    def conversations(self):
        with self.db.session() as conn:
            rows = [dict(r, ephemere=False) for r in conn.execute('SELECT * FROM conversations ORDER BY date_maj DESC, rowid DESC')]
        return sorted([self._public(c) for c in self.ephemeral.values()] + rows,
                      key=lambda c: (-int(c.get('epingle', 0)), c.get('position', 0)))

    @staticmethod
    def _public(conv):
        return {k: v for k, v in conv.items() if k != 'messages'}

    def conversation(self, conv_id: str):
        if conv_id in self.ephemeral:
            return self._public(self.ephemeral[conv_id])
        with self.db.session() as conn:
            row = conn.execute('SELECT * FROM conversations WHERE id = ?', (conv_id,)).fetchone()
        return dict(row, ephemere=False) if row else None

    def create_conversation(self, modele: str, dossier_id: str | None, ephemere: bool):
        conv = dict(id=uuid4().hex, dossier_id=dossier_id, titre='Nouvelle discussion',
                    modele=modele, ephemere=ephemere, resume='', resume_count=0, epingle=False, position=0)
        if ephemere:
            self.ephemeral[conv['id']] = {**conv, 'messages': []}
        else:
            with self.db.session() as conn:
                conn.execute('INSERT INTO conversations (id, dossier_id, titre, modele) VALUES (?, ?, ?, ?)',
                             (conv['id'], dossier_id, conv['titre'], modele))
        return conv

    def update_conversation(self, conv_id: str, **fields):
        if set(fields) - {'titre', 'modele', 'dossier_id', 'resume', 'resume_count', 'epingle'}:
            raise ValueError('Champs de conversation inconnus.')
        if not fields:
            return
        if conv_id in self.ephemeral:
            self.ephemeral[conv_id].update(fields)
        else:
            with self.db.session() as conn:
                conn.execute('UPDATE conversations SET ' + ', '.join(f'{k} = ?' for k in fields)
                             + ', date_maj = CURRENT_TIMESTAMP WHERE id = ?', (*fields.values(), conv_id))

    def delete_conversation(self, conv_id: str):
        self.ephemeral.pop(conv_id, None)
        with self.db.session() as conn:
            conn.execute('DELETE FROM conversations WHERE id = ?', (conv_id,))

    def messages(self, conv_id: str):
        if conv_id in self.ephemeral:
            return [dict(m) for m in self.ephemeral[conv_id]['messages']]
        with self.db.session() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM messages WHERE conversation_id = ? ORDER BY id', (conv_id,))]

    def append(self, conv_id: str, role: str, contenu: str, statut: str):
        if conv_id in self.ephemeral:
            messages = self.ephemeral[conv_id]['messages']
            msg = dict(id=len(messages) + 1, conversation_id=conv_id, role=role, contenu=contenu, statut=statut, erreur='')
            messages.append(msg)
            return msg['id']
        with self.db.session() as conn:
            cursor = conn.execute('INSERT INTO messages (conversation_id, role, contenu, statut) VALUES (?, ?, ?, ?)',
                                  (conv_id, role, contenu, statut))
            conn.execute('UPDATE conversations SET date_maj = CURRENT_TIMESTAMP WHERE id = ?', (conv_id,))
            return cursor.lastrowid

    def finish(self, conv_id: str, message_id: int, contenu: str, statut: str, erreur: str = ''):
        if conv_id in self.ephemeral:
            msg = next(m for m in self.ephemeral[conv_id]['messages'] if m['id'] == message_id)
            msg.update(contenu=contenu, statut=statut, erreur=erreur)
        else:
            with self.db.session() as conn:
                conn.execute('UPDATE messages SET contenu = ?, statut = ?, erreur = ? WHERE id = ? AND conversation_id = ?',
                             (contenu, statut, erreur, message_id, conv_id))

    def history(self, conv_id: str, before_id: int):
        messages = [m for m in self.messages(conv_id) if m['id'] < before_id]
        history = []
        for index in range(0, len(messages) - 1, 2):
            user, assistant = messages[index:index + 2]
            if user['statut'] == 'termine' and assistant['statut'] in {'termine', 'arrete'} and assistant['contenu']:
                history.extend([user, assistant])
        return history
