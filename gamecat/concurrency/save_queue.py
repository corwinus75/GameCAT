from __future__ import annotations
import queue
import threading
from dataclasses import replace
from gamecat.database.repositories import SegmentRepository
from gamecat.models.segment import Segment

_SENTINEL = object()


class SaveQueue:
    """Serialize segment writes through one worker and one critical section."""
    def __init__(self, repository: SegmentRepository):
        self.repository = repository
        self._queue: queue.Queue[Segment | object] = queue.Queue()
        self._lock = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(target=self._worker, daemon=True, name='gamecat-save')
        self._thread.start()

    def enqueue(self, segment: Segment) -> None:
        if self._closed:
            raise RuntimeError('SaveQueue is closed')
        # Snapshot mutable values at enqueue time.
        snapshot = Segment(segment.source, segment.position, segment.key, segment.target, segment.status,
                           segment.comment, segment.id, segment.project_id, segment.created_at, segment.updated_at)
        self._queue.put(snapshot)

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _SENTINEL:
                    return
                assert isinstance(item, Segment)
                with self._lock:
                    self.repository.update(item)
            finally:
                self._queue.task_done()

    def flush(self) -> None:
        self._queue.join()

    def close(self) -> None:
        if self._closed:
            return
        self.flush()
        self._closed = True
        self._queue.put(_SENTINEL)
        self._queue.join()
        self._thread.join(timeout=2)
