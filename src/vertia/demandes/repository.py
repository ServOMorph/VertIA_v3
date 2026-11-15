from __future__ import annotations

import json
from uuid import uuid4


class DemandesRepository:
    def __init__(self, db):
        self.db = db

    def get(self, demande_id):
        with self.db.session() as conn:
            row = conn.execute('SELECT * FROM demandes WHERE id=?', (demande_id,)).fetchone()
            if row is None:
                raise LookupError('Demande introuvable.')
            result = dict(row)
            result['params'] = json.loads(result['params'])
            result['analyse_requise'] = bool(result['analyse_requise'])
            result['essais'] = [dict(row) for row in conn.execute(
                'SELECT * FROM essais WHERE demande_id=? ORDER BY numero', (demande_id,))]
            result['retours'] = [dict(row) for row in conn.execute(
                'SELECT * FROM retours WHERE demande_id=? ORDER BY id', (demande_id,))]
        for essai in result['essais']:
            for key in ('params', 'chemins'):
                essai[key] = json.loads(essai[key])
        result['chemins'] = result['essais'][-1]['chemins'] if result['essais'] else []
        return result

    def create(self, session, capacite, params, critere, essais_max):
        demande_id = uuid4().hex
        with self.db.session() as conn:
            nouvelle = not conn.execute('SELECT 1 FROM demandes WHERE session=? AND capacite=?',
                                        (session, capacite)).fetchone()
            conn.execute('INSERT INTO demandes(id,session,capacite,params,critere,essais_max,analyse_requise) '
                         'VALUES(?,?,?,?,?,?,?)', (demande_id, session, capacite,
                         json.dumps(params, ensure_ascii=False), critere, essais_max, int(nouvelle)))
        return demande_id

    def update(self, demande_id, **values):
        if not values or not values.keys() <= {'etat', 'analyse_requise', 'motif_code', 'erreur'}:
            raise ValueError('Mise à jour de demande invalide.')
        with self.db.session() as conn:
            conn.execute('UPDATE demandes SET ' + ','.join(f'{key}=?' for key in values)
                         + ',updated=CURRENT_TIMESTAMP WHERE id=?', (*values.values(), demande_id))

    def essai(self, demande_id, numero, **values):
        if not values or not values.keys() <= {'job_id', 'etat', 'chemins', 'duree'}:
            raise ValueError('Mise à jour d’essai invalide.')
        if 'chemins' in values:
            values['chemins'] = json.dumps(values['chemins'], ensure_ascii=False)
        with self.db.session() as conn:
            conn.execute('UPDATE essais SET ' + ','.join(f'{key}=?' for key in values)
                         + ' WHERE demande_id=? AND numero=?', (*values.values(), demande_id, numero))

    def add_essai(self, demande_id, params, module, motif):
        with self.db.session() as conn:
            numero = conn.execute('SELECT COUNT(*) FROM essais WHERE demande_id=?', (demande_id,)).fetchone()[0] + 1
            conn.execute('INSERT INTO essais(demande_id,numero,params,module,version,motif) VALUES(?,?,?,?,?,?)',
                         (demande_id, numero, json.dumps(params, ensure_ascii=False), module.nom, module.version, motif))
        return numero

    def retour(self, demande_id, numero, verdict, motif):
        with self.db.session() as conn:
            conn.execute('INSERT INTO retours(demande_id,numero,verdict,motif) VALUES(?,?,?,?)',
                         (demande_id, numero, verdict, motif))
