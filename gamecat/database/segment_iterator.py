"""Iterator czytający segmenty projektu z SQLite partiami."""
from __future__ import annotations

from collections import deque
from collections.abc import Callable
import sqlite3
from typing import Any

from gamecat.models.segment import Segment

_BATCH_SQL = """
    SELECT * FROM segments
    WHERE project_id = ?
      AND (position > ? OR (position = ? AND id > ?))
    ORDER BY position, id
    LIMIT ?
"""


class SegmentBatchIterator:
    """Jednorazowy iterator po segmentach projektu (protokół ``__iter__``/``__next__``).

    Zamiast wczytywać cały projekt do pamięci, pobiera z bazy kolejne partie
    po *batch_size* wierszy. Stosuje paginację po kluczu (keyset pagination):
    każda partia zaczyna się za ostatnim zwróconym ``(position, id)``, więc
    koszt pobrania partii nie rośnie wraz z numerem strony, jak przy ``OFFSET``.

    Każda partia jest czytana w osobnej transakcji, dzięki czemu wątek autosave
    nie jest blokowany na czas całej iteracji.
    """

    def __init__(
        self,
        connection: Any,
        project_id: int,
        row_factory: Callable[[sqlite3.Row], Segment],
        batch_size: int = 500,
    ) -> None:
        if batch_size < 1:
            raise ValueError('batch_size must be >= 1')
        self._connection = connection
        self._project_id = project_id
        self._row_factory = row_factory
        self._batch_size = batch_size
        self._buffer: deque[Segment] = deque()
        self._last_key: tuple[int, int] = (-(2**63), -(2**63))
        self._exhausted = False
        self.batches_fetched = 0

    def __iter__(self) -> SegmentBatchIterator:
        return self

    def __next__(self) -> Segment:
        if not self._buffer:
            if self._exhausted:
                raise StopIteration
            self._fetch_batch()
            if not self._buffer:
                self._exhausted = True
                raise StopIteration
        return self._buffer.popleft()

    def _fetch_batch(self) -> None:
        position, segment_id = self._last_key
        with self._connection:
            rows = self._connection.fetchall(
                _BATCH_SQL,
                (self._project_id, position, position, segment_id, self._batch_size),
            )
        if not rows:
            return
        self.batches_fetched += 1
        self._buffer.extend(self._row_factory(row) for row in rows)
        last = rows[-1]
        self._last_key = (last['position'], last['id'])
        if len(rows) < self._batch_size:
            # Ostatnia, niepełna partia – kolejne zapytanie nie jest potrzebne.
            self._exhausted = True
