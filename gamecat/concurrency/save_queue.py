from __future__ import annotations

import queue
import sqlite3
import threading
import time
from collections import OrderedDict

from gamecat.database.repositories import SegmentRepository
from gamecat.exceptions import DatabaseError
from gamecat.models.segment import Segment
from gamecat.utils.decorators import is_transient_sqlite_error, retry

_SENTINEL = object()


class SaveQueue:
    """Serialize and coalesce segment writes in a background worker.

    Rapid edits of the same segment are reduced to the newest snapshot after a
    short idle window. ``flush()`` is the durability boundary used by manual
    save, export/QA operations and project shutdown.
    """

    def __init__(self, repository: SegmentRepository, debounce_seconds: float = 0.20):
        if debounce_seconds < 0:
            raise ValueError('debounce_seconds must be non-negative')
        self.repository = repository
        self.debounce_seconds = debounce_seconds
        self._queue: queue.Queue[Segment | object] = queue.Queue()
        self._closed = False
        self._state_lock = threading.Lock()
        self._pending_count = 0
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._worker, daemon=True, name='gamecat-save')
        self._thread.start()

    @staticmethod
    def _snapshot(segment: Segment) -> Segment:
        return Segment(
            segment.source,
            segment.position,
            segment.key,
            segment.target,
            segment.status,
            segment.comment,
            segment.id,
            segment.project_id,
            segment.created_at,
            segment.updated_at,
            segment.ai_generated,
        )

    @property
    def pending_count(self) -> int:
        with self._state_lock:
            return self._pending_count

    def enqueue(self, segment: Segment) -> None:
        if self._closed:
            raise RuntimeError('SaveQueue is closed')
        with self._state_lock:
            if self._error is not None:
                raise RuntimeError('Background save worker failed') from self._error
            self._pending_count += 1
        self._queue.put(self._snapshot(segment))

    def _mark_done(self, count: int) -> None:
        with self._state_lock:
            self._pending_count -= count

    @staticmethod
    def _coalesce(batch: list[Segment]) -> list[Segment]:
        """Zostaw tylko najnowszą migawkę każdego segmentu (kolejność pierwszego wystąpienia)."""
        latest: OrderedDict[int, Segment] = OrderedDict()
        for item in batch:
            key = item.id if item.id is not None else id(item)
            latest[key] = item
        return list(latest.values())

    # Zapis jest idempotentny (UPDATE najnowszej migawki w jednej transakcji),
    # więc można go bezpiecznie ponowić, gdy plik bazy chwilowo blokuje inny
    # proces (np. klient synchronizacji chmury, antywirus, druga instancja).
    @retry(attempts=3, delay=0.25, exceptions=(sqlite3.OperationalError, DatabaseError), when=is_transient_sqlite_error)
    def _save_batch(self, batch: list[Segment]) -> None:
        self.repository.update_many(self._coalesce(batch))

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                self._queue.task_done()
                return

            assert isinstance(item, Segment)
            batch = [item]
            sentinel_seen = False

            if self.debounce_seconds > 0:
                deadline = time.monotonic() + self.debounce_seconds
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        next_item = self._queue.get(timeout=remaining)
                    except queue.Empty:
                        break
                    if next_item is _SENTINEL:
                        sentinel_seen = True
                        break
                    assert isinstance(next_item, Segment)
                    batch.append(next_item)
                    # Debounce from the last edit rather than from the first.
                    deadline = time.monotonic() + self.debounce_seconds

            try:
                self._save_batch(batch)
            except BaseException as exc:
                with self._state_lock:
                    if self._error is None:
                        self._error = exc
            finally:
                for _ in batch:
                    self._queue.task_done()
                self._mark_done(len(batch))

            if sentinel_seen:
                self._queue.task_done()
                return

    def flush(self) -> None:
        self._queue.join()
        with self._state_lock:
            error = self._error
        if error is not None:
            raise RuntimeError('Background save failed') from error

    def close(self) -> None:
        if self._closed:
            return
        self.flush()
        self._closed = True
        self._queue.put(_SENTINEL)
        self._queue.join()
        self._thread.join(timeout=2)
