from __future__ import annotations
from collections.abc import Iterable
from functools import wraps
from datetime import datetime
import sqlite3
from gamecat.models.project import Project
from gamecat.models.segment import Segment, SegmentStatus
from gamecat.models.glossary import GlossaryEntry, GlossaryTerm
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.database.segment_iterator import SegmentBatchIterator
from gamecat.exceptions import DatabaseError

_INSERT_SEGMENT = '''INSERT INTO segments(project_id,position,key,source,target,status,comment,created_at,updated_at,ai_generated)
                VALUES(?,?,?,?,?,?,?,?,?,?)'''
_UPDATE_SEGMENT = 'UPDATE segments SET target=?,status=?,comment=?,updated_at=?,ai_generated=? WHERE id=?'


def _insert_params(segment: Segment) -> tuple:
    return (segment.project_id, segment.position, segment.key, segment.source, segment.target,
            segment.status.value, segment.comment, segment.created_at.isoformat(), segment.updated_at.isoformat(), int(segment.ai_generated))


def _update_params(segment: Segment) -> tuple:
    if segment.id is None:
        raise ValueError('segment has no id')
    return (segment.target, segment.status.value, segment.comment, segment.updated_at.isoformat(), int(segment.ai_generated), segment.id)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def database_errors(method):
    """Convert low-level SQLite failures at repository API boundaries."""
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except sqlite3.Error as exc:
            raise DatabaseError(f'Database operation {method.__qualname__} failed: {exc}') from exc
    return wrapped


def repository_errors(cls):
    """Decorate repository methods; preserve domain validation exceptions."""
    for name, member in vars(cls).items():
        if name != '__init__' and callable(member):
            setattr(cls, name, database_errors(member))
    return cls


