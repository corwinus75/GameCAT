from pathlib import Path
from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema
from gamecat.database.repositories import ProjectRepository, SegmentRepository
from gamecat.models.project import Project
from gamecat.models.segment import Segment
from gamecat.concurrency.save_queue import SaveQueue
from gamecat.concurrency.io_workers import IOWorkerPool


def test_save_queue_keeps_last_value(tmp_path: Path):
    conn=open_database(tmp_path/'db.sqlite'); initialize_schema(conn)
    p=ProjectRepository(conn).create(Project('P','en','pl','txt'))
    repo=SegmentRepository(conn); s=repo.create(Segment('Hello',1,project_id=p.id))
    q=SaveQueue(repo)
    s.target='A'; q.enqueue(s)
    s.target='B'; q.enqueue(s)
    q.flush(); q.close()
    assert repo.get(s.id).target == 'B'


def test_manual_and_autosave_do_not_break_sqlite(tmp_path: Path):
    conn=open_database(tmp_path/'db.sqlite'); initialize_schema(conn)
    p=ProjectRepository(conn).create(Project('P','en','pl','txt'))
    repo=SegmentRepository(conn); s=repo.create(Segment('Hello',1,project_id=p.id))
    q=SaveQueue(repo); s.target='A'; q.enqueue(s); repo.update(s); q.flush(); q.close()
    assert repo.get(s.id).target == 'A'


def test_io_worker_pool_returns_future():
    pool=IOWorkerPool(max_workers=2)
    assert pool.submit(lambda x: x+1, 3).result(timeout=2) == 4
    pool.close()


def test_save_queue_coalesces_rapid_updates_for_same_segment():
    class RecordingRepository:
        def __init__(self):
            self.saved: list[str] = []

        def update_many(self, segments) -> int:
            segments = list(segments)
            self.saved.extend(segment.target for segment in segments)
            return len(segments)

    repo = RecordingRepository()
    q = SaveQueue(repo, debounce_seconds=0.03)
    segment = Segment('Hello', 1, target='A', id=7, project_id=1)
    q.enqueue(segment)
    segment.target = 'AB'
    q.enqueue(segment)
    segment.target = 'ABC'
    q.enqueue(segment)
    q.flush()
    q.close()

    assert repo.saved == ['ABC']
    assert q.pending_count == 0


def test_project_service_flushes_queued_segment_save(tmp_path: Path):
    from gamecat.services.project_service import ProjectService

    service = ProjectService(tmp_path / 'project.sqlite', autosave_debounce_seconds=0.01)
    project = service.create_project('P', 'en', 'pl', 'txt')
    segment = service.segments.create(Segment('Hello', 1, project_id=project.id))
    segment.target = 'Cześć'

    service.queue_segment_save(segment)
    assert service.pending_save_count >= 1
    service.flush_saves()

    assert service.segments.get(segment.id).target == 'Cześć'
    assert service.pending_save_count == 0
    service.close()


def test_project_service_close_flushes_pending_autosave(tmp_path: Path):
    from gamecat.services.project_service import ProjectService

    db = tmp_path / 'project.sqlite'
    service = ProjectService(db, autosave_debounce_seconds=0.05)
    project = service.create_project('P', 'en', 'pl', 'txt')
    segment = service.segments.create(Segment('Hello', 1, project_id=project.id))
    segment.target = 'Ostatnia zmiana'
    service.queue_segment_save(segment)
    service.close()

    reopened = ProjectService(db)
    try:
        assert reopened.segments.get(segment.id).target == 'Ostatnia zmiana'
    finally:
        reopened.close()


def test_list_segments_flushes_pending_autosave(tmp_path: Path):
    from gamecat.services.project_service import ProjectService

    service = ProjectService(tmp_path / 'project.sqlite', autosave_debounce_seconds=0.2)
    project = service.create_project('P', 'en', 'pl', 'txt')
    segment = service.segments.create(Segment('Hello', 1, project_id=project.id))
    segment.target = 'W kolejce'
    service.queue_segment_save(segment)

    rows = service.list_segments(project.id)

    assert rows[0].target == 'W kolejce'
    assert service.pending_save_count == 0
    service.close()


def test_save_queue_retries_transient_lock():
    import sqlite3

    class LockedOnceRepository:
        def __init__(self):
            self.calls = 0
            self.saved: list[str] = []

        def update_many(self, segments) -> int:
            self.calls += 1
            if self.calls == 1:
                raise sqlite3.OperationalError('database is locked')
            segments = list(segments)
            self.saved.extend(s.target for s in segments)
            return len(segments)

    repo = LockedOnceRepository()
    q = SaveQueue(repo, debounce_seconds=0)
    q.enqueue(Segment('Hello', 1, target='Cześć', id=1, project_id=1))
    q.flush(); q.close()
    assert repo.calls == 2
    assert repo.saved == ['Cześć']
