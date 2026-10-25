from __future__ import annotations
from pathlib import Path
from concurrent.futures import Future
from gamecat.concurrency.io_workers import IOWorkerPool
from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema
from gamecat.database.repositories import GlossaryRepository, ProjectRepository, SegmentRepository
from gamecat.exporters.txt_exporter import export_txt
from gamecat.exporters.csv_exporter import export_csv
from gamecat.exporters.json_exporter import export_json
from gamecat.importers.txt_importer import import_txt
from gamecat.importers.csv_importer import import_csv
from gamecat.importers.json_importer import import_json
from gamecat.models.project import Project
from gamecat.models.glossary import GlossaryEntry
from gamecat.models.segment import Segment
from gamecat.exceptions import ImportFormatError


class ProjectService:
    """High-level project workflow independent of the GUI."""
    def __init__(self, database_path: Path, max_io_workers: int = 4):
        self.connection = open_database(database_path)
        initialize_schema(self.connection)
        self.projects = ProjectRepository(self.connection)
        self.segments = SegmentRepository(self.connection)
        self.glossary = GlossaryRepository(self.connection)
        self.io = IOWorkerPool(max_io_workers)

    def create_project(self, name: str, source_language: str, target_language: str, source_format: str) -> Project:
        return self.projects.create(Project(name, source_language, target_language, source_format))

    def load_project(self, project_id: int | None) -> Project:
        if project_id is None:
            raise ValueError('project_id is required')
        return self.projects.get(project_id)

    def list_projects(self) -> list[Project]:
        return self.projects.list_all()

    def list_segments(self, project_id: int | None) -> list[Segment]:
        if project_id is None:
            return []
        return self.segments.list_for_project(project_id)

    def list_glossary(self, project_id: int | None) -> list[GlossaryEntry]:
        return self.glossary.list_for_project(project_id)

    def _import_file(
        self,
        project: Project,
        path: Path,
        csv_columns: tuple[str, str, str | None] | None = None,
    ) -> list[Segment]:
        if project.id is None:
            raise ValueError('project must be persisted before import')
        suffix = path.suffix.casefold()
        if suffix == '.txt':
            imported = import_txt(path)
        elif suffix == '.csv':
            key_column, source_column, target_column = csv_columns or ('id', 'source', 'target')
            imported = import_csv(path, key_column, source_column, target_column)
        elif suffix == '.json':
            imported = import_json(path)
        else:
            raise ValueError(f'Unsupported import format: {suffix}')
        result: list[Segment] = []
        try:
            for item in imported:
                result.append(self.segments.create(Segment(item.source, item.position, item.key, item.target, project_id=project.id)))
        except (UnicodeError, ValueError, KeyError) as exc:
            raise ImportFormatError(f'Cannot import {path.name}: {exc}') from exc
        return result

    def import_file_async(
        self,
        project: Project,
        path: Path,
        csv_columns: tuple[str, str, str | None] | None = None,
    ) -> Future[list[Segment]]:
        return self.io.submit(self._import_file, project, path, csv_columns)

    def save_segment(self, segment: Segment) -> None:
        self.segments.update(segment)

    @staticmethod
    def _export_file(segments: list[Segment], path: Path, format_name: str) -> None:
        if format_name == 'txt':
            export_txt(segments, path)
        elif format_name == 'csv':
            export_csv(segments, path)
        elif format_name == 'json':
            export_json(segments, path, 'list')
        else:
            raise ValueError(f'Unsupported export format: {format_name}')

    def export_file_async(self, segments: list[Segment], path: Path, format_name: str) -> Future[None]:
        return self.io.submit(self._export_file, segments, path, format_name)

    def close(self) -> None:
        self.io.close()
        self.connection.close()
