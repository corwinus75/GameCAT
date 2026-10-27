"""Ręczny workflow zapisu tłumaczeń z historią; dotychczasowe API importu pozostaje zgodne."""
from pathlib import Path

import pytest

from gamecat.models.segment import Segment, SegmentStatus
from gamecat.services.project_service import ProjectService


def test_explicit_actions_atomic_and_ordered(tmp_path: Path):
    db = tmp_path / 'p.sqlite'
    service = ProjectService(db)
    project = service.create_project('Demo', 'en', 'pl', 'txt')
    segment = service.segments.create(Segment('Hello', 1, project_id=project.id))
    try:
        # RAM-only edits MUST NOT get into persistent project data.
        segment.target = 'Robocze'
        assert service.segments.get(segment.id).target == ''
        for status, text in [('TRANSLATED','Cześć'),('REVIEWED','Witaj'),('APPROVED','Witam')]:
            saved = service.commit_segment_action(project, segment.id, text, status)
            assert saved.target == text
            assert saved.status == SegmentStatus(status)
        journal = service.segment_history(project, segment.id)
        assert [(e['status'],e['target']) for e in journal] == [
            ('APPROVED','Witam'), ('REVIEWED','Witaj'), ('TRANSLATED','Cześć')]
        assert all('T' in entry['created_at'] for entry in journal)
        with pytest.raises(ValueError):
            service.commit_segment_action(project,segment.id,'',SegmentStatus.APPROVED)
        assert service.segment_history(project, segment.id) == journal
    finally:
        service.close()
    reopened = ProjectService(db)
    try:
        assert len(reopened.segment_history(project, segment.id)) == 3
        assert reopened.segments.get(segment.id).target == 'Witam'
    finally:
        reopened.close()


def test_project_scoped_history_and_rollback(tmp_path):
    service = ProjectService(tmp_path/'data.sqlite')
    first = service.create_project('A','en','pl','txt')
    second = service.create_project('B','en','pl','txt')
    seg = service.segments.create(Segment('A', 1, project_id=first.id))
    try:
        with pytest.raises(KeyError):
            service.commit_segment_action(second, seg.id, 'nonsense', SegmentStatus.TRANSLATED)
        assert service.segment_history(first,seg.id) == []
        assert service.segments.get(seg.id).target == ''
        # Explicit repeated click is an intentional new history event.
        for _ in range(2):
            service.commit_segment_action(first, seg.id, 'X', SegmentStatus.TRANSLATED)
        assert len(service.segment_history(first, seg.id)) == 2
        assert service.segment_history(second, seg.id) == []
    finally:
        service.close()


def test_history_migration_idempotent(tmp_path):
    path=tmp_path/'old.sqlite'
    a=ProjectService(path)
    project=a.create_project('A','en','pl','txt')
    seg=a.segments.create(Segment('x',1,project_id=project.id))
    a.close()
    for _ in range(2):
        b=ProjectService(path)
        try:
            assert b.segment_history(project,seg.id)==[]
            assert b.connection.fetchone('SELECT COUNT(*) FROM sqlite_master WHERE type=\'table\' AND name=\'segment_history\'')[0]==1
        finally:
            b.close()


def test_history_insert_failure_rolls_back_translation(tmp_path):
    from gamecat.exceptions import DatabaseError
    service=ProjectService(tmp_path/'rollback.sqlite')
    project=service.create_project('Demo','en','pl','txt')
    segment=service.segments.create(Segment('A',1,project_id=project.id))
    try:
        with service.connection:
            service.connection.execute("""CREATE TRIGGER block_history BEFORE INSERT ON segment_history
                BEGIN SELECT RAISE(ABORT,'history refused'); END""")
        with pytest.raises(DatabaseError):
            service.commit_segment_action(project,segment.id,'Nie powinno się zapisać','TRANSLATED')
        assert service.segments.get(segment.id).target == ''
        assert service.segment_history(project,segment.id)==[]
    finally:
        service.close()
