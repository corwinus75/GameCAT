from pathlib import Path
import pytest

from gamecat.models.segment import Segment, SegmentStatus
from gamecat.search.operations import SearchQuery, filter_segments, preview_replacements
from gamecat.services.project_service import ProjectService


def data():
    return [
        Segment('The sword', 2, target='Stary miecz', status='TRANSLATED', id=11),
        Segment('A SWORD', 1, target='', status='NEW', id=12),
        Segment('Swordfish', 3, target='Ryba', status='APPROVED', id=13),
        Segment('Dragon', 4, target='Smok', status='REVIEWED', id=14),
    ]


def test_scope_case_regex_and_sort():
    rows = data()
    assert [s.id for s in filter_segments(rows, SearchQuery('sword', scope='source'))] == [12, 11, 13]
    assert [s.id for s in filter_segments(rows, SearchQuery(r'\\bsword\\b', scope='source', regex=True))] == []
    assert [s.id for s in filter_segments(rows, SearchQuery(r'\bsword\b', scope='source', regex=True))] == [12, 11]
    assert [s.id for s in filter_segments(rows, SearchQuery('miecz', scope='target'))] == [11]
    assert [s.id for s in filter_segments(rows, SearchQuery('SWORD', scope='source', case_sensitive=True))] == [12]
    assert [s.id for s in filter_segments(rows, SearchQuery(sort='source'))] == [12, 14, 13, 11]
    assert [s.id for s in filter_segments(rows, SearchQuery(sort='position', descending=True))] == [14, 13, 11, 12]


def test_quality_filters_and_status_are_intersection():
    rows = data()
    assert [s.id for s in filter_segments(rows, SearchQuery(quality='untranslated'))] == [12]
    assert [s.id for s in filter_segments(rows, SearchQuery(quality='qa_errors'), qa_error_ids={13})] == [13]
    assert [s.id for s in filter_segments(rows, SearchQuery(quality='tm_match'), tm_match_ids={11, 12})] == [12, 11]
    assert [s.id for s in filter_segments(rows, SearchQuery(status='APPROVED', quality='qa_errors'), qa_error_ids={13, 14})] == [13]


def test_regex_invalid_and_empty_search():
    with pytest.raises(ValueError, match='regex'):
        filter_segments(data(), SearchQuery('(', regex=True))
    assert len(filter_segments(data(), SearchQuery(''))) == 4


def test_replace_preview_protects_reviewed_and_approved_and_literal_backslash():
    rows = data()
    rows[0].target = r'ABC \1 ABC'
    preview = preview_replacements(rows, 'ABC', r'\1', regex=False)
    assert len(preview) == 1
    assert preview[0].target == r'\1 \1 \1'
    assert preview[0].occurrences == 2
    assert preview_replacements(rows, 'Smok', 'SMOK', regex=False) == []
    assert len(preview_replacements(rows, 'Smok', 'SMOK', regex=False, include_reviewed=True)) == 1
    with pytest.raises(ValueError, match='regex'):
        preview_replacements(rows, '(', 'abc', regex=True)
    with pytest.raises(ValueError, match='replacement'):
        preview_replacements(rows, '(ABC)', r'\9', regex=True)


def test_regex_replacement_expands_capture_groups():
    rows = data()
    preview = preview_replacements(rows, r'(Stary) (miecz)', r'\2 (\1)', regex=True)
    assert preview[0].target == 'miecz (Stary)'
    assert preview[0].segment_id == 11


def test_bulk_replace_is_atomic_scoped_and_flushes_pending_edits(tmp_path: Path):
    service = ProjectService(tmp_path / 'cat.db', autosave_debounce_seconds=5)
    p = service.create_project('one', 'en', 'pl', 'txt')
    other = service.create_project('two', 'en', 'pl', 'txt')
    a, b = service.segments.create_many([
        Segment('Hello', 1, target='Kot', project_id=p.id),
        Segment('Next', 2, target='Pies', status='REVIEWED', project_id=p.id),
    ])
    foreign = service.segments.create(Segment('Other', 1, target='Kot', project_id=other.id))
    try:
        a.target = 'Kot nowy'
        service.queue_segment_save(a)
        assert service.replace_targets(p, {a.id: 'Kot nowy!'}) == 1
        assert service.segments.get(a.id).target == 'Kot nowy!'
        with pytest.raises(ValueError):
            service.replace_targets(p, {a.id: 'Z', foreign.id: 'X'})
        assert service.segments.get(a.id).target == 'Kot nowy!'
        assert service.segments.get(foreign.id).target == 'Kot'
        with pytest.raises(ValueError, match='reviewed'):
            service.replace_targets(p, {b.id: 'X'})
        assert service.replace_targets(p, {b.id: 'X'}, include_reviewed=True) == 1
        assert service.segments.get(b.id).target == 'X'
    finally:
        service.close()


def test_editing_approved_target_requires_new_review(tmp_path: Path):
    service = ProjectService(tmp_path / 'statuses.db')
    project = service.create_project('one', 'en', 'pl', 'txt')
    approved = service.segments.create(Segment('Yes', 1, target='Tak', status='APPROVED', project_id=project.id))
    reviewed = service.segments.create(Segment('No', 2, target='Nie', status='REVIEWED', project_id=project.id))
    try:
        assert service.replace_targets(project, {approved.id: 'Zgoda', reviewed.id: 'Odmowa'}, include_reviewed=True) == 2
        assert service.segments.get(approved.id).status == SegmentStatus.TRANSLATED
        assert service.segments.get(reviewed.id).status == SegmentStatus.TRANSLATED
    finally:
        service.close()


def test_empty_target_reverts_draft_to_new(tmp_path: Path):
    service = ProjectService(tmp_path / 'statuses.db')
    project = service.create_project('one', 'en', 'pl', 'txt')
    draft = service.segments.create(Segment('Yes', 1, target='Tak', status='TRANSLATED', project_id=project.id))
    try:
        assert service.replace_targets(project, {draft.id: ''}) == 1
        assert service.segments.get(draft.id).status == SegmentStatus.NEW
    finally:
        service.close()
