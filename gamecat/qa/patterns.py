from dataclasses import dataclass
import re

BRACE_RE = re.compile(r'(?P<brace>\{(?:g|d|mf)\|[^{}]*\}|\{[^{}]+\})')
PRINTF_OR_TAG_RE = re.compile(r'(?P<printf>%\d*\$?[sdif])|(?P<tag></?[^<>]+?>)')

@dataclass(frozen=True, slots=True)
class QAToken:
    kind: str
    value: str


def extract_tokens(text: str) -> list[QAToken]:
    """Extract placeholders and markup using named regex groups."""
    found: list[tuple[int, QAToken]] = []
    for pattern in (BRACE_RE, PRINTF_OR_TAG_RE):
        for match in pattern.finditer(text):
            kind = match.lastgroup or 'token'
            found.append((match.start(), QAToken(kind, match.group(0))))
    found.sort(key=lambda item: item[0])
    return [item[1] for item in found]
