"""Wyszukiwanie terminów glosariusza w tekście."""
from __future__ import annotations

import re


def contains_term(text: str, term: str, *, case_sensitive: bool = False) -> bool:
    """Sprawdź, czy *term* występuje w *text* jako pełne słowo lub fraza.

    Granice słowa (regex) są stosowane tylko przy krawędziach terminu
    złożonych ze znaków słownych, dzięki czemu terminy z interpunkcją, np.
    ``C++`` lub ``+1 sword``, nadal są wykrywane.
    """
    needle = term.strip()
    if not needle:
        return False
    prefix = r"(?<!\w)" if needle[0].isalnum() or needle[0] == "_" else ""
    suffix = r"(?!\w)" if needle[-1].isalnum() or needle[-1] == "_" else ""
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.search(prefix + re.escape(needle) + suffix, text, flags) is not None
