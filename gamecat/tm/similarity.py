"""Miara podobieństwa tekstów w czystym Pythonie (obliczenia CPU-bound)."""
import re

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    """Podziel tekst na słowa wyrażeniem regularnym, bez rozróżniania wielkości liter."""
    return _WORD_RE.findall(text.casefold())


def _bigrams(tokens: list[str]) -> set[tuple[str, str]]:
    """Zwróć zbiór par sąsiednich słów (bigramów)."""
    return set(zip(tokens, tokens[1:]))


def similarity(source: str, candidate: str) -> float:
    """Oblicz podobieństwo tekstów w zakresie 0..1.

    Łączy współczynnik Dice’a dla słów (55%), dla bigramów (35%) i stosunek
    długości (10%); identyczne teksty dają 1.0.
    """
    if source == candidate:
        return 1.0
    a, b = _tokens(source), _tokens(candidate)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    token_score = 2 * len(sa & sb) / (len(sa) + len(sb))
    ba, bb = _bigrams(a), _bigrams(b)
    if ba or bb:
        bigram_score = 2 * len(ba & bb) / (len(ba) + len(bb)) if (len(ba) + len(bb)) else 0.0
    else:
        bigram_score = token_score
    length_score = min(len(source), len(candidate)) / max(len(source), len(candidate))
    return max(0.0, min(1.0, 0.55 * token_score + 0.35 * bigram_score + 0.10 * length_score))
