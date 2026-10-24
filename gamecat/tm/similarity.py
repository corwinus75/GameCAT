import re

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.casefold())


def _bigrams(tokens: list[str]) -> set[tuple[str, str]]:
    return set(zip(tokens, tokens[1:]))


def similarity(source: str, candidate: str) -> float:
    """Pure-Python token/ngram similarity in the 0..1 range."""
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
