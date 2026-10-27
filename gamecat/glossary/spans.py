"""Wyznaczanie nienakładających się wystąpień terminów glosariusza w Source."""
from __future__ import annotations

import re

from gamecat.models.glossary import GlossaryTerm


def term_spans(text: str, terms: list[GlossaryTerm]) -> list[tuple[int, int, GlossaryTerm]]:
    """Zwróć zakresy (indeksy napisu) terminów do podkreślenia w Source.

    Dłuższe frazy mają pierwszeństwo przed krótszymi, nakładającymi się
    terminami; granice słów działają tak samo jak w :func:`contains_term`.
    """
    result: list[tuple[int, int, GlossaryTerm]] = []
    occupied = [False] * len(text)
    for term in sorted(terms, key=lambda t: len(t.source_term), reverse=True):
        needle = term.source_term.strip()
        if not needle or not term.targets:
            continue
        prefix = r'(?<!\w)' if needle[0].isalnum() or needle[0] == '_' else ''
        suffix = r'(?!\w)' if needle[-1].isalnum() or needle[-1] == '_' else ''
        pattern = prefix + re.escape(needle) + suffix
        for match in re.finditer(pattern, text, 0 if term.case_sensitive else re.IGNORECASE):
            start, end = match.span()
            if any(occupied[start:end]):
                continue
            occupied[start:end] = [True] * (end - start)
            result.append((start, end, term))
    return sorted(result, key=lambda span: span[0])
