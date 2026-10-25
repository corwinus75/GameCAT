from __future__ import annotations

from pathlib import Path
import sqlite3
import threading
from types import TracebackType
from typing import Any


class ThreadSafeConnection:
    """Small sqlite3 connection proxy that serializes transaction contexts across threads."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._lock = threading.RLock()

    def __enter__(self) -> ThreadSafeConnection:
        self._lock.acquire()
        self._connection.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        try:
            return self._connection.__exit__(exc_type, exc_value, traceback)
        finally:
            self._lock.release()

    def execute(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        return self._connection.execute(*args, **kwargs)

    def executescript(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        with self._lock:
            return self._connection.executescript(*args, **kwargs)

    def commit(self) -> None:
        with self._lock:
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()


def open_database(path: Path) -> ThreadSafeConnection:
    """Open a SQLite database configured for GameCAT and safe shared use by worker threads."""
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return ThreadSafeConnection(connection)
