from __future__ import annotations

import ipaddress
import re
from typing import Callable


SENSITIVE_PLACEHOLDER = "[DONNÉE_SENSIBLE]"

EMAIL_PATTERN = re.compile(
    r"[\w.+-]+(?:@|＠)[\w-]+(?:(?:\.|．)[\w-]+)+",
    re.IGNORECASE,
)
IBAN_CANDIDATE_PATTERN = re.compile(
    r"(?<![A-Z0-9])[A-Z]{2}\d{2}"
    r"(?:[ \u00a0\u200b-\u200d\ufeff]*[A-Z0-9]){11,30}"
    r"(?![A-Z0-9])",
    re.IGNORECASE | re.ASCII,
)
CARD_PATTERN = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
ADDRESS_WITH_CITY_PATTERN = re.compile(
    r"\b\d{1,4}\s?(?:(?i:bis|ter))?,?\s+"
    r"(?i:rue|avenue|av\.|boulevard|bd|impasse|allée|allee|chemin|place|quai)"
    r"\s+[^,\n.;]+,\s*\d{5}\s+"
    r"[A-ZÀ-Ý][\w'’-]*(?:[ -][A-ZÀ-Ý][\w'’-]*){0,3}",
)
NIR_PATTERN = re.compile(
    r"\b[12]\s?\d{2}\s?(?:0[1-9]|1[0-2])\s?\d{2}\s?\d{3}\s?\d{3}"
    r"(?:\s?\d{2})?\b"
)
PHONE_PATTERN = re.compile(r"(?:\+33\s?|\b0)[1-9](?:[\s.-]?\d{2}){4}\b")
ADDRESS_PATTERN = re.compile(
    r"\b\d{1,4}\s?(?:bis|ter)?,?\s+"
    r"(?:rue|avenue|av\.|boulevard|bd|impasse|allée|allee|chemin|place|quai)"
    r"\s+[^,\n.;]+",
    re.IGNORECASE,
)
NAME_PATTERN = re.compile(
    r"\b(?:M\.|Mr|Mme|Mlle|Dr|Me)\s+[A-ZÀ-Ý][\w'’-]+"
    r"(?:\s+[A-ZÀ-Ý][\w'’-]+)?"
)

SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    EMAIL_PATTERN,
    NIR_PATTERN,
    PHONE_PATTERN,
    ADDRESS_WITH_CITY_PATTERN,
    ADDRESS_PATTERN,
    NAME_PATTERN,
]


def _compact_iban(value: str) -> str:
    return re.sub(r"[ \u00a0\u200b-\u200d\ufeff]", "", value).upper()


def _is_valid_iban(value: str) -> bool:
    compact = _compact_iban(value)
    if not re.fullmatch(
        r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact, flags=re.ASCII
    ):
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(
        str(ord(character) - ord("A") + 10) if character.isalpha() else character
        for character in rearranged
    )
    return int(numeric) % 97 == 1


def _replace_iban_candidates(text: str) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        candidate = match.group(0)
        alphanumeric_positions = [
            index + 1 for index, character in enumerate(candidate) if character.isalnum()
        ]
        for compact_length in range(min(34, len(alphanumeric_positions)), 14, -1):
            end = alphanumeric_positions[compact_length - 1]
            prefix = candidate[:end]
            if _is_valid_iban(prefix):
                count += 1
                return SENSITIVE_PLACEHOLDER + candidate[end:]
        return candidate

    return IBAN_CANDIDATE_PATTERN.sub(replace, text), count


def _passes_luhn(value: str) -> bool:
    digits = [int(character) for character in value if character.isdigit()]
    if len(digits) != 16:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _is_valid_ipv4(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).version == 4
    except ValueError:
        return False


def _replace_validated(
    text: str,
    pattern: re.Pattern[str],
    validator: Callable[[str], bool],
) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        value = match.group(0)
        if not validator(value):
            return value
        count += 1
        return SENSITIVE_PLACEHOLDER

    return pattern.sub(replace, text), count


def anonymize_details(text: str) -> tuple[str, dict[str, int]]:
    counts = {}

    def record(kind, result):
        nonlocal text
        text, count = result
        if count:
            counts[kind] = counts.get(kind, 0) + count

    record('email', EMAIL_PATTERN.subn(SENSITIVE_PLACEHOLDER, text))
    record('iban', _replace_iban_candidates(text))
    for kind, pattern in (('nir', NIR_PATTERN), ('telephone', PHONE_PATTERN)):
        record(kind, pattern.subn(SENSITIVE_PLACEHOLDER, text))
    record('carte', _replace_validated(text, CARD_PATTERN, _passes_luhn))
    record('ip', _replace_validated(text, IPV4_PATTERN, _is_valid_ipv4))
    for kind, pattern in (('adresse', ADDRESS_WITH_CITY_PATTERN),
                          ('adresse', ADDRESS_PATTERN), ('nom', NAME_PATTERN)):
        record(kind, pattern.subn(SENSITIVE_PLACEHOLDER, text))
    return text, counts


def anonymize_text(text: str) -> tuple[str, int]:
    text, counts = anonymize_details(text)
    return text, sum(counts.values())
