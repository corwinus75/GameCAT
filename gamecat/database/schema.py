import sqlite3
from pathlib import Path

_TM_STORAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS translation_memory (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 source TEXT NOT NULL, target TEXT NOT NULL,
 source_language TEXT NOT NULL, target_language TEXT NOT NULL,
 origin_project TEXT, created_at TEXT NOT NULL
);
"""

_TM_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tm_project_settings (
 project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
 external_path TEXT, threshold REAL NOT NULL DEFAULT 0.45
);
"""

def backup_duplicate_tm(connection, path: Path) -> Path | None:
    """Back up legacy TM before the first deduplication; never overwrite a backup."""
    row = connection.fetchone(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='translation_memory'"
    )
    if row is None:
        return None
    duplicate = connection.fetchone("""
        SELECT 1 FROM translation_memory
        GROUP BY source,target,source_language,target_language
        HAVING COUNT(*) > 1 LIMIT 1
    """)
    if duplicate is None:
        return None
    backup = Path(str(path) + '.before-v1.0.2.bak')
    if not backup.exists():
        try:
            connection.backup_to(backup)
        except Exception:
            backup.unlink(missing_ok=True)
            raise
    return backup


def migrate_tm_indexes(connection: sqlite3.Connection) -> None:
    """Remove legacy duplicate bilingual pairs, then enforce fast and unique lookups.

    Keep the lowest ``id`` (the earliest inserted entry) including its origin.
    The migration is repeatable and runs inside a transaction.
    """
    with connection:
        indexes = {row['name'] for row in connection.fetchall("PRAGMA index_list('translation_memory')")}
        if 'ux_tm_pair' not in indexes:
            connection.execute("""DELETE FROM translation_memory WHERE id NOT IN (
                SELECT MIN(id) FROM translation_memory
                GROUP BY source, target, source_language, target_language
            )""")
        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_tm_languages '
            'ON translation_memory(source_language,target_language)'
        )
        connection.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS ux_tm_pair '
            'ON translation_memory(source,target,source_language,target_language)'
        )


def initialize_tm_storage(connection: sqlite3.Connection) -> None:
    connection.executescript(_TM_STORAGE_SCHEMA)
    migrate_tm_indexes(connection)


from gamecat.database.migrations import migrate_glossary_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_language TEXT NOT NULL,
    target_language TEXT NOT NULL,
    source_format TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    key TEXT,
    source TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'NEW',
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_segments_project_position ON segments(project_id, position);
CREATE TABLE IF NOT EXISTS translation_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    source_language TEXT NOT NULL,
    target_language TEXT NOT NULL,
    origin_project TEXT,
    created_at TEXT NOT NULL
);
"""


_AI_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_project_settings (
 project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
 model TEXT NOT NULL DEFAULT 'gpt-5-mini',
 instructions TEXT NOT NULL DEFAULT '',
 input_price_per_million REAL NOT NULL DEFAULT 0,
 output_price_per_million REAL NOT NULL DEFAULT 0,
 max_output_tokens INTEGER NOT NULL DEFAULT 1024
);
"""


def migrate_ai_schema(connection: sqlite3.Connection) -> None:
    """Idempotent migration; never removes existing translation data."""
    with connection:
        columns = {row['name'] for row in connection.fetchall('PRAGMA table_info(segments)')}
        if 'ai_generated' not in columns:
            connection.execute('ALTER TABLE segments ADD COLUMN ai_generated INTEGER NOT NULL DEFAULT 0')
        connection.executescript(_AI_SETTINGS_SCHEMA)


_FORMAT_PROFILE_SCHEMA = """
CREATE TABLE IF NOT EXISTS project_format_profiles (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    format TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    PRIMARY KEY (project_id, format)
);
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create database objects and migrate the project glossary to schema 0.7."""
    connection.executescript(_SCHEMA)
    migrate_tm_indexes(connection)
    migrate_glossary_schema(connection)
    connection.executescript(_TM_SETTINGS_SCHEMA)
    migrate_ai_schema(connection)
    connection.executescript(_FORMAT_PROFILE_SCHEMA)
    connection.commit()
