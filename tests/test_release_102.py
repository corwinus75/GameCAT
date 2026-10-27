"""Testy regresyjne bazy danych i obsługi wielu projektów (wydanie 1.0.2)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gamecat.exceptions import DatabaseError
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.services.project_service import ProjectService


def test_migrate_duplicate_internal_tm_preserves_oldest_and_is_idempotent(tmp_path: Path):
    path = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(path) as old:
        old.execute('CREATE TABLE translation_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, target TEXT NOT NULL, source_language TEXT NOT NULL, target_language TEXT NOT NULL, origin_project TEXT, created_at TEXT NOT NULL)')
        old.executemany('INSERT INTO translation_memory(source,target,source_language,target_language,origin_project,created_at) VALUES(?,?,?,?,?,?)', [
            ('Hi', 'Cześć', 'en', 'pl', 'original', '2020-01-01'),
            ('Hi', 'Cześć', 'en', 'pl', 'duplicate', '2021-01-01'),
            ('Hi', 'Cześć', 'en', 'de', 'different language', '2022-01-01'),
        ])
    for _ in range(2):
        svc = ProjectService(path)
        try:
            pairs = svc.translation_memory.list_all()
            assert len(pairs) == (2 if _ == 0 else 3)
            backup = Path(str(path) + '.before-v1.0.2.bak')
            assert backup.exists()
            with sqlite3.connect(backup) as original:
                assert original.execute('SELECT count(*) FROM translation_memory').fetchone()[0] == 3
            assert pairs[0].origin_project == 'original'
            indexes = {row['name'] for row in svc.connection.fetchall("PRAGMA index_list('translation_memory')")}
            assert 'idx_tm_languages' in indexes
            assert 'ux_tm_pair' in indexes
            assert svc.translation_memory.create_unique_many([TranslationMemoryEntry('Hi', 'Cześć', 'en', 'pl')]) == 0
            assert svc.translation_memory.create_unique_many([TranslationMemoryEntry('Hi', 'Hej', 'en', 'pl')]) == (1 if _ == 0 else 0)
        finally:
            svc.close()


def test_external_tm_is_migrated_without_touching_unrelated_data(tmp_path: Path):
    project_path = tmp_path / 'project.sqlite'
    external_path = tmp_path / 'tm.sqlite'
    svc = ProjectService(project_path)
    project = svc.create_project('P', 'en', 'pl', 'txt')
    svc.close()
    with sqlite3.connect(external_path) as conn:
        conn.execute('CREATE TABLE translation_memory (id INTEGER PRIMARY KEY, source TEXT NOT NULL, target TEXT NOT NULL, source_language TEXT NOT NULL, target_language TEXT NOT NULL, origin_project TEXT, created_at TEXT NOT NULL)')
        for row in (1, 2):
            conn.execute('INSERT INTO translation_memory VALUES(?, ?, ?, ?, ?, ?, ?)', (row, 'A', 'B', 'en', 'pl', f'v{row}', '2020-01-01'))
    svc = ProjectService(project_path)
    try:
        p = svc.list_projects()[0]
        svc.attach_tm_database(p, external_path)
        assert len(svc.translation_memory.list_all()) == 1
        assert Path(str(external_path) + '.before-v1.0.2.bak').exists()
    finally:
        svc.close()


def test_multi_project_switches_tm_backends_without_cross_project_leakage(tmp_path: Path):
    path = tmp_path / 'multi.sqlite'
    ext1, ext2 = tmp_path / 'first.sqlite', tmp_path / 'second.sqlite'
    svc = ProjectService(path)
    try:
        p1 = svc.create_project('One', 'en', 'pl', 'txt')
        svc.attach_tm_database(p1, ext1)
        svc.translation_memory.create(TranslationMemoryEntry('one', 'jeden', 'en', 'pl'))
        p2 = svc.create_project('Two', 'en', 'pl', 'txt')
        svc.attach_tm_database(p2, ext2)
        svc.translation_memory.create(TranslationMemoryEntry('two', 'dwa', 'en', 'pl'))
        assert [e.source for e in svc.translation_memory.list_all()] == ['two']
        svc.select_project(p1)
        assert [e.source for e in svc.translation_memory.list_all()] == ['one']
    finally:
        svc.close()
    reopened = ProjectService(path)
    try:
        projects = reopened.list_projects()
        assert len(projects) == 2
        assert reopened.translation_memory.list_all() == []  # no implicit first-project selection
        reopened.select_project(projects[1])
        assert [e.source for e in reopened.translation_memory.list_all()] == ['two']
        reopened.select_project(projects[0])
        assert [e.source for e in reopened.translation_memory.list_all()] == ['one']
    finally:
        reopened.close()


def test_failed_project_switch_keeps_current_tm(tmp_path: Path):
    svc = ProjectService(tmp_path / 'multi.sqlite')
    try:
        first = svc.create_project('One', 'en', 'pl', 'txt')
        second = svc.create_project('Two', 'en', 'pl', 'txt')
        svc.select_project(first)
        svc.translation_memory.create(TranslationMemoryEntry('Internal', 'Wewnętrzny', 'en', 'pl'))
        nonexistent = tmp_path / 'lost.sqlite'
        with svc.connection:
            svc.connection.execute('INSERT INTO tm_project_settings(project_id, external_path) VALUES (?,?)', (second.id, str(nonexistent)))
        with pytest.raises(FileNotFoundError):
            svc.select_project(second)
        assert svc.active_project_id == first.id
        assert [entry.source for entry in svc.translation_memory.list_all()] == ['Internal']
    finally:
        svc.close()


def test_repository_sql_errors_are_wrapped_with_cause_and_domain_errors_stay(tmp_path: Path):
    svc = ProjectService(tmp_path / 'p.sqlite')
    try:
        with pytest.raises(KeyError):
            svc.projects.get(999)
        with svc.connection:
            svc.connection.execute('DROP TABLE projects')
        with pytest.raises(DatabaseError) as exc:
            svc.projects.list_all()
        assert isinstance(exc.value.__cause__, sqlite3.Error)
    finally:
        svc.close()


def test_tm_create_returns_existing_row_for_identical_pair(tmp_path: Path):
    svc = ProjectService(tmp_path / 'p.sqlite')
    try:
        first = svc.translation_memory.create(TranslationMemoryEntry('Hi', 'Cześć', 'en', 'pl', origin_project='first'))
        second = svc.translation_memory.create(TranslationMemoryEntry('Hi', 'Cześć', 'en', 'pl', origin_project='second'))
        assert first.id == second.id
        assert [entry.origin_project for entry in svc.translation_memory.list_all()] == ['first']
    finally:
        svc.close()


def test_autosave_retries_wrapped_transient_database_error():
    from gamecat.concurrency.save_queue import SaveQueue
    from gamecat.models.segment import Segment

    class FlakyRepository:
        calls = 0

        def update_many(self, items):
            self.calls += 1
            if self.calls == 1:
                try:
                    raise sqlite3.OperationalError('database is locked')
                except sqlite3.OperationalError as exc:
                    raise DatabaseError('database is locked') from exc
            return len(items)

    repo = FlakyRepository()
    queue = SaveQueue(repo, debounce_seconds=0)
    queue.enqueue(Segment('Hi', 1, target='Cześć', id=1, project_id=1))
    queue.flush()
    queue.close()
    assert repo.calls == 2


def test_other_project_can_open_when_first_external_tm_is_missing(tmp_path: Path):
    svc = ProjectService(tmp_path / 'multi.sqlite')
    p1 = svc.create_project('P1', 'en', 'pl', 'txt')
    p2 = svc.create_project('P2', 'en', 'pl', 'txt')
    with svc.connection:
        svc.connection.execute('INSERT INTO tm_project_settings(project_id, external_path) VALUES (?,?)',
                               (p1.id, str(tmp_path / 'not-there.sqlite')))
    svc.close()
    reopened = ProjectService(tmp_path / 'multi.sqlite')
    try:
        assert len(reopened.list_projects()) == 2
        reopened.select_project(p2)
        assert reopened.active_project_id == p2.id
        with pytest.raises(FileNotFoundError):
            reopened.select_project(p1)
        assert reopened.active_project_id == p2.id
    finally:
        reopened.close()


def test_approval_does_not_persist_if_project_tm_is_unavailable(tmp_path: Path):
    from gamecat.models.segment import Segment, SegmentStatus

    svc = ProjectService(tmp_path / 'multi.sqlite')
    try:
        p1 = svc.create_project('Active', 'en', 'pl', 'txt')
        p2 = svc.create_project('Broken', 'en', 'pl', 'txt')
        item = svc.segments.create(Segment('The gate.', 1, target='Brama.', project_id=p2.id))
        with svc.connection:
            svc.connection.execute('INSERT INTO tm_project_settings(project_id, external_path) VALUES (?,?)',
                                   (p2.id, str(tmp_path / 'missing-tm.sqlite')))
        svc.select_project(p1)
        with pytest.raises(FileNotFoundError):
            svc.set_segment_statuses([item], SegmentStatus.APPROVED)
        assert svc.segments.get(item.id).status is SegmentStatus.NEW
    finally:
        svc.close()
