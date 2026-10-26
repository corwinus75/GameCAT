"""Analiza projektu względem pamięci tłumaczeniowej (TM).

Dla każdego segmentu wyszukiwane jest najlepsze dopasowanie w TM, a wynik
jest klasyfikowany do progów stosowanych w narzędziach CAT (100%, 95–99%,
85–94%, 75–84%, 50–74%, brak dopasowania). Na tej podstawie tłumacz ocenia
nakład pracy, a program może wstawić dopasowania 100% (pretranslacja).

Porównanie każdego segmentu z każdym wpisem TM to obliczenia CPU-bound
w czystym Pythonie (``gamecat.tm.similarity``), dlatego analiza może być
wykonywana sekwencyjnie, w wątkach lub w procesach – co jest jednocześnie
podstawą benchmarku GIL (``benchmarks/gil_benchmark.py``).
"""
from __future__ import annotations

import multiprocessing
import os
import re
import time
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from functools import partial

from gamecat.tm.similarity import similarity

TMPair = tuple[str, str]
"""Wpis TM przekazywany do analizy: ``(source, target)``."""

SegmentItem = tuple[int, str]
"""Segment przekazywany do analizy: ``(segment_id, source)``."""

_WORD_RE = re.compile(r'\w+', re.UNICODE)


class ExecutionMode(StrEnum):
    SEQUENTIAL = 'sequential'
    THREADS = 'threads'
    PROCESSES = 'processes'


# (etykieta, minimalny wynik włącznie) – od najwyższego progu.
MATCH_BANDS: tuple[tuple[str, float], ...] = (
    ('100%', 1.0),
    ('95–99%', 0.95),
    ('85–94%', 0.85),
    ('75–84%', 0.75),
    ('50–74%', 0.50),
    ('Brak', 0.0),
)


def band_for(score: float) -> str:
    """Zwróć etykietę progu dla wyniku podobieństwa 0..1."""
    for label, minimum in MATCH_BANDS:
        if score >= minimum:
            return label
    return MATCH_BANDS[-1][0]


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


@dataclass(frozen=True, slots=True)
class SegmentMatch:
    """Najlepsze dopasowanie TM dla jednego segmentu."""
    segment_id: int
    words: int
    score: float
    tm_source: str | None
    tm_target: str | None

    @property
    def band(self) -> str:
        return band_for(self.score)


@dataclass(slots=True)
class TMAnalysisReport:
    """Wynik analizy projektu: dopasowania i statystyka według progów."""
    matches: list[SegmentMatch]
    mode: ExecutionMode
    workers: int
    elapsed: float
    tm_size: int
    band_segments: dict[str, int] = field(init=False)
    band_words: dict[str, int] = field(init=False)

    def __post_init__(self) -> None:
        self.band_segments = {label: 0 for label, _ in MATCH_BANDS}
        self.band_words = {label: 0 for label, _ in MATCH_BANDS}
        for match in self.matches:
            self.band_segments[match.band] += 1
            self.band_words[match.band] += match.words

    @property
    def segment_count(self) -> int:
        return len(self.matches)

    @property
    def total_words(self) -> int:
        return sum(self.band_words.values())

    def exact_matches(self) -> list[SegmentMatch]:
        return [m for m in self.matches if m.score >= 1.0 and m.tm_target is not None]


def best_match(source: str, tm: Sequence[TMPair], exact: dict[str, str] | None = None) -> tuple[float, str | None, str | None]:
    """Znajdź najlepiej pasujący wpis TM dla *source*.

    Dopasowanie dokładne jest sprawdzane słownikiem w O(1); dopiero gdy go
    nie ma, liczone jest podobieństwo fuzzy względem wszystkich wpisów.
    """
    if exact is not None and source in exact:
        return 1.0, source, exact[source]
    best: tuple[float, str | None, str | None] = (0.0, None, None)
    for tm_source, tm_target in tm:
        score = similarity(source, tm_source)
        if score > best[0]:
            best = (score, tm_source, tm_target)
            if score >= 1.0:
                break
    return best


def _match_item(item: SegmentItem, tm: Sequence[TMPair], exact: dict[str, str]) -> SegmentMatch:
    segment_id, source = item
    score, tm_source, tm_target = best_match(source, tm, exact)
    return SegmentMatch(segment_id, word_count(source), score, tm_source, tm_target)


# --- stan procesu roboczego -------------------------------------------------
# TM jest przekazywana do każdego procesu tylko raz, przez initializer puli,
# a nie z każdym zadaniem – inaczej koszt serializacji (pickle) zjadłby zysk.
_WORKER_TM: Sequence[TMPair] = ()
_WORKER_EXACT: dict[str, str] = {}


def _init_worker(tm: Sequence[TMPair]) -> None:
    global _WORKER_TM, _WORKER_EXACT
    _WORKER_TM = tm
    _WORKER_EXACT = _exact_index(tm)


def _match_item_in_worker(item: SegmentItem) -> SegmentMatch:
    return _match_item(item, _WORKER_TM, _WORKER_EXACT)


def _exact_index(tm: Iterable[TMPair]) -> dict[str, str]:
    index: dict[str, str] = {}
    for source, target in tm:
        index.setdefault(source, target)  # pierwszy wpis wygrywa
    return index


def default_workers() -> int:
    return os.cpu_count() or 1


def analyze(
    segments: Iterable[SegmentItem],
    tm: Sequence[TMPair],
    mode: ExecutionMode | str = ExecutionMode.PROCESSES,
    workers: int | None = None,
    min_parallel: int = 0,
) -> TMAnalysisReport:
    """Przeanalizuj segmenty względem TM w wybranym trybie wykonania.

    :param segments: pary ``(segment_id, source)``; może to być generator.
    :param tm: wpisy TM jako pary ``(source, target)``.
    :param mode: ``sequential``, ``threads`` albo ``processes``.
    :param workers: liczba wątków/procesów (domyślnie liczba rdzeni).
    :param min_parallel: poniżej tej liczby segmentów analiza idzie
        sekwencyjnie – start puli procesów kosztuje więcej niż sama praca.
    """
    mode = ExecutionMode(mode)
    items = list(segments)
    tm = list(tm)
    worker_count = max(1, workers or default_workers())
    if not tm or len(items) < min_parallel:
        mode = ExecutionMode.SEQUENTIAL
    if mode is ExecutionMode.SEQUENTIAL:
        worker_count = 1

    start = time.perf_counter()
    if mode is ExecutionMode.SEQUENTIAL:
        exact = _exact_index(tm)
        matches = [_match_item(item, tm, exact) for item in items]
    elif mode is ExecutionMode.THREADS:
        exact = _exact_index(tm)
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix='gamecat-tm') as pool:
            matches = list(pool.map(partial(_match_item, tm=tm, exact=exact), items))
    else:
        # 'spawn' na wszystkich systemach: identyczne zachowanie jak na Windows
        # i brak ryzyka forka procesu, który ma już działające wątki (GUI, autosave).
        context = multiprocessing.get_context('spawn')
        chunksize = max(1, len(items) // (worker_count * 4))
        with ProcessPoolExecutor(max_workers=worker_count, mp_context=context,
                                 initializer=_init_worker, initargs=(tm,)) as pool:
            matches = list(pool.map(_match_item_in_worker, items, chunksize=chunksize))
    elapsed = time.perf_counter() - start
    return TMAnalysisReport(matches, mode, worker_count, elapsed, len(tm))
