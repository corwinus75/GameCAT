"""Połączenie SQLite bezpieczne do współdzielenia między wątkami."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import threading
from types import TracebackType
from typing import Any


class ThreadSafeConnection:
    """Pośrednik ``sqlite3.Connection`` serializujący dostęp z wielu wątków.

    Każde wywołanie i cały blok ``with connection`` (transakcja) są chronione
    jedną blokadą ``RLock``, więc wątek autosave i wątek GUI nie przeplatają
    swoich transakcji.
    """

    def __init__(self, connection: sqlite3.Connection):
        """Opakuj istniejące połączenie i utwórz blokadę wielowejściową."""
        self._connection = connection
        self._lock = threading.RLock()

    def __enter__(self) -> ThreadSafeConnection:
        """Rozpocznij transakcję, zajmując blokadę na cały blok ``with``."""
        self._lock.acquire()
        try:
            self._connection.__enter__()
        except BaseException:
            self._lock.release()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Zatwierdź lub wycofaj transakcję i zwolnij blokadę."""
        try:
            return self._connection.__exit__(exc_type, exc_value, traceback)
        finally:
            self._lock.release()

    def execute(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        """Wykonaj instrukcję SQL pod blokadą i zwróć kursor."""
        with self._lock:
            return self._connection.execute(*args, **kwargs)

    def fetchone(self, *args: Any, **kwargs: Any) -> sqlite3.Row | tuple | None:
        """Wykonaj zapytanie i pobierz jeden wiersz pod tą samą blokadą."""
        with self._lock:
            return self._connection.execute(*args, **kwargs).fetchone()

    def fetchall(self, *args: Any, **kwargs: Any) -> list[sqlite3.Row]:
        """Wykonaj zapytanie i pobierz wszystkie wiersze, nie zwalniając blokady."""
        with self._lock:
            return self._connection.execute(*args, **kwargs).fetchall()

    def executemany(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        """Wykonaj instrukcję dla wielu zestawów parametrów pod blokadą."""
        with self._lock:
            return self._connection.executemany(*args, **kwargs)

    def executescript(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        """Wykonaj skrypt SQL (wiele instrukcji) pod blokadą."""
        with self._lock:
            return self._connection.executescript(*args, **kwargs)

    def backup_to(self, destination: Path) -> None:
        """Utwórz spójną kopię bazy w pliku *destination*, nie zwalniając blokady."""
        with self._lock, sqlite3.connect(destination) as backup:
            self._connection.backup(backup)

    def commit(self) -> None:
        """Zatwierdź bieżącą transakcję pod blokadą."""
        with self._lock:
            self._connection.commit()

    def close(self) -> None:
        """Zamknij połączenie pod blokadą."""
        with self._lock:
            self._connection.close()


def open_database(path: Path) -> ThreadSafeConnection:
    """Otwórz bazę GameCAT (klucze obce, ``sqlite3.Row``) gotową do użycia z wielu wątków."""
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return ThreadSafeConnection(connection)
