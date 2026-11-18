from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


FORMATS = {
    'image/png': ('image', '.png'), 'image/jpeg': ('image', '.jpg'),
    'image/webp': ('image', '.webp'), 'audio/mpeg': ('audio', '.mp3'),
    'audio/wav': ('audio', '.wav'), 'audio/ogg': ('audio', '.ogg'),
    'video/mp4': ('video', '.mp4'), 'video/webm': ('video', '.webm'),
}
MAX_BYTES = 256 * 1024**2
TEXT_FORMATS = {
    '.md': 'text/markdown', '.txt': 'text/plain', '.json': 'application/json', '.html': 'text/html',
    '.css': 'text/css', '.js': 'text/javascript', '.py': 'text/x-python', '.csv': 'text/csv',
    '.xml': 'application/xml', '.yaml': 'application/yaml', '.yml': 'application/yaml',
}


class FileStore:
    def __init__(self, db, repository, root, events):
        self.db, self.repository, self.events = db, repository, events
        self.root = Path(root).resolve()
        self.ephemeral = {}

    def get(self, file_id):
        if file_id in self.ephemeral:
            return dict(self.ephemeral[file_id][0])
        with self.db.session() as conn:
            row = conn.execute('SELECT * FROM fichiers WHERE id=?', (file_id,)).fetchone()
        if row is None:
            raise LookupError('Fichier introuvable.')
        return dict(row, parameters=json.loads(row['parameters']))

    def list(self, conv_id):
        with self.db.session() as conn:
            ids = [r[0] for r in conn.execute('SELECT id FROM fichiers WHERE conversation_id=? ORDER BY rowid', (conv_id,))]
        ids += [key for key, (meta, _) in self.ephemeral.items() if meta['conversation_id'] == conv_id]
        return [self.get(key) for key in ids]

    def directory(self, conv_id):
        # Identifiants internes uniquement ; aucune route ne reçoit un chemin disque.
        if len(conv_id) != 32 or any(c not in '0123456789abcdef' for c in conv_id):
            raise ValueError('Identifiant de conversation invalide.')
        path = (self.root / conv_id).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError('Dossier inaccessible.')
        return path

    def path(self, meta):
        folder = self.directory(meta['conversation_id'])
        path = (folder / meta['name']).resolve()
        if not path.is_relative_to(folder) or path == folder:
            raise ValueError('Fichier inaccessible.')
        return path

    def read(self, file_id):
        meta = self.get(file_id)
        if file_id in self.ephemeral:
            return self.ephemeral[file_id][1], meta['mime']
        path = self.path(meta)
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('Fichier trop volumineux.')
        return path.read_bytes(), meta['mime']

    def save(self, action, job_id, artifacts):
        conv_id = action['conversation_id']
        conv = self.repository.conversation(conv_id)
        if conv is None:
            raise LookupError('Conversation introuvable.')
        prepared = []
        for data, mime in artifacts:
            mime = mime.split(';')[0].strip()
            if mime not in FORMATS or not data or len(data) > MAX_BYTES:
                raise ValueError('Format ou taille du résultat invalide.')
            kind, suffix = FORMATS[mime]
            file_id = uuid4().hex
            meta = dict(id=file_id, conversation_id=conv_id, action_id=action['id'],
                        job_id=job_id, type=kind, mime=mime, name=file_id + suffix,
                        size=len(data), prompt=action['parameters'].get('prompt', ''),
                        parameters=action['parameters'])
            prepared.append((meta, data))
        written = []
        try:
            if conv['ephemere']:
                self.ephemeral.update({m['id']: (m, d) for m, d in prepared})
            else:
                with self.db.session() as conn:
                    for meta, data in prepared:
                        path = self.path(meta)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with path.open('xb') as target:
                            written.append(path)
                            target.write(data)
                        conn.execute('INSERT INTO fichiers(id,conversation_id,action_id,job_id,type,mime,name,size,prompt,parameters) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                     tuple(meta[k] for k in ('id', 'conversation_id', 'action_id', 'job_id', 'type', 'mime', 'name', 'size', 'prompt')) + (json.dumps(meta['parameters'], ensure_ascii=False),))
        except BaseException:
            for path in written:
                path.unlink(missing_ok=True)
            raise
        self.events.publish('fichiers.maj', {'conversation_id': conv_id})
        return [m['id'] for m, _ in prepared]

    def save_text(self, conv_id, filename, content):
        conv = self.repository.conversation(conv_id)
        if conv is None:
            raise LookupError('Conversation introuvable.')
        data = content.encode('utf-8')
        if not data or len(data) > MAX_BYTES:
            raise ValueError('Contenu vide ou trop volumineux.')
        mime = TEXT_FORMATS.get(Path(filename).suffix.lower())
        if mime is None:
            raise ValueError('Extension de fichier texte non autorisée.')
        meta = dict(id=uuid4().hex, conversation_id=conv_id, action_id='commande', job_id='commande',
                    type='texte', mime=mime, name=filename, size=len(data), prompt=filename, parameters={})
        if conv['ephemere']:
            if any(m['conversation_id'] == conv_id and m['name'] == filename for m, _ in self.ephemeral.values()):
                raise ValueError('Ce fichier existe déjà.')
            self.ephemeral[meta['id']] = (meta, data)
        else:
            path = self.path(meta)
            if path.parent != self.directory(conv_id):
                raise ValueError('Nom de fichier invalide.')
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                target = path.open('xb')
            except FileExistsError as exc:
                raise ValueError('Ce fichier existe déjà.') from exc
            try:
                with target:
                    target.write(data)
                with self.db.session() as conn:
                    conn.execute('INSERT INTO fichiers(id,conversation_id,action_id,job_id,type,mime,name,size,prompt,parameters) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                 tuple(meta[k] for k in ('id', 'conversation_id', 'action_id', 'job_id', 'type', 'mime', 'name', 'size', 'prompt')) + ('{}',))
            except BaseException:
                path.unlink(missing_ok=True)
                raise
        self.events.publish('fichiers.maj', {'conversation_id': conv_id})
        return meta['id']

    def references(self, conv_id, ids, kind=None):
        if len(ids) > 3 or len(set(ids)) != len(ids):
            raise ValueError('Sélectionnez au maximum trois fichiers distincts.')
        result = [self.get(key) for key in ids]
        if any(m['conversation_id'] != conv_id or kind and m['type'] != kind for m in result):
            raise ValueError('Pièce jointe étrangère à cette discussion ou de type incompatible.')
        return result

    def message(self, conv_id, ids):
        refs = self.references(conv_id, ids)
        return ''.join(f"\n[Fichier {m['id']} | {m['type']} | origine : {' '.join(m['prompt'].split())[:160]}]" for m in refs)

    def forget(self, conv_id):
        for meta in self.list(conv_id):
            if meta['id'] not in self.ephemeral:
                self.path(meta).unlink(missing_ok=True)
        folder = self.directory(conv_id)
        if folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
        for key in [k for k, (m, _) in self.ephemeral.items() if m['conversation_id'] == conv_id]:
            del self.ephemeral[key]
