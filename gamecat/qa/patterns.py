"""Wyrażenia regularne do wykrywania placeholderów i tagów.

``BRACE_RE`` i ``PRINTF_OR_TAG_RE`` używają grup nazwanych (``brace``,
``printf``, ``tag``) – nazwa dopasowanej grupy określa rodzaj tokenu.
"""
from dataclasses import dataclass
import re

BRACE_RE = re.compile(r'(?P<brace>\{(?:g|d|mf)\|[^{}]*\}|\{[^{}]+\})')
PRINTF_OR_TAG_RE = re.compile(r'(?P<printf>%\d*\$?[sdif])|(?P<tag></?[^<>]+?>)')

@dataclass(frozen=True, slots=True)
class QAToken:
    """Token lokalizacyjny znaleziony w tekście: rodzaj (nazwa grupy regex) i wartość."""
    kind: str
    value: str


def extract_tokens(text: str) -> list[QAToken]:
    """Wyodrębnij placeholdery i znaczniki w kolejności występowania, korzystając z grup nazwanych."""
    found: list[tuple[int, QAToken]] = []
    for pattern in (BRACE_RE, PRINTF_OR_TAG_RE):
        for match in pattern.finditer(text):
            kind = match.lastgroup or 'token'
            found.append((match.start(), QAToken(kind, match.group(0))))
    found.sort(key=lambda item: item[0])
    return [item[1] for item in found]
