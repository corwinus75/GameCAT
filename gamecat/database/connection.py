from pathlib import Path
import sqlite3
import threading


class SynchronizedConnection(sqlite3.Connection):
    """Serialize transactions on a connection shared between GameCAT threads.

    The lock covers the *entire* `with connection:` transaction, including its
    commit/rollback. Locking only individual SQL statements would still let
    another thread change the connection's transaction state before commit.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._db_lock = threading.RLock()

    def __enter__(self):
        self._db_lock.acquire()
        try:
            return super().__enter__()
        except BaseException:
            self._db_lock.release()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self._db_lock.release()

    def execute(self, sql, parameters=(), /):
        with self._db_lock:
            return super().execute(sql, parameters)

    def executemany(self, sql, parameters, /):
        with self._db_lock:
            return super().executemany(sql, parameters)

    def executescript(self, sql_script, /):
        with self._db_lock:
            return super().executescript(sql_script)

    def commit(self):
        with self._db_lock:
            return super().commit()

    def rollback(self):
        with self._db_lock:
            return super().rollback()

    def close(self):
        with self._db_lock:
            return super().close()


def open_database(path: Path) -> sqlite3.Connection:
    """Open a thread-safe-for-GameCAT SQLite connection.

    Only connections opened here receive transaction synchronization.
    check_same_thread=False alone does NOT make shared transactions safe.
    """
    connection = sqlite3.connect(path, check_same_thread=False, factory=SynchronizedConnection)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection
