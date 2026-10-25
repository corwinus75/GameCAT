from __future__ import annotations
import queue
import threading

from gamecat.database.repositories import SegmentRepository
from gamecat.models.segment import Segment

_SENTINEL = object()


class SaveQueue:
    """Queue snapshots of segment edits; report worker failures to the caller."""

    def __init__(self, repository: SegmentRepository):
        self.repository = repository
        self._queue: queue.Queue[Segment | object] = queue.Queue()
        self._state_lock = threading.Lock()
        self._closed = False
        self._errors: list[Exception] = []
        self._thread = threading.Thread(target=self._worker, daemon=True, name='gamecat-save')
        self._thread.start()

    def enqueue(self, segment: Segment) -> None:
        # Keep edits as they were when enqueued, even if the UI changes the
        # Segment while it is waiting for the worker.
        snapshot = Segment(segment.source, segment.position, segment.key, segment.target, segment.status,
                           segment.comment, segment.id, segment.project_id, segment.created_at, segment.updated_at)
        with self._state_lock:
            if self._closed:
                raise RuntimeError('SaveQueue is closed')
            self._queue.put(snapshot)

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _SENTINEL:
                    return
                assert isinstance(item, Segment)
                try:
                    self.repository.update(item)
                except Exception as exc:
                    # Don't terminate the consumer: otherwise any remaining
                    # unfinished tasks make Queue.join() hang indefinitely.
                    self._errors.append(exc)
            finally:
                self._queue.task_done()

    def _raise_if_failed(self) -> None:
        if self._errors:
            raise RuntimeError('SaveQueue: segment write failed') from self._errors[0]

    def flush(self) -> None:
        self._queue.join()
        self._raise_if_failed()

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            # Add the sentinel while holding the same lock as enqueue(), so
            # that no edit can be placed *after* the stop request.
            self._queue.put(_SENTINEL)
        self._queue.join()
        self._thread.join()
        self._raise_if_failed()