@repository_errors
class ProjectRepository:
    def __init__(self, connection: sqlite3.Connection): self.connection = connection
    def create(self, project: Project) -> Project:
        with self.connection:
            cur = self.connection.execute(
                'INSERT INTO projects(name,source_language,target_language,source_format,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                (project.name, project.source_language, project.target_language, project.source_format, project.created_at.isoformat(), project.updated_at.isoformat()))
        project.id = cur.lastrowid
        return project
    def get(self, project_id: int) -> Project:
        with self.connection:
            row = self.connection.fetchone('SELECT * FROM projects WHERE id=?', (project_id,))
        if row is None: raise KeyError(project_id)
        return Project(row['name'], row['source_language'], row['target_language'], row['source_format'], row['id'], _dt(row['created_at']), _dt(row['updated_at']))
    def list_all(self) -> list[Project]:
        with self.connection:
            rows = self.connection.fetchall('SELECT id FROM projects ORDER BY id')
        return [self.get(row['id']) for row in rows]
    def update(self, project: Project) -> None:
        if project.id is None: raise ValueError('project has no id')
        with self.connection:
            self.connection.execute('UPDATE projects SET name=?,source_language=?,target_language=?,source_format=?,updated_at=? WHERE id=?',
                                    (project.name, project.source_language, project.target_language, project.source_format, project.updated_at.isoformat(), project.id))


@repository_errors
class SegmentRepository:
    def __init__(self, connection: sqlite3.Connection): self.connection = connection
    def create(self, segment: Segment) -> Segment:
        if segment.project_id is None: raise ValueError('segment requires project_id')
        with self.connection:
            cur = self.connection.execute(_INSERT_SEGMENT, _insert_params(segment))
        segment.id = cur.lastrowid
        return segment

    def create_many(self, segments: Iterable[Segment]) -> list[Segment]:
        """Zapisz wiele segmentów w jednej transakcji (wszystko albo nic).

        *segments* może być generatorem – jest konsumowany wewnątrz transakcji,
        więc błąd parsowania w połowie pliku cofa również już wstawione wiersze.
        """
        created: list[Segment] = []
        with self.connection:
            for segment in segments:
                if segment.project_id is None:
                    raise ValueError('segment requires project_id')
                cur = self.connection.execute(_INSERT_SEGMENT, _insert_params(segment))
                segment.id = cur.lastrowid
                created.append(segment)
        return created
    def _from_row(self, row: sqlite3.Row) -> Segment:
        return Segment(row['source'], row['position'], row['key'], row['target'], row['status'], row['comment'], row['id'], row['project_id'], _dt(row['created_at']), _dt(row['updated_at']), bool(row['ai_generated']))
    def get(self, segment_id: int | None) -> Segment:
        if segment_id is None: raise KeyError(segment_id)
        with self.connection:
            row = self.connection.fetchone('SELECT * FROM segments WHERE id=?', (segment_id,))
        if row is None: raise KeyError(segment_id)
        return self._from_row(row)
    def list_for_project(self, project_id: int) -> list[Segment]:
        with self.connection:
            rows = self.connection.fetchall('SELECT * FROM segments WHERE project_id=? ORDER BY position,id', (project_id,))
        return [self._from_row(r) for r in rows]
    def update(self, segment: Segment) -> None:
        params = _update_params(segment)
        with self.connection:
            self.connection.execute(_UPDATE_SEGMENT, params)

    def update_many(self, segments: Iterable[Segment]) -> int:
        """Zaktualizuj wiele segmentów w jednej transakcji; zwraca ich liczbę."""
        params = [_update_params(segment) for segment in segments]
        if not params:
            return 0
        with self.connection:
            self.connection.executemany(_UPDATE_SEGMENT, params)
        return len(params)

    def iter_for_project(self, project_id: int, batch_size: int = 500) -> SegmentBatchIterator:
        """Zwróć iterator czytający segmenty projektu partiami."""
        return SegmentBatchIterator(self.connection, project_id, self._from_row, batch_size)

    def references_for_pairs(
        self, project_id: int, pairs: Iterable[tuple[str, str]],
    ) -> dict[tuple[str, str], tuple[tuple[int, int], ...]]:
        """Map exact TM Source/Target pairs to (segment ID, position) in a project.

        An entry imported from another TM database has no local segment ID.
        A pair reused by multiple segments returns *all* matching references.
        """
        distinct_pairs = list(dict.fromkeys(pairs))
        if not distinct_pairs:
            return {}
        conditions = ' OR '.join('(source=? AND target=?)' for _ in distinct_pairs)
        params: list[str | int] = [project_id]
        for source, target in distinct_pairs:
            params.extend((source, target))
        with self.connection:
            rows = self.connection.fetchall(
                f'SELECT id, position, source, target FROM segments '
                f'WHERE project_id=? AND ({conditions}) ORDER BY position,id',
                tuple(params),
            )
        grouped: dict[tuple[str, str], list[tuple[int, int]]] = {}
        for row in rows:
            grouped.setdefault((row['source'], row['target']), []).append(
                (int(row['id']), int(row['position']))
            )
        return {pair: tuple(refs) for pair, refs in grouped.items()}

    def count_for_project(self, project_id: int) -> int:
        with self.connection:
            row = self.connection.fetchone('SELECT COUNT(*) FROM segments WHERE project_id=?', (project_id,))
        return int(row[0])

    def status_counts(self, project_id: int) -> dict[SegmentStatus, int]:
        """Return exclusive workflow status counts for a project."""
        with self.connection:
            rows = self.connection.fetchall(
                'SELECT status, COUNT(*) AS count FROM segments WHERE project_id=? GROUP BY status',
                (project_id,),
            )
        counts = {status: 0 for status in SegmentStatus}
        for row in rows:
            counts[SegmentStatus(row['status'])] = int(row['count'])
        return counts


@repository_errors
class GlossaryRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def _term_from_id(self, term_id: int) -> GlossaryTerm:
        row = self.connection.fetchone('SELECT * FROM glossary_terms WHERE id=?', (term_id,))
        if row is None:
            raise KeyError(term_id)
        targets = [r['target_term'] for r in self.connection.fetchall(
            'SELECT target_term FROM glossary_translations WHERE term_id=? ORDER BY id', (term_id,)
        )]
        return GlossaryTerm(row['source_term'], targets, row['description'], bool(row['case_sensitive']), row['id'], row['project_id'])

    def get_term(self, term_id: int) -> GlossaryTerm:
        with self.connection:
            return self._term_from_id(term_id)

    def get_by_identity(self, project_id: int, source_term: str, case_sensitive: bool) -> GlossaryTerm | None:
        source = source_term.strip()
        with self.connection:
            row = self.connection.fetchone(
                'SELECT id FROM glossary_terms WHERE project_id=? AND source_term=? AND case_sensitive=?',
                (project_id, source, int(case_sensitive)),
            )
            return self._term_from_id(row['id']) if row else None

    def list_terms(self, project_id: int) -> list[GlossaryTerm]:
        with self.connection:
            rows = self.connection.fetchall(
                'SELECT id FROM glossary_terms WHERE project_id=? ORDER BY source_term COLLATE NOCASE,id',
                (project_id,),
            )
            return [self._term_from_id(r['id']) for r in rows]

    def search_terms(self, project_id: int, query: str) -> list[GlossaryTerm]:
        needle = query.strip().casefold()
        terms = self.list_terms(project_id)
        if not needle:
            return terms
        return [t for t in terms if needle in t.source_term.casefold() or any(needle in x.casefold() for x in t.targets)]

    def create_term(self, term: GlossaryTerm) -> GlossaryTerm:
        if term.project_id is None:
            raise ValueError('glossary term requires project_id')
        with self.connection:
            cur = self.connection.execute(
                'INSERT INTO glossary_terms(project_id,source_term,description,case_sensitive) VALUES(?,?,?,?)',
                (term.project_id, term.source_term, term.description, int(term.case_sensitive)),
            )
            term.id = int(cur.lastrowid)
            self.connection.executemany(
                'INSERT INTO glossary_translations(term_id,target_term) VALUES(?,?)',
                [(term.id, target) for target in term.targets],
            )
        return term

    def update_term_fields(self, term_id: int, source_term: str, description: str, case_sensitive: bool) -> None:
        with self.connection:
            self.connection.execute(
                'UPDATE glossary_terms SET source_term=?,description=?,case_sensitive=? WHERE id=?',
                (source_term.strip(), description.strip(), int(case_sensitive), term_id),
            )

    def delete_term(self, term_id: int) -> None:
        with self.connection:
            self.connection.execute('DELETE FROM glossary_terms WHERE id=?', (term_id,))

    def add_variant(self, term_id: int, target: str) -> bool:
        value = target.strip()
        if not value:
            raise ValueError('target variant cannot be blank')
        with self.connection:
            cur = self.connection.execute(
                'INSERT OR IGNORE INTO glossary_translations(term_id,target_term) VALUES(?,?)',
                (term_id, value),
            )
        return cur.rowcount > 0

    def remove_variant(self, term_id: int, target: str) -> None:
        with self.connection:
            self.connection.execute(
                'DELETE FROM glossary_translations WHERE term_id=? AND target_term=?', (term_id, target.strip())
            )

    def merge_terms(self, project_id: int, terms: Iterable[GlossaryTerm]) -> tuple[int, int, int]:
        new_terms = new_variants = duplicates = 0
        with self.connection:
            for incoming in terms:
                row = self.connection.fetchone(
                    'SELECT id FROM glossary_terms WHERE project_id=? AND source_term=? AND case_sensitive=?',
                    (project_id, incoming.source_term, int(incoming.case_sensitive)),
                )
                if row is None:
                    cur = self.connection.execute(
                        'INSERT INTO glossary_terms(project_id,source_term,description,case_sensitive) VALUES(?,?,?,?)',
                        (project_id, incoming.source_term, incoming.description, int(incoming.case_sensitive)),
                    )
                    term_id = int(cur.lastrowid); new_terms += 1
                else:
                    term_id = int(row['id'])
                    if incoming.description:
                        existing = self.connection.fetchone('SELECT description FROM glossary_terms WHERE id=?',(term_id,))['description']
                        if not existing:
                            self.connection.execute('UPDATE glossary_terms SET description=? WHERE id=?',(incoming.description,term_id))
                for target in incoming.targets:
                    cur = self.connection.execute(
                        'INSERT OR IGNORE INTO glossary_translations(term_id,target_term) VALUES(?,?)',
                        (term_id, target),
                    )
                    if cur.rowcount:
                        new_variants += 1
                    else:
                        duplicates += 1
        return new_terms, new_variants, duplicates

    # 0.6 compatibility path. New code should use list_terms/create_term.
    def create(self, entry: GlossaryEntry) -> GlossaryEntry:
        if entry.project_id is None:
            raise ValueError('global glossary entries are not supported in 0.7')
        existing = self.get_by_identity(entry.project_id, entry.source_term, entry.case_sensitive)
        if existing is None:
            term = self.create_term(GlossaryTerm(entry.source_term, [entry.target_term], entry.description, entry.case_sensitive, project_id=entry.project_id))
            entry.id = term.id
        else:
            self.add_variant(existing.id, entry.target_term)
            entry.id = existing.id
        return entry

    def list_for_project(self, project_id: int | None) -> list[GlossaryEntry]:
        if project_id is None:
            return []
        flat: list[GlossaryEntry] = []
        for term in self.list_terms(project_id):
            for target in term.targets:
                flat.append(GlossaryEntry(term.source_term, target, term.description, term.case_sensitive, term.id, term.project_id))
        return flat


@repository_errors
class TranslationMemoryRepository:
    def __init__(self, connection: sqlite3.Connection): self.connection = connection
    def create(self, entry: TranslationMemoryEntry) -> TranslationMemoryEntry:
        with self.connection:
            cur = self.connection.execute('INSERT INTO translation_memory(source,target,source_language,target_language,origin_project,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(source,target,source_language,target_language) DO NOTHING',
                                          (entry.source, entry.target, entry.source_language, entry.target_language, entry.origin_project, entry.created_at.isoformat()))
            if cur.rowcount:
                entry.id = cur.lastrowid
            else:
                row = self.connection.fetchone('SELECT id FROM translation_memory WHERE source=? AND target=? AND source_language=? AND target_language=?',
                                               (entry.source, entry.target, entry.source_language, entry.target_language))
                entry.id = row['id']
        return entry
    def list_all(self) -> list[TranslationMemoryEntry]:
        with self.connection:
            rows = self.connection.fetchall('SELECT * FROM translation_memory ORDER BY id')
        return [TranslationMemoryEntry(r['source'], r['target'], r['source_language'], r['target_language'], r['origin_project'], r['id'], _dt(r['created_at'])) for r in rows]
    def list_for_languages(self, source_language: str, target_language: str) -> list[TranslationMemoryEntry]:
        with self.connection:
            rows = self.connection.fetchall(
                'SELECT * FROM translation_memory WHERE source_language=? AND target_language=? ORDER BY id',
                (source_language, target_language),
            )
        return [TranslationMemoryEntry(r['source'], r['target'], r['source_language'], r['target_language'], r['origin_project'], r['id'], _dt(r['created_at'])) for r in rows]
    def contains_pair(self, source: str, target: str, source_language: str, target_language: str) -> bool:
        with self.connection:
            row = self.connection.fetchone(
                'SELECT 1 FROM translation_memory WHERE source=? AND target=? AND source_language=? AND target_language=? LIMIT 1',
                (source, target, source_language, target_language),
            )
        return row is not None

    def create_unique_many(self, entries: Iterable[TranslationMemoryEntry]) -> int:
        """Insert distinct bilingual pairs atomically; preserve existing rows."""
        created = 0
        statement = """INSERT OR IGNORE INTO translation_memory
                       (source,target,source_language,target_language,origin_project,created_at)
                       VALUES(?,?,?,?,?,?)"""
        with self.connection:
            for entry in entries:
                if not all(isinstance(value, str) and value.strip() for value in
                           (entry.source, entry.target, entry.source_language, entry.target_language)):
                    raise ValueError('TM source, target and both languages must be non-empty')
                cursor = self.connection.execute(statement, (
                    entry.source, entry.target, entry.source_language, entry.target_language,
                    entry.origin_project, entry.created_at.isoformat(),
                ))
                created += cursor.rowcount
        return created
