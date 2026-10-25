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
    conn = open_database(tmp_path / 'db.sqlite')
    initialize_schema(conn)
    p = ProjectRepository(conn).create(Project('P', 'en', 'pl', 'txt'))
    repo = SegmentRepository(conn)
    s = repo.create(Segment('Hello', 1, project_id=p.id))

    q = SaveQueue(repo)
    s.target = 'A'
    q.enqueue(s)
    repo.update(s)
    q.flush()
    q.close()
    assert repo.get(s.id).target == 'A'


def test_io_worker_pool_returns_future():
    pool=IOWorkerPool(max_workers=2)
    assert pool.submit(lambda x: x+1, 3).result(timeout=2) == 4
    pool.close()


def test_parallel_repositories_share_one_transaction_lock(tmp_path: Path):
    """Two repositories must not commit each other's transactions."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    conn = open_database(tmp_path / 'shared.sqlite')
    initialize_schema(conn)
    projects = ProjectRepository(conn)
    segments = SegmentRepository(conn)
    p = projects.create(Project('P', 'en', 'pl', 'txt'))
    s = segments.create(Segment('Hello', 1, project_id=p.id))
    start = Barrier(4)

    def writer(index):
        start.wait(timeout=3)
        for _ in range(100):
            if index % 2:
                projects.update(p)
            else:
                segments.update(s)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(writer, i) for i in range(4)]
        for future in futures:
            future.result(timeout=10)

    assert segments.get(s.id).source == 'Hello'
    conn.close()


def test_save_queue_worker_error_does_not_hang_flush():
    import pytest

    class BrokenRepository:
        def update(self, segment):
            raise ValueError('simulated SQLite error')

    q = SaveQueue(BrokenRepository())
    q.enqueue(Segment('first', 1, id=1, project_id=1))
    q.enqueue(Segment('second', 2, id=2, project_id=1))
    with pytest.raises(RuntimeError, match='segment write failed') as exc_info:
        q.flush()
    assert isinstance(exc_info.value.__cause__, ValueError)
    with pytest.raises(RuntimeError, match='segment write failed'):
        q.close()
    assert not q._thread.is_alive()
