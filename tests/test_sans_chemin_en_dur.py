from pathlib import Path
import re


def test_sans_chemin_windows_en_dur():
    root = Path(__file__).resolve().parents[1]
    interdits = []
    for folder in ('src', 'modules'):
        for path in (root / folder).rglob('*.py'):
            relative = path.relative_to(root)
            if folder == 'modules' and 'tests' in relative.parts:
                continue
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if re.search(r'[CD]:\\', line, re.IGNORECASE):
                    interdits.append(f'{relative}:{number}')
    assert not interdits, '\n'.join(interdits)
