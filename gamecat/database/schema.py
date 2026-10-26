import sqlite3

_TM_STORAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS translation_memory (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 source TEXT NOT NULL, target TEXT NOT NULL,
 source_language TEXT NOT NULL, target_language TEXT NOT NULL,
 origin_project TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tm_languages ON translation_memory(source_language,target_language);
"""

_TM_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tm_project_settings (
 project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
 external_path TEXT, threshold REAL NOT NULL DEFAULT 0.45
);
"""

def initialize_tm_storage(connection: sqlite3.Connection) -> None:
    connection.executescript(_TM_STORAGE_SCHEMA)
    connection.commit()


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
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(segments)').fetchall()}
        if 'ai_generated' not in columns:
            connection.execute('ALTER TABLE segments ADD COLUMN ai_generated INTEGER NOT NULL DEFAULT 0')
        connection.executescript(_AI_SETTINGS_SCHEMA)


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create database objects and migrate the project glossary to schema 0.7."""
    connection.executescript(_SCHEMA)
    migrate_glossary_schema(connection)
    connection.executescript(_TM_SETTINGS_SCHEMA)
    migrate_ai_schema(connection)
    connection.commit()
