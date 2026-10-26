from pathlib import Path
import sqlite3

from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema
from gamecat.database.repositories import GlossaryRepository


def _legacy_db(path: Path):
    conn = sqlite3.connect(path)
    conn.executescript('''
    CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, source_language TEXT NOT NULL,
      target_language TEXT NOT NULL, source_format TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    INSERT INTO projects VALUES(1,'P','en','pl','txt','x','x');
    CREATE TABLE glossary (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
      source_term TEXT NOT NULL, target_term TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '', case_sensitive INTEGER NOT NULL DEFAULT 0
    );
    ''')
    return conn


def test_migrates_legacy_rows_to_one_term_with_variants(tmp_path: Path):
    path = tmp_path / 'legacy.db'
    raw = _legacy_db(path)
    raw.executemany('INSERT INTO glossary(project_id,source_term,target_term,description,case_sensitive) VALUES(?,?,?,?,?)', [
        (1, 'sword', 'miecz', '', 0),
        (1, 'sword', 'ostrze', 'Broń', 0),
        (1, 'sword', 'miecz', 'Inny opis', 0),
        (None, 'global', 'globalny', '', 0),
    ])
    raw.commit(); raw.close()

    conn = open_database(path)
    initialize_schema(conn)
    repo = GlossaryRepository(conn)
    terms = repo.list_terms(1)
    assert len(terms) == 1
    assert terms[0].source_term == 'sword'
    assert terms[0].targets == ['miecz', 'ostrze']
    assert terms[0].description == 'Broń'
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='glossary'").fetchone() is None
    initialize_schema(conn)  # idempotent
    assert len(repo.list_terms(1)) == 1
    conn.close()


def test_fresh_schema_contains_new_glossary_tables(tmp_path: Path):
    conn = open_database(tmp_path / 'fresh.db')
    initialize_schema(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {'glossary_terms', 'glossary_translations'} <= names
    assert 'glossary' not in names
    conn.close()
