"""Deterministyczny generator danych testowych dla benchmarku analizy TM.

Tworzy zdania przypominające teksty z gier RPG oraz pamięć tłumaczeniową,
w której część wpisów pokrywa się z segmentami dokładnie, część jest do
nich podobna (zmienione pojedyncze słowa), a reszta jest niezwiązana.
"""
from __future__ import annotations

import random
from collections.abc import Iterator

SUBJECTS = ['The old gate', 'A rusty key', 'The village elder', 'Your companion', 'The dark crypt',
            'A hooded stranger', 'The ancient sword', 'The merchant', 'A wounded soldier', 'The tower guard']
VERBS = ['is waiting near', 'was found inside', 'leads to', 'protects', 'was stolen from',
         'can be opened in', 'hides beneath', 'points toward', 'has vanished from', 'guards']
OBJECTS = ['the northern bridge', 'the abandoned mine', 'the royal library', 'the forest shrine',
           'the harbour warehouse', 'the castle dungeon', 'the mountain pass', 'the temple ruins',
           'the old windmill', 'the thieves guild']
TAILS = ['', ' before nightfall', ' after the storm', ' since the last war', ' according to the map',
         ' as the legend says', ' if you hurry', ' for many years']
SWAPS = {'old': 'ancient', 'rusty': 'broken', 'dark': 'gloomy', 'near': 'beside', 'waiting': 'standing',
         'found': 'hidden', 'royal': 'great', 'forest': 'woodland', 'mountain': 'high', 'castle': 'fortress'}


def _sentence(rng: random.Random) -> str:
    return f'{rng.choice(SUBJECTS)} {rng.choice(VERBS)} {rng.choice(OBJECTS)}{rng.choice(TAILS)}.'


def _mutate(sentence: str, rng: random.Random) -> str:
    words = sentence.split()
    candidates = [i for i, w in enumerate(words) if w.strip('.') in SWAPS]
    if not candidates:
        return sentence[:-1] + ' again.'
    i = rng.choice(candidates)
    word = words[i].strip('.')
    words[i] = words[i].replace(word, SWAPS[word])
    return ' '.join(words)


def _sentences(rng: random.Random) -> Iterator[str]:
    """Nieskończony generator zdań."""
    while True:
        yield _sentence(rng)


def generate_dataset(
    n_segments: int,
    n_tm: int,
    seed: int = 2026,
    exact_ratio: float = 0.2,
    fuzzy_ratio: float = 0.4,
) -> tuple[list[tuple[int, str]], list[tuple[str, str]]]:
    """Zwróć ``(segments, tm)`` – segmenty jako ``(id, source)``, TM jako ``(source, target)``."""
    rng = random.Random(seed)
    stream = _sentences(rng)
    tm_sources = [next(stream) for _ in range(n_tm)]
    tm = [(source, f'[PL] {source}') for source in tm_sources]

    segments: list[tuple[int, str]] = []
    for segment_id in range(1, n_segments + 1):
        roll = rng.random()
        if tm_sources and roll < exact_ratio:
            source = rng.choice(tm_sources)
        elif tm_sources and roll < exact_ratio + fuzzy_ratio:
            source = _mutate(rng.choice(tm_sources), rng)
        else:
            source = next(stream) + f' #{segment_id}'
        segments.append((segment_id, source))
    return segments, tm
