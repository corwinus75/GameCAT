from __future__ import annotations

import re


def contains_term(text: str, term: str, *, case_sensitive: bool = False) -> bool:
    """Return whether *term* occurs as a complete literal word/phrase in *text*.

    Regex boundaries are applied only when the corresponding edge of the term
    is word-like, so punctuation-heavy localization terms such as ``C++`` and
    ``+1 sword`` remain matchable.
    """
    needle = term.strip()
    if not needle:
        return False
    prefix = r"(?<!\w)" if needle[0].isalnum() or needle[0] == "_" else ""
    suffix = r"(?!\w)" if needle[-1].isalnum() or needle[-1] == "_" else ""
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.search(prefix + re.escape(needle) + suffix, text, flags) is not None
