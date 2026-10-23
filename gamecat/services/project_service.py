from __future__ import annotations
from pathlib import Path
from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema
from gamecat.database.repositories import ProjectRepository, SegmentRepository
from gamecat.exporters.txt_exporter import export_txt
from gamecat.importers.txt_importer import import_txt
from gamecat.models.project import Project
from gamecat.models.segment import Segment
from gamecat.exceptions import ImportFormatError
from gamecat.utils.decorators import measure_time
from gamecat.utils.decorators import retry
from gamecat.utils.decorators import requires_project
from gamecat.importers.csv_importer import import_csv
from gamecat.importers.json_importer import import_json
from gamecat.exporters.csv_exporter import export_csv
from gamecat.exporters.json_exporter import export_json


class ProjectService:
    """Warstwa obsługi projektów — niezależna od GUI."""
    def __init__(self, database_path: Path, max_io_workers: int = 4):
        self.connection = open_database(database_path)
        initialize_schema(self.connection)
        self.projects = ProjectRepository(self.connection)
        self.segments = SegmentRepository(self.connection)
        self.current_project: Project | None = None

    def create_project(self, name: str, source_language: str, target_language: str, source_format: str) -> Project:
        self.current_project = self.projects.create(Project(name, source_language, target_language, source_format))
        return self.current_project

    def load_project(self, project_id: int) -> Project:
        self.current_project = self.projects.get(project_id)
        return self.current_project

    def list_segments(self, project_id: int | None) -> list[Segment]:
        return self.segments.list_for_project(project_id) if project_id is not None else []

    @measure_time
    @retry(attempts=2, delay=0.05)

    def _import_file(self, project: Project, path: Path) -> list[Segment]:
        if project.id is None:
            raise ValueError('Projekt musi być zapisany')
        suffix = path.suffix.casefold()
        if suffix == '.txt':
            imported = import_txt(path)
        elif suffix == '.csv':
            imported = import_csv(path, 'id', 'source', 'target')
        elif suffix == '.json':
            imported = import_json(path)

        else:
            raise ValueError(f'Nieobsługiwany import: {suffix}')
        result = []
        try:
            for item in imported:
                result.append(self.segments.create(Segment(item.source, item.position, item.key, item.target, project_id=project.id)))
        except (UnicodeError, ValueError, KeyError) as exc:
            raise ImportFormatError(f'Nie można zaimportować {path.name}: {exc}') from exc
        return result

    @requires_project
    def import_file(self, project: Project, path: Path) -> list[Segment]:
        return self._import_file(project, path)

    @requires_project

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
            raise ValueError(f'Nieobsługiwany eksport: {format_name}')

    @requires_project

    def export_file(self, segments: list[Segment], path: Path, format_name: str) -> None:
        self._export_file(segments, path, format_name)


    def close(self) -> None:
        self.connection.close()
