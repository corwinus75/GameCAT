from pathlib import Path
import sqlite3


def open_database(path: Path) -> sqlite3.Connection:
    """Open a SQLite database configured for GameCAT."""
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection
