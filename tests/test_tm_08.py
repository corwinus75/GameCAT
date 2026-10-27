"""Regression tests for GameCAT 0.8 TM enhancements."""
from pathlib import Path

import pytest

from gamecat.models.segment import SegmentStatus
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.services.project_service import ProjectService
from gamecat.tm.exchange import read_tm, write_tm


def add_entry(service: ProjectService, source: str = 'Take the sword.', target: str = 'Weź miecz.') -> None:
    service.translation_memory.create(TranslationMemoryEntry(source, target, 'en', 'pl'))


def test_tm_json_csv_roundtrip_and_deduplicate(tmp_path: Path):
    path = tmp_path / 'p.sqlite'
    service = ProjectService(path)
    try:
        project = service.create_project('P', 'en', 'pl', 'txt')
        add_entry(service)
        add_entry(service, 'A gate.', 'Brama.')
        for ext in ('csv', 'json'):
            output = tmp_path / f'tm.{ext}'
            assert service.export_tm_file(project, output) == 2
            assert len(read_tm(output)) == 2
            assert service.import_tm_file(project, output) == 0
    finally:
        service.close()


def test_tm_import_atomic_when_invalid_entry(tmp_path: Path):
    service = ProjectService(tmp_path / 'p.sqlite')
    try:
        project = service.create_project('P', 'en', 'pl', 'txt')
        invalid = tmp_path / 'bad.json'
        invalid.write_text('[{"source":"A", "target":"B", "source_language":"en", "target_language":"pl"}, {"source":"", "target":"C", "source_language":"en", "target_language":"pl"}]', encoding='utf-8')
        with pytest.raises(ValueError):
            service.import_tm_file(project, invalid)
        assert service.translation_memory.list_all() == []
    finally:
        service.close()


def test_external_tm_database_persists_selection_and_isolated_from_project_tm(tmp_path: Path):
    db = tmp_path / 'project.sqlite'
    extra = tmp_path / 'external.sqlite'
    service = ProjectService(db)
    project = service.create_project('P', 'en', 'pl', 'txt')
    add_entry(service, 'Internal', 'Wewnętrzne')
    service.attach_tm_database(project, extra)
    assert service.tm_database_path(project) == extra
    assert service.translation_memory.list_all() == []
    add_entry(service, 'External', 'Zewnętrzne')
    service.close()
    reopened = ProjectService(db)
    try:
        p = reopened.list_projects()[0]
        assert reopened.tm_database_path(p) == extra
        assert [x.source for x in reopened.translation_memory.list_all()] == ['External']
        reopened.use_project_tm_database(p)
        assert [x.source for x in reopened.translation_memory.list_all()] == ['Internal']
    finally:
        reopened.close()


def test_tm_rejects_project_database_as_external_storage(tmp_path: Path):
    path = tmp_path / 'p.sqlite'
    service = ProjectService(path)
    try:
        project = service.create_project('P', 'en', 'pl', 'txt')
        with pytest.raises(ValueError):
            service.attach_tm_database(project, path)
    finally:
        service.close()


def test_tm_threshold_saved_per_project_and_used_by_default(tmp_path: Path):
    path = tmp_path / 'project.sqlite'
    service = ProjectService(path)
    project = service.create_project('P', 'en', 'pl', 'txt')
    add_entry(service, 'The gate is open.', 'Brama jest otwarta.')
    service.set_tm_threshold(project, .92)
    assert service.find_tm_matches(project, 'The gate is open.')
    assert not service.find_tm_matches(project, 'The gate is now open.')
    service.close()
    reopened = ProjectService(path)
    try:
        assert reopened.get_tm_threshold(reopened.list_projects()[0]) == pytest.approx(.92)
    finally:
        reopened.close()


def test_approved_segment_added_automatically_to_tm(tmp_path: Path):
    service = ProjectService(tmp_path / 'p.sqlite')
    try:
        project = service.create_project('P', 'en', 'pl', 'txt')
        sample = tmp_path / 's.txt'
        sample.write_text('The castle.\n', encoding='utf-8')
        row = service.import_file_async(project, sample).result(timeout=5)[0]
        row.target = 'Zamek.'
        service.save_segment(row)
        assert service.set_segment_statuses([row], SegmentStatus.APPROVED) == 1
        assert [e.target for e in service.translation_memory.list_for_languages('en','pl')] == ['Zamek.']
        assert service.set_segment_statuses([row], SegmentStatus.APPROVED) == 1
        assert len(service.translation_memory.list_all()) == 1
    finally:
        service.close()


