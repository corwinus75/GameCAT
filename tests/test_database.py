from pathlib import Path
from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema
from gamecat.database.repositories import ProjectRepository, SegmentRepository
from gamecat.models.project import Project
from gamecat.models.segment import Segment, SegmentStatus


def test_project_and_segment_crud(tmp_path: Path):
    conn = open_database(tmp_path / 'db.sqlite')
    initialize_schema(conn)
    projects = ProjectRepository(conn)
    segments = SegmentRepository(conn)
    p = projects.create(Project('P', 'en', 'pl', 'txt'))
    assert p.id is not None
    assert projects.get(p.id).name == 'P'
    s2 = segments.create(Segment('two', 2, project_id=p.id))
    s1 = segments.create(Segment('one', 1, project_id=p.id))
    assert [s.source for s in segments.list_for_project(p.id)] == ['one', 'two']
    s1.target = 'jeden'; s1.status = SegmentStatus.TRANSLATED
    segments.update(s1)
    loaded = segments.get(s1.id)
    assert loaded.target == 'jeden' and loaded.status is SegmentStatus.TRANSLATED


def test_empty_database_lists_are_empty(tmp_path: Path):
    conn = open_database(tmp_path / 'empty.sqlite')
    initialize_schema(conn)
    assert ProjectRepository(conn).list_all() == []
