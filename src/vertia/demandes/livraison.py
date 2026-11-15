from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def horodatage():
    return datetime.now(timezone.utc).isoformat()


class Livraison:
    def __init__(self, outbox: Path):
        self.outbox = Path(outbox)

    def journal(self, demande_id, evenement, **details):
        self.outbox.mkdir(parents=True, exist_ok=True)
        with (self.outbox / 'journal.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(id=demande_id, evenement=evenement,
                                        horodatage=horodatage(), **details), ensure_ascii=False) + '\n')

    def livrer(self, demande, numero, fichiers, travail, module, duree):
        if not fichiers:
            raise ValueError('Le moteur n’a produit aucun fichier.')
        sources = [Path(path).resolve() for path in fichiers]
        if any(not path.is_relative_to(travail.resolve()) or not path.is_file() for path in sources):
            raise ValueError('Fichier produit hors du dossier de travail.')
        dossier = self.outbox / demande['session'] / demande['id']
        dossier.mkdir(parents=True, exist_ok=True)
        chemins = []
        for index, source in enumerate(sources, 1):
            suffixe = '' if len(sources) == 1 else f'_{index}'
            # Le fichier JSON est réservé aux métadonnées de l’essai.
            if source.suffix.lower() == '.json' and not suffixe:
                suffixe = '_1'
            cible = dossier / f'essai_{numero}{suffixe}{source.suffix}'
            shutil.copyfile(source, cible)
            chemins.append(str(cible.resolve()))
        metadata = dict(capacite=demande['capacite'], params=demande['params'],
                        module=module.nom, version=module.version, duree=duree,
                        horodatage=horodatage(), modele=demande['params'].get('modele'),
                        seed=demande['params'].get('seed'), chemins=chemins)
        (dossier / f'essai_{numero}.json').write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        return chemins