def test_batch_pretranslate_threshold_protects_existing_targets(tmp_path: Path):
    service = ProjectService(tmp_path / 'p.sqlite')
    try:
        project = service.create_project('P', 'en', 'pl', 'txt')
        sample = tmp_path / 's.txt'
        sample.write_text('Open the gate.\nOpen the gate now.\nOpen the gate now.\n', encoding='utf-8')
        rows = service.import_file_async(project, sample).result(timeout=5)
        rows[2].target = 'Już przetłumaczone.'
        service.save_segment(rows[2])
        add_entry(service, 'Open the gate.', 'Otwórz bramę.')
        report = service.analyze_project_tm(project, mode='sequential')
        assert service.apply_tm_matches(project, report, minimum_score=1) == 1
        assert service.apply_tm_matches(project, report, minimum_score=.5) == 1
        targets = [r.target for r in service.list_segments(project.id)]
        assert targets == ['Otwórz bramę.', 'Otwórz bramę.', 'Już przetłumaczone.']
    finally:
        service.close()


def test_missing_linked_tm_is_not_silently_recreated(tmp_path: Path):
    project_file = tmp_path / 'project.sqlite'
    ext = tmp_path / 'external.sqlite'
    service = ProjectService(project_file)
    project = service.create_project('P', 'en', 'pl', 'txt')
    service.attach_tm_database(project, ext)
    service.close()
    ext.unlink()
    # Since 1.0.2 TM is loaded only after selecting the project.
    reopened = ProjectService(project_file)
    try:
        with pytest.raises(FileNotFoundError, match='Linked external TM'):
            reopened.select_project(reopened.projects.list_all()[0])
    finally:
        reopened.close()
    assert not ext.exists()


def test_external_tm_does_not_modify_unrelated_sqlite(tmp_path: Path):
    import sqlite3
    foreign_path = tmp_path / 'unrelated.sqlite'
    with sqlite3.connect(foreign_path) as db:
        db.execute('CREATE TABLE customers (name TEXT)')
    service = ProjectService(tmp_path / 'project.sqlite')
    try:
        project = service.create_project('P', 'en', 'pl', 'txt')
        with pytest.raises(ValueError, match='not a standalone'):
            service.attach_tm_database(project, foreign_path)
        with sqlite3.connect(foreign_path) as db:
            assert not db.execute("SELECT name FROM sqlite_master WHERE name='translation_memory'").fetchone()
    finally:
        service.close()


def test_import_tm_preserves_language_pairs_and_unicode(tmp_path: Path):
    service = ProjectService(tmp_path / 'project.sqlite')
    try:
        project = service.create_project('P', 'en', 'pl', 'txt')
        fixture = tmp_path / 'tm.csv'
        fixture.write_text('source,target,source_language,target_language,origin_project,created_at\n'
                           'Łódź,Łódź,pl,en,BAK,\n'
                           'The gate,Brama,en,pl,Kingmaker,\n', encoding='utf-8-sig')
        assert service.import_tm_file(project, fixture) == 2
        assert len(service.translation_memory.list_for_languages('en', 'pl')) == 1
        assert len(service.translation_memory.list_for_languages('pl', 'en')) == 1
        assert service.import_tm_file(project, fixture) == 0
    finally:
        service.close()


def test_pretranslation_does_not_apply_stale_matches_to_different_source(tmp_path: Path):
    """Raport ze starszej migawki nie może pretranslować niezwiązanego tekstu."""
    p1 = ProjectService(tmp_path / 'first.sqlite')
    p2 = ProjectService(tmp_path / 'second.sqlite')
    try:
        a = p1.create_project('A', 'en', 'pl', 'txt')
        b = p2.create_project('B', 'en', 'pl', 'txt')
        src1, src2 = tmp_path / 'a.txt', tmp_path / 'b.txt'
        src1.write_text('Open the gate.\n', encoding='utf-8')
        src2.write_text('Kill the dragon.\n', encoding='utf-8')
        p1.import_file_async(a, src1).result(timeout=5)
        p2.import_file_async(b, src2).result(timeout=5)
        add_entry(p1, 'Open the gate.', 'Otwórz bramę.')
        stale = p1.analyze_project_tm(a, mode='sequential')
        with pytest.raises(ValueError, match='does not belong'):
            p2.apply_tm_matches(b, stale)
        assert p2.list_segments(b.id)[0].target == ''
    finally:
        p1.close(); p2.close()


def test_tm_csv_quotes_newlines_placeholders_survive_roundtrip(tmp_path: Path):
    from gamecat.models.translation_memory import TranslationMemoryEntry
    from gamecat.tm.exchange import read_tm
    source = '"Hello", {name}\nNext line, please.'
    target = '„Witaj”, {name}\nNastępna linia, proszę.'
    original = [TranslationMemoryEntry(source, target, 'en', 'pl')]
    for suffix in ('.csv', '.json'):
        path = tmp_path / f'export{suffix}'
        assert write_tm(path, original) == 1
        result = read_tm(path)
        assert len(result) == 1
        assert (result[0].source, result[0].target) == (source, target)
