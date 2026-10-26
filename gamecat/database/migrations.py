from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

_TERMS_SQL = '''
CREATE TABLE IF NOT EXISTS glossary_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_term TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    case_sensitive INTEGER NOT NULL DEFAULT 0,
    UNIQUE(project_id, source_term, case_sensitive)
)
'''

_TRANSLATIONS_SQL = '''
CREATE TABLE IF NOT EXISTS glossary_translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term_id INTEGER NOT NULL REFERENCES glossary_terms(id) ON DELETE CASCADE,
    target_term TEXT NOT NULL,
    UNIQUE(term_id, target_term)
)
'''


def _table_exists(connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def migrate_glossary_schema(connection: sqlite3.Connection) -> None:
    """Create the 0.7 glossary schema and migrate legacy 0.6 rows atomically."""
    legacy_exists = _table_exists(connection, 'glossary')
    with connection:
        connection.execute(_TERMS_SQL)
        connection.execute(_TRANSLATIONS_SQL)
        if not legacy_exists:
            return

        rows = connection.execute(
            'SELECT id,project_id,source_term,target_term,description,case_sensitive '
            'FROM glossary ORDER BY id'
        ).fetchall()
        grouped: dict[tuple[int, str, bool], dict[str, object]] = {}
        for row in rows:
            project_id = row['project_id']
            if project_id is None:
                logger.warning('Skipping legacy global glossary row id=%s', row['id'])
                continue
            source = str(row['source_term']).strip()
            target = str(row['target_term']).strip()
            if not source or not target:
                logger.warning('Skipping invalid legacy glossary row id=%s', row['id'])
                continue
            case_sensitive = bool(row['case_sensitive'])
            key = (int(project_id), source, case_sensitive)
            description = str(row['description'] or '').strip()
            state = grouped.setdefault(key, {'description': '', 'targets': []})
            old_description = str(state['description'])
            if description and not old_description:
                state['description'] = description
            elif description and old_description and description != old_description:
                logger.warning(
                    'Conflicting descriptions for legacy glossary term %r; keeping first non-empty description',
                    source,
                )
            targets = state['targets']
            assert isinstance(targets, list)
            if target not in targets:
                targets.append(target)

        for (project_id, source, case_sensitive), state in grouped.items():
            cur = connection.execute(
                'INSERT OR IGNORE INTO glossary_terms(project_id,source_term,description,case_sensitive) VALUES(?,?,?,?)',
                (project_id, source, state['description'], int(case_sensitive)),
            )
            term_id = cur.lastrowid
            if not term_id:
                term_id = connection.execute(
                    'SELECT id FROM glossary_terms WHERE project_id=? AND source_term=? AND case_sensitive=?',
                    (project_id, source, int(case_sensitive)),
                ).fetchone()['id']
            for target in state['targets']:
                connection.execute(
                    'INSERT OR IGNORE INTO glossary_translations(term_id,target_term) VALUES(?,?)',
                    (term_id, target),
                )
        connection.execute('DROP TABLE glossary')
