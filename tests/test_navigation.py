from vertia.chat.repository import ChatRepository
from vertia.core.db import MIGRATIONS, Database


def test_navigation_pin_move_order_persist(client, settings):
    folders = [client.post('/api/dossiers', json={'nom': name}).json() for name in ('Alpha', 'Beta')]
    conversations = [client.post('/api/conversations', json={'modele': 'fake', 'dossier_id': folders[0]['id']}).json() for _ in range(2)]
    path = '/api/conversations/' + conversations[0]['id']
    response = client.patch(path, json={'titre': 'Titre modifié', 'epingle': True, 'dossier_id': folders[1]['id']})
    assert response.status_code == 200
    assert response.json()['dossier_id'] == folders[1]['id']
    assert client.patch('/api/dossiers/' + folders[1]['id'], json={'epingle': True}).status_code == 200
    ids = [c['id'] for c in reversed(conversations)]
    assert client.put('/api/navigation/ordre', json={'type': 'conversations', 'ids': ids}).status_code == 200
    repo = ChatRepository(Database(settings.database))
    assert repo.folders()[0]['id'] == folders[1]['id']
    assert repo.conversations()[0]['titre'] == 'Titre modifié'
    client.patch(path, json={'epingle': False})
    assert [c['id'] for c in repo.conversations()] == ids
    assert client.delete('/api/dossiers/' + folders[1]['id']).status_code == 200
    assert repo.conversation(conversations[0]['id'])['dossier_id'] is None
    assert repo.conversation(conversations[0]['id'])['titre'] == 'Titre modifié'


def test_navigation_ephemeral_order_does_not_persist(client, settings):
    ids = [client.post('/api/conversations', json={'ephemere': True}).json()['id'] for _ in range(2)]
    assert client.patch('/api/conversations/' + ids[0], json={'epingle': True}).status_code == 200
    assert client.put('/api/navigation/ordre', json={'type': 'conversations', 'ids': ids[::-1]}).status_code == 200
    assert client.patch('/api/conversations/' + ids[0], json={'epingle': False}).status_code == 200
    assert [c['id'] for c in client.get('/api/conversations').json()] == ids[::-1]
    assert ChatRepository(Database(settings.database)).conversations() == []


def test_navigation_rejects_invalid_changes_atomically(client):
    folder = client.post('/api/dossiers', json={'nom': 'Initial'}).json()
    conv = client.post('/api/conversations', json={}).json()
    path = '/api/conversations/' + conv['id']
    for fields, code in [({'titre': ' '}, 422), ({'titre': None}, 422), ({'epingle': None}, 422),
                         ({'dossier_id': 'absent'}, 404)]:
        assert client.patch(path, json=fields).status_code == code
    assert client.patch('/api/dossiers/absent', json={'epingle': True}).status_code == 404
    for ids in [[conv['id'], 'absent'], [conv['id'], conv['id']]]:
        assert client.put('/api/navigation/ordre', json={'type': 'conversations', 'ids': ids}).status_code == 422
    assert client.get(path).json()['position'] == 0
    assert client.put('/api/navigation/ordre', json={'type': 'messages', 'ids': []}).status_code == 422
    assert client.patch(path, json={'dossier_id': folder['id']}).status_code == 200
    assert client.patch(path, json={'dossier_id': None}).json()['dossier_id'] is None


def test_navigation_migrates_existing_database(tmp_path):
    db = Database(tmp_path / 'old.db')
    with db.session() as conn:
        for migration in MIGRATIONS[:-1]:
            conn.executescript(migration)
        conn.execute(f'PRAGMA user_version = {len(MIGRATIONS) - 1}')
        conn.execute("INSERT INTO dossiers VALUES ('f', 'Ancien', 'Instructions')")
        conn.execute("INSERT INTO conversations (id, dossier_id, titre, modele) VALUES ('c', 'f', 'Conservé', 'fake')")
    db.initialize()
    repo = ChatRepository(db)
    assert repo.folder('f')['system_prompt'] == 'Instructions'
    assert repo.conversation('c')['titre'] == 'Conservé'
    assert repo.conversation('c')['epingle'] == 0


def test_frontend_revalidates_modules(client):
    assert client.get('/').headers['cache-control'] == 'no-cache'
    assert client.get('/static/js/setup.js').headers['cache-control'] == 'no-cache'


def test_navigation_blocks_move_and_folder_delete_during_tool_job(client, app, monkeypatch):
    folder = client.post('/api/dossiers', json={'nom': 'En cours'}).json()
    conv = client.post('/api/conversations', json={'dossier_id': folder['id']}).json()
    monkeypatch.setattr(app.state.services.actions, 'busy', lambda conv_id: conv_id == conv['id'])
    path = '/api/conversations/' + conv['id']
    assert client.patch(path, json={'dossier_id': None}).status_code == 409
    assert client.delete('/api/dossiers/' + folder['id']).status_code == 409
    assert client.get(path).json()['dossier_id'] == folder['id']
    assert client.patch(path, json={'epingle': True}).status_code == 200
