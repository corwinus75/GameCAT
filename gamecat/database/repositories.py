from __future__ import annotations
from datetime import datetime
import sqlite3
from gamecat.models.project import Project
from gamecat.models.segment import Segment
from gamecat.models.glossary import GlossaryEntry


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class ProjectRepository:
    def __init__(self, connection: sqlite3.Connection): self.connection = connection
    def create(self, project: Project) -> Project:
        with self.connection:
            cur = self.connection.execute(
                'INSERT INTO projects(name,source_language,target_language,source_format,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                (project.name, project.source_language, project.target_language, project.source_format, project.created_at.isoformat(), project.updated_at.isoformat()))
        project.id = cur.lastrowid
        return project
    def get(self, project_id: int) -> Project:
        row = self.connection.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        if row is None: raise KeyError(project_id)
        return Project(row['name'], row['source_language'], row['target_language'], row['source_format'], row['id'], _dt(row['created_at']), _dt(row['updated_at']))
    def list_all(self) -> list[Project]:
        rows = self.connection.execute('SELECT id FROM projects ORDER BY id').fetchall()
        return [self.get(row['id']) for row in rows]
    def update(self, project: Project) -> None:
        if project.id is None: raise ValueError('project has no id')
        with self.connection:
            self.connection.execute('UPDATE projects SET name=?,source_language=?,target_language=?,source_format=?,updated_at=? WHERE id=?',
                                    (project.name, project.source_language, project.target_language, project.source_format, project.updated_at.isoformat(), project.id))


class SegmentRepository:
    def __init__(self, connection: sqlite3.Connection): self.connection = connection
    def create(self, segment: Segment) -> Segment:
        if segment.project_id is None: raise ValueError('segment requires project_id')
        with self.connection:
            cur = self.connection.execute('''INSERT INTO segments(project_id,position,key,source,target,status,comment,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)''', (segment.project_id, segment.position, segment.key, segment.source, segment.target, segment.status.value, segment.comment, segment.created_at.isoformat(), segment.updated_at.isoformat()))
        segment.id = cur.lastrowid
        return segment
    def _from_row(self, row: sqlite3.Row) -> Segment:
        return Segment(row['source'], row['position'], row['key'], row['target'], row['status'], row['comment'], row['id'], row['project_id'], _dt(row['created_at']), _dt(row['updated_at']))
    def get(self, segment_id: int | None) -> Segment:
        if segment_id is None: raise KeyError(segment_id)
        row = self.connection.execute('SELECT * FROM segments WHERE id=?', (segment_id,)).fetchone()
        if row is None: raise KeyError(segment_id)
        return self._from_row(row)
    def list_for_project(self, project_id: int) -> list[Segment]:
        rows = self.connection.execute('SELECT * FROM segments WHERE project_id=? ORDER BY position,id', (project_id,)).fetchall()
        return [self._from_row(r) for r in rows]
    def update(self, segment: Segment) -> None:
        if segment.id is None: raise ValueError('segment has no id')
        with self.connection:
            self.connection.execute('UPDATE segments SET target=?,status=?,comment=?,updated_at=? WHERE id=?',
                                    (segment.target, segment.status.value, segment.comment, segment.updated_at.isoformat(), segment.id))


class GlossaryRepository:
    def __init__(self, connection: sqlite3.Connection): self.connection = connection
    def create(self, entry: GlossaryEntry) -> GlossaryEntry:
        with self.connection:
            cur = self.connection.execute('INSERT INTO glossary(project_id,source_term,target_term,description,case_sensitive) VALUES(?,?,?,?,?)',
                                          (entry.project_id, entry.source_term, entry.target_term, entry.description, int(entry.case_sensitive)))
        entry.id = cur.lastrowid; return entry
    def list_for_project(self, project_id: int | None) -> list[GlossaryEntry]:
        if project_id is None:
            rows = self.connection.execute('SELECT * FROM glossary ORDER BY id').fetchall()
        else:
            rows = self.connection.execute('SELECT * FROM glossary WHERE project_id=? OR project_id IS NULL ORDER BY id', (project_id,)).fetchall()
        return [GlossaryEntry(r['source_term'], r['target_term'], r['description'], bool(r['case_sensitive']), r['id'], r['project_id']) for r in rows]

