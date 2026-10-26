import json
from pathlib import Path

import pytest

from gamecat.database.connection import open_database
from gamecat.database.repositories import ProjectRepository, SegmentRepository
from gamecat.database.schema import initialize_schema
from gamecat.database.segment_iterator import SegmentBatchIterator
from gamecat.exceptions import ImportFormatError
from gamecat.models.project import Project
from gamecat.models.segment import Segment
from gamecat.services.project_service import ProjectService


def _repo_with_segments(tmp_path: Path, count: int) -> tuple[SegmentRepository, int]:
    conn = open_database(tmp_path / 'db.sqlite'); initialize_schema(conn)
    project = ProjectRepository(conn).create(Project('P', 'en', 'pl', 'txt'))
    repo = SegmentRepository(conn)
    repo.create_many(Segment(f's{i}', i, project_id=project.id) for i in range(1, count + 1))
    return repo, project.id


def test_batch_iterator_reads_all_segments_in_order_in_batches(tmp_path: Path):
    repo, project_id = _repo_with_segments(tmp_path, 23)
    iterator = repo.iter_for_project(project_id, batch_size=5)
    assert iter(iterator) is iterator
    sources = [segment.source for segment in iterator]
    assert sources == [f's{i}' for i in range(1, 24)]
    assert iterator.batches_fetched == 5
    with pytest.raises(StopIteration):
        next(iterator)


def test_batch_iterator_handles_duplicate_positions(tmp_path: Path):
    repo, project_id = _repo_with_segments(tmp_path, 0)
    repo.create_many(Segment(f'dup{i}', 1, project_id=project_id) for i in range(7))
    assert len(list(repo.iter_for_project(project_id, batch_size=3))) == 7


def test_batch_iterator_on_empty_project(tmp_path: Path):
    repo, project_id = _repo_with_segments(tmp_path, 0)
    assert list(repo.iter_for_project(project_id)) == []


def test_batch_iterator_rejects_invalid_batch_size(tmp_path: Path):
    repo, project_id = _repo_with_segments(tmp_path, 1)
    with pytest.raises(ValueError):
        SegmentBatchIterator(repo.connection, project_id, repo._from_row, batch_size=0)


def test_failed_import_is_rolled_back(tmp_path: Path):
    src = tmp_path / 'broken.json'
    src.write_text(json.dumps([{'source': 'ok'}, {'no_source': 'x'}]), encoding='utf-8')
    service = ProjectService(tmp_path / 'p.sqlite')
    project = service.create_project('P', 'en', 'pl', 'json')
    try:
        with pytest.raises(ImportFormatError):
            service.import_file_async(project, src).result(timeout=5)
        assert service.segments.count_for_project(project.id) == 0
    finally:
        service.close()


def test_failed_translation_import_changes_nothing(tmp_path: Path):
    src = tmp_path / 'src.json'
    src.write_text(json.dumps([{'key': 'A', 'source': 'One'}, {'key': 'B', 'source': 'Two'},
                               {'key': 'B', 'source': 'Two again'}]), encoding='utf-8')
    tr = tmp_path / 'tr.json'
    tr.write_text(json.dumps({'A': 'Jeden', 'B': 'Dwa'}), encoding='utf-8')
    service = ProjectService(tmp_path / 'p.sqlite')
    project = service.create_project('P', 'en', 'pl', 'json')
    try:
        service.import_file_async(project, src).result(timeout=5)
        with pytest.raises(ValueError, match='Niejednoznaczny'):
            service.import_translation_file_async(project, tr).result(timeout=5)
        assert [s.target for s in service.list_segments(project.id)] == ['', '', '']
    finally:
        service.close()


def test_export_project_streams_from_database(tmp_path: Path):
    src = tmp_path / 'src.txt'; src.write_text('a\nb\nc\n', encoding='utf-8')
    out = tmp_path / 'out.csv'
    service = ProjectService(tmp_path / 'p.sqlite')
    project = service.create_project('P', 'en', 'pl', 'txt')
    try:
        service.import_file_async(project, src).result(timeout=5)
        assert service.export_project_async(project, out, 'csv').result(timeout=5) == 3
        assert out.read_text(encoding='utf-8').count('\n') == 4
    finally:
        service.close()


def test_run_project_qa_sees_pending_autosave(tmp_path: Path):
    src = tmp_path / 'src.txt'; src.write_text('Hello {name}\n', encoding='utf-8')
    service = ProjectService(tmp_path / 'p.sqlite', autosave_debounce_seconds=0.05)
    project = service.create_project('P', 'en', 'pl', 'txt')
    try:
        segment, = service.import_file_async(project, src).result(timeout=5)
        segment.target = 'Witaj'
        service.queue_segment_save(segment)
        report = service.run_project_qa(project)
        assert report.segment_count == 1
        assert any(i.code == 'placeholder-missing' for i in report.results[0].issues)
    finally:
        service.close()
