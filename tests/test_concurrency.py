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
