"""Czyste (bez Qt) wyszukiwanie, sortowanie i podgląd masowej zamiany Target."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Collection
import re

from gamecat.models.segment import Segment, SegmentStatus


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Parametry wyszukiwania: fraza, zakres, regex, filtry statusu i jakości oraz sortowanie."""
    phrase: str = ''
    scope: str = 'both'  # both, source, target
    regex: bool = False
    case_sensitive: bool = False
    status: str = 'ALL'
    quality: str = 'all'  # all, untranslated, qa_errors, tm_match
    sort: str = 'position'  # position, source, status
    descending: bool = False


@dataclass(frozen=True, slots=True)
class TargetReplacement:
    """Proponowana zmiana Target jednego segmentu wraz z liczbą zamienionych wystąpień."""
    segment_id: int
    source: str
    original: str
    target: str
    occurrences: int


def _regex(text: str, regex: bool, case_sensitive: bool) -> re.Pattern[str]:
    """Skompiluj wzorzec wyszukiwania (dosłowny tekst jest escapowany).

    :raises ValueError: nieprawidłowe wyrażenie regularne.
    """
    try:
        return re.compile(text if regex else re.escape(text), 0 if case_sensitive else re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f'Invalid search regex: {exc}') from exc


def filter_segments(
    segments: Iterable[Segment],
    query: SearchQuery,
    *,
    qa_error_ids: Collection[int] = (),
    tm_match_ids: Collection[int] = (),
) -> list[Segment]:
    """Zwróć segmenty spełniające kryteria zapytania, posortowane zgodnie z nim.

    :raises ValueError: nieprawidłowy zakres, sortowanie, filtr lub regex.
    """
    if query.scope not in {'both', 'source', 'target'}:
        raise ValueError('Invalid search scope')
    if query.sort not in {'position', 'source', 'status'}:
        raise ValueError('Invalid sort mode')
    if query.quality not in {'all', 'untranslated', 'qa_errors', 'tm_match'}:
        raise ValueError('Invalid quality filter')
    if query.status not in {'ALL', *[status.value for status in SegmentStatus]}:
        raise ValueError('Invalid status filter')

    matcher = _regex(query.phrase, query.regex, query.case_sensitive) if query.phrase else None
    qa_ids, tm_ids = set(qa_error_ids), set(tm_match_ids)

    def included(segment: Segment) -> bool:
        if query.status != 'ALL' and segment.status.value != query.status:
            return False
        if query.quality == 'untranslated' and segment.target.strip():
            return False
        if query.quality == 'qa_errors' and segment.id not in qa_ids:
            return False
        if query.quality == 'tm_match' and segment.id not in tm_ids:
            return False
        if matcher is None:
            return True
        fields = ([segment.source] if query.scope == 'source'
                  else [segment.target] if query.scope == 'target'
                  else [segment.source, segment.target])
        return any(matcher.search(value) for value in fields)

    status_order = {status: index for index, status in enumerate(SegmentStatus)}
    if query.sort == 'source':
        sort_key = lambda item: (item.source.casefold(), item.position, item.id or 0)
    elif query.sort == 'status':
        sort_key = lambda item: (status_order[item.status], item.position, item.id or 0)
    else:
        sort_key = lambda item: (item.position, item.id or 0)
    return sorted((segment for segment in segments if included(segment)), key=sort_key, reverse=query.descending)


def preview_replacements(
    segments: Iterable[Segment], find: str, replacement: str, *,
    regex: bool = False, case_sensitive: bool = False,
    include_reviewed: bool = False,
) -> list[TargetReplacement]:
    """Przygotuj podgląd zamiany w Target bez modyfikowania segmentów.

    Segmenty ``REVIEWED``/``APPROVED`` są pomijane, chyba że ``include_reviewed``.
    Source nigdy nie jest zmieniany.

    :raises ValueError: pusta fraza lub błędne wyrażenie zamiany.
    """
    if not find:
        raise ValueError('Search text cannot be empty for replacement')
    pattern = _regex(find, regex, case_sensitive)
    result: list[TargetReplacement] = []
    for segment in segments:
        if segment.id is None:
            continue
        if not include_reviewed and segment.status in {SegmentStatus.REVIEWED, SegmentStatus.APPROVED}:
            continue
        try:
            if regex:
                value, count = pattern.subn(lambda match: match.expand(replacement), segment.target)
            else:
                value, count = pattern.subn(lambda _: replacement, segment.target)
        except re.error as exc:
            raise ValueError(f'Invalid regex replacement: {exc}') from exc
        if count and value != segment.target:
            result.append(TargetReplacement(segment.id, segment.source, segment.target, value, count))
    return result
