"""Szybki, niezależny od Qt indeks do interaktywnego filtrowania dużych projektów.

Indeks jest migawką: wątki w tle nigdy nie czytają modyfikowalnych obiektów
``Segment``. Tylko wątek GUI aktualizuje pojedyncze rekordy po jawnym zapisie.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from collections.abc import Sequence
import re

from gamecat.models.segment import Segment, SegmentStatus
from gamecat.search.operations import SearchQuery


@dataclass(frozen=True, slots=True)
class SearchRecord:
    """Niemutowalny rekord indeksu z tekstami przygotowanymi do wyszukiwania bez wielkości liter."""
    id: int | None
    position: int
    source: str
    target: str
    status: str
    source_folded: str
    target_folded: str

    @classmethod
    def from_segment(cls, segment: Segment) -> 'SearchRecord':
        """Utwórz rekord indeksu z segmentu (alternatywny konstruktor)."""
        return cls(segment.id, segment.position, segment.source, segment.target,
                   segment.status.value, segment.source.casefold(), segment.target.casefold())


class SegmentSearchIndex:
    """Niemutowalne rekordy umożliwiające przerywalne wyszukiwanie poza wątkiem GUI.

    Aktualizacja publikuje nową krotkę rekordów zamiast zmieniać istniejące,
    dzięki czemu trwające filtrowanie może bezpiecznie się zakończyć lub przerwać.
    """

    def __init__(self, segments: Sequence[Segment]):
        """Zbuduj indeks z migawek segmentów."""
        self._records = tuple(SearchRecord.from_segment(s) for s in segments)
        self._id_to_row = {record.id: row for row, record in enumerate(self._records)
                           if record.id is not None}

    def updated(self, segment: Segment) -> 'SegmentSearchIndex':
        """Zwróć nowy indeks z odświeżonym rekordem segmentu (oryginał pozostaje bez zmian)."""
        row = self._id_to_row.get(segment.id)
        if row is None:
            return self
        result = object.__new__(SegmentSearchIndex)
        records = list(self._records)
        records[row] = SearchRecord.from_segment(segment)
        result._records = tuple(records)
        result._id_to_row = self._id_to_row
        return result

    def _filter_rows(self, query: SearchQuery, matcher: re.Pattern[str] | None, needle: str,
                     results: list[int], cancel: Event | None,
                     qa_ids: frozenset[int] = frozenset(),
                     tm_ids: frozenset[int] = frozenset()) -> list[int] | None:
        """Przefiltruj i posortuj wiersze; zwróć ``None``, gdy ustawiono zdarzenie *cancel*.

        Przerwanie jest sprawdzane co 128 rekordów.
        """
        for row, record in enumerate(self._records):
            if cancel is not None and row % 128 == 0 and cancel.is_set():
                return None
            if query.status != 'ALL' and record.status != query.status:
                continue
            if query.quality == 'untranslated' and record.target.strip():
                continue
            if query.quality == 'qa_errors' and record.id not in qa_ids:
                continue
            if query.quality == 'tm_match' and record.id not in tm_ids:
                continue
            if needle:
                fields = (record.source, record.target) if query.scope == 'both' else (
                    (record.source,) if query.scope == 'source' else (record.target,))
                if matcher is not None:
                    if not any(matcher.search(value) for value in fields):
                        continue
                else:
                    values = fields if query.case_sensitive else (
                        (record.source_folded, record.target_folded) if query.scope == 'both' else
                        (record.source_folded,) if query.scope == 'source' else (record.target_folded,))
                    if not any(needle in value for value in values):
                        continue
            results.append(row)
        if cancel is not None and cancel.is_set():
            return None
        status_order = {s.value: i for i, s in enumerate(SegmentStatus)}
        if query.sort == 'source':
            key = lambda row: (self._records[row].source_folded, self._records[row].position,
                               self._records[row].id or 0)
        elif query.sort == 'status':
            key = lambda row: (status_order[self._records[row].status], self._records[row].position,
                               self._records[row].id or 0)
        else:
            key = lambda row: (self._records[row].position, self._records[row].id or 0)
        results.sort(key=key, reverse=query.descending)
        return results

    def search(self, query: SearchQuery, *, qa_error_ids=(), tm_match_ids=(),
               cancel: Event | None = None) -> list[int] | None:
        """Przefiltruj stabilną migawkę – bez operacji na bazie i Qt.

        :raises ValueError: nieprawidłowe opcje lub wyrażenie regularne.
        """
        if query.scope not in {'both', 'source', 'target'} or query.sort not in {'position', 'source', 'status'} \
                or query.quality not in {'all', 'untranslated', 'qa_errors', 'tm_match'} \
                or query.status not in {'ALL', *(s.value for s in SegmentStatus)}:
            raise ValueError('Invalid search options')
        try:
            matcher = re.compile(query.phrase, 0 if query.case_sensitive else re.IGNORECASE) \
                if query.regex and query.phrase else None
        except re.error as exc:
            raise ValueError(f'Invalid search regex: {exc}') from exc
        needle = query.phrase if query.case_sensitive else query.phrase.casefold()
        return self._filter_rows(query, matcher, needle, [], cancel,
                                 frozenset(qa_error_ids), frozenset(tm_match_ids))
