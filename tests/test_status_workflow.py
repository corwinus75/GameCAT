from pathlib import Path

from gamecat.models.segment import Segment, SegmentStatus
from gamecat.services.project_service import ProjectService
from gamecat.workflow.status import ProjectProgress, confirmed_translation_status


def test_confirmed_translation_promotes_only_new_status():
    assert confirmed_translation_status(SegmentStatus.NEW) is SegmentStatus.TRANSLATED
    assert confirmed_translation_status(SegmentStatus.TRANSLATED) is SegmentStatus.TRANSLATED
    assert confirmed_translation_status(SegmentStatus.REVIEWED) is SegmentStatus.REVIEWED
    assert confirmed_translation_status(SegmentStatus.APPROVED) is SegmentStatus.APPROVED


def test_project_progress_uses_cumulative_workflow_counts():
    progress = ProjectProgress.from_counts(
        {
            SegmentStatus.NEW: 4,
            SegmentStatus.TRANSLATED: 3,
            SegmentStatus.REVIEWED: 2,
            SegmentStatus.APPROVED: 1,
        }
    )

    assert progress.total == 10
    assert progress.new == 4
    assert progress.translated == 3
    assert progress.reviewed == 2
    assert progress.approved == 1
    assert progress.translated_or_better == 6
    assert progress.reviewed_or_better == 3
    assert progress.translation_percent == 60.0
    assert progress.review_percent == 30.0
    assert progress.approval_percent == 10.0


def test_service_bulk_status_change_persists_and_reports_progress(tmp_path: Path):
    service = ProjectService(tmp_path / 'project.sqlite', autosave_debounce_seconds=0.01)
    project = service.create_project('Demo', 'en', 'pl', 'txt')
    try:
        rows = service.segments.create_many(
            [
                Segment('One', 1, target='Jeden', status=SegmentStatus.TRANSLATED, project_id=project.id),
                Segment('Two', 2, target='Dwa', status=SegmentStatus.TRANSLATED, project_id=project.id),
                Segment('Three', 3, project_id=project.id),
            ]
        )

        updated = service.set_segment_statuses(rows[:2], SegmentStatus.REVIEWED)

        assert updated == 2
        reloaded = service.list_segments(project.id)
        assert [s.status for s in reloaded] == [
            SegmentStatus.REVIEWED,
            SegmentStatus.REVIEWED,
            SegmentStatus.NEW,
        ]
        progress = service.project_progress(project.id)
        assert progress.total == 3
        assert progress.new == 1
        assert progress.reviewed == 2
        assert progress.translated_or_better == 2
        assert progress.reviewed_or_better == 2
    finally:
        service.close()


def test_bulk_status_change_flushes_queued_target_before_direct_update(tmp_path: Path):
    service = ProjectService(tmp_path / 'project.sqlite', autosave_debounce_seconds=0.5)
    project = service.create_project('Demo', 'en', 'pl', 'txt')
    try:
        segment = service.segments.create(Segment('Hello', 1, project_id=project.id))
        segment.target = 'Cześć'
        service.queue_segment_save(segment)

        service.set_segment_statuses([segment], SegmentStatus.APPROVED)

        loaded = service.segments.get(segment.id)
        assert loaded.target == 'Cześć'
        assert loaded.status is SegmentStatus.APPROVED
    finally:
        service.close()
