from pathlib import Path

import pytest

from gamecat.models.segment import SegmentStatus
from gamecat.services.project_service import ProjectService


def _project_with_source(tmp_path: Path):
    service = ProjectService(tmp_path / 'project.sqlite')
    project = service.create_project('Demo', 'en', 'pl', 'txt')
    src = tmp_path / 'source.csv'
    src.write_text('id,source\nA1,Hello\nA2,World\n', encoding='utf-8')
    service.import_file_async(project, src, ('id', 'source', None)).result(timeout=5)
    return service, project


def test_import_translation_txt_updates_targets_by_position(tmp_path: Path):
    service, project = _project_with_source(tmp_path)
    translation = tmp_path / 'pl.txt'
    translation.write_text('Cześć\nŚwiat\n', encoding='utf-8')
    try:
        result = service.import_translation_file_async(project, translation).result(timeout=5)
        rows = service.list_segments(project.id)
        assert result.updated == 2
        assert result.unmatched == 0
        assert [row.source for row in rows] == ['Hello', 'World']
        assert [row.target for row in rows] == ['Cześć', 'Świat']
        assert all(row.status is SegmentStatus.TRANSLATED for row in rows)
    finally:
        service.close()


def test_import_translation_csv_updates_by_key_without_touching_source(tmp_path: Path):
    service, project = _project_with_source(tmp_path)
    translation = tmp_path / 'pl.csv'
    translation.write_text('string_id,polish\nA2,Świat\nA1,Cześć\n', encoding='utf-8')
    try:
        result = service.import_translation_file_async(
            project,
            translation,
            csv_columns=('string_id', 'polish'),
        ).result(timeout=5)
        rows = service.list_segments(project.id)
        assert result.updated == 2
        assert [(row.key, row.source, row.target) for row in rows] == [
            ('A1', 'Hello', 'Cześć'),
            ('A2', 'World', 'Świat'),
        ]
    finally:
        service.close()


def test_import_translation_json_dict_matches_existing_keys_and_reports_unknown(tmp_path: Path):
    service, project = _project_with_source(tmp_path)
    translation = tmp_path / 'pl.json'
    translation.write_text('{"A1": "Cześć", "MISSING": "Brak"}', encoding='utf-8')
    try:
        result = service.import_translation_file_async(project, translation).result(timeout=5)
        rows = service.list_segments(project.id)
        assert result.updated == 1
        assert result.unmatched == 1
        assert rows[0].target == 'Cześć'
        assert rows[1].target == ''
    finally:
        service.close()


def test_import_translation_txt_rejects_more_rows_than_project(tmp_path: Path):
    service, project = _project_with_source(tmp_path)
    translation = tmp_path / 'pl.txt'
    translation.write_text('a\nb\nc\n', encoding='utf-8')
    try:
        with pytest.raises(ValueError, match='więcej wpisów'):
            service.import_translation_file_async(project, translation).result(timeout=5)
    finally:
        service.close()


def test_reimport_changed_translation_demotes_approved_segment(tmp_path: Path):
    """An imported revision must not retain a human approval of older text."""
    service, project = _project_with_source(tmp_path)
    incoming = tmp_path / 'translation.txt'
    try:
        first = service.list_segments(project.id)[0]
        first.target = 'Witaj'
        first.status = SegmentStatus.APPROVED
        service.save_segment(first)
        incoming.write_text('Cześć\n\n', encoding='utf-8')

        service.import_translation_file_async(project, incoming).result(timeout=5)

        after = service.list_segments(project.id)[0]
        assert after.source == 'Hello'
        assert after.target == 'Cześć'
        assert after.status is SegmentStatus.TRANSLATED
    finally:
        service.close()


def test_reimport_unchanged_translation_preserves_reviewed_status(tmp_path: Path):
    """Identical imports should not invalidate a completed human review."""
    service, project = _project_with_source(tmp_path)
    incoming = tmp_path / 'translation.txt'
    try:
        first = service.list_segments(project.id)[0]
        first.target = 'Witaj'
        first.status = SegmentStatus.REVIEWED
        service.save_segment(first)
        incoming.write_text('Witaj\n\n', encoding='utf-8')

        service.import_translation_file_async(project, incoming).result(timeout=5)

        assert service.list_segments(project.id)[0].status is SegmentStatus.REVIEWED
    finally:
        service.close()
