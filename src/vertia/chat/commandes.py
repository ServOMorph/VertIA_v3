from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import stat

from vertia.chat.rgpd import anonymize_details


HELP = (
    'Commandes disponibles :\n'
    '/help : affiche cette aide locale, sans enregistrer de message.\n'
    '/write <nom_fichier> : enregistre le dernier livrable dans cette discussion.\n'
    '/rgpd <texte> ou /rgpd fichier:<nom> : anonymise localement les emails, '
    'téléphones, NIR, IBAN, cartes, IPv4, adresses et noms avec civilité. '
    'Les noms sans civilité ne sont pas détectés.'
)
EXTENSIONS = {'.md', '.txt', '.json', '.html', '.css', '.js', '.py', '.csv', '.xml', '.yaml', '.yml'}
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$',
            *(f'{prefix}{i}' for prefix in ('COM', 'LPT') for i in range(1, 10))}
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})([^\r\n]*)\r?\n', re.MULTILINE)
MAX_TEXT = 5 * 1024**2
MAX_CAPTURE = 10 * 1024**2
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def validate_name(name: str) -> str:
    if (not re.fullmatch(r'[A-Za-z0-9._ -]{1,120}', name) or '..' in name
            or name != name.strip() or name.endswith('.')
            or name.split('.')[0].rstrip().upper() in RESERVED
            or Path(name).suffix.lower() not in EXTENSIONS):
        raise ValueError('Nom de fichier invalide : nom simple, extension texte autorisée, sans nom Windows réservé ni .. .')
    return name


def last_deliverable(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message['role'] != 'assistant' or message['statut'] not in {'termine', 'arrete'}:
            continue
        text = message['contenu']
        cursor, blocks = 0, []
        while opening := FENCE.search(text, cursor):
            fence, info = opening.groups()
            closing = re.search(r'^ {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}[ \t]*\r?$',
                                text[opening.end():], re.MULTILINE)
            if not closing:
                break
            end = opening.end() + closing.start()
            if info.strip().split()[:1] == ['livrable']:
                blocks.append(text[opening.end():end].strip())
            cursor = opening.end() + closing.end()
        if blocks and blocks[-1]:
            return blocks[-1]
    raise ValueError('Aucun bloc livrable terminé dans cette conversation.')


def read_inbox(inbox: Path, name: str) -> str:
    validate_name(name)
    if Path(name).suffix.lower() not in {'.txt', '.md'}:
        raise ValueError('Le fichier inbox doit être .txt ou .md.')
    try:
        root = inbox.resolve(strict=True)
        path = inbox / name
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or path.resolve(strict=True).parent != root):
            raise ValueError('Le fichier doit être dans inbox, sans lien.')
        if info.st_size > MAX_TEXT:
            raise ValueError('Fichier supérieur à 5 Mio.')
        with path.open('rb') as stream:
            current = os.fstat(stream.fileno())
            if (current.st_ino, current.st_dev) != (info.st_ino, info.st_dev):
                raise ValueError('Le fichier inbox a changé pendant la lecture.')
            data = stream.read(MAX_TEXT + 1)
        if len(data) > MAX_TEXT:
            raise ValueError('Fichier supérieur à 5 Mio.')
        return data.decode('utf-8')
    except (OSError, UnicodeError) as exc:
        raise ValueError('Fichier inbox inaccessible ou texte UTF-8 invalide.') from exc


def save_text(store, conv_id: str, filename: str, content: str):
    save = getattr(store, 'save_text', None)
    if save is None:
        raise ValueError('L’enregistrement des livrables texte nécessite une extension de FileStore.')
    return save(conv_id, filename, content)


def execute(svc, conv_id: str, text: str) -> dict:
    parts = text.split(maxsplit=1)
    name = parts[0].lower()
    payload = parts[1] if len(parts) > 1 else ''
    if name == '/help':
        return {'local': True, 'contenu': HELP}
    if name not in {'/write', '/rgpd'}:
        raise ValueError('Commande inconnue. ' + HELP)
    if svc.chat.closed or svc.chat.busy(conv_id):
        raise ValueError('Attendez la fin des réponses de cette discussion.')
    if name == '/write':
        filename = validate_name(payload)
        content = last_deliverable(svc.chat.messages(conv_id))
        save_text(svc.files, conv_id, filename, content)
        result = f'Fichier écrit : {filename}'
        stored = text
    elif name == '/rgpd':
        if not payload:
            raise ValueError('Usage : /rgpd <texte> ou /rgpd fichier:<nom>')
        filename = None
        if payload.startswith('fichier:'):
            source = payload[len('fichier:'):]
            content = read_inbox(svc.chemins.inbox_dir, source)
            filename = validate_name(Path(source).stem + '_anonymise.md')
        else:
            content = payload
        anonymized, counts = anonymize_details(content)
        summary = ', '.join(f'{kind} : {count}' for kind, count in counts.items()) or 'aucune'
        result = f'{sum(counts.values())} donnée(s) sensible(s) remplacée(s) ({summary}).'
        if filename:
            save_text(svc.files, conv_id, filename, anonymized)
            result += f'\nFichier anonymisé écrit : {filename}'
        else:
            result += '\n\n' + anonymized
        stored = f'/rgpd [texte non conservé, {len(content)} caractères]'
    return svc.chat.local_reply(conv_id, stored, result)


def save_capture(root: Path, data: bytes) -> str:
    if len(data) > MAX_CAPTURE:
        raise ValueError('Capture supérieure à 10 Mio.')
    if not data.startswith(PNG_MAGIC):
        raise ValueError('Le contenu doit être un PNG.')
    root = root.resolve()
    folder = root / 'captures'
    folder.mkdir(parents=True, exist_ok=True)
    info = folder.lstat()
    if (not stat.S_ISDIR(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or folder.resolve().parent != root):
        raise ValueError('Dossier de captures inaccessible, sans lien requis.')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    for index in range(100):
        name = f'capture_{stamp}' + (f'_{index}' if index else '') + '.png'
        path = folder / name
        try:
            stream = path.open('xb')
        except FileExistsError:
            continue
        try:
            with stream:
                stream.write(data)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return name
    raise ValueError('Impossible de créer un nom de capture disponible.')
