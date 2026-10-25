from __future__ import annotations
from pathlib import Path
from concurrent.futures import Future
from dataclasses import dataclass
from gamecat.concurrency.io_workers import IOWorkerPool
from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema
from gamecat.database.repositories import GlossaryRepository, ProjectRepository, SegmentRepository, TranslationMemoryRepository
from gamecat.exporters.txt_exporter import export_txt
from gamecat.exporters.csv_exporter import export_csv
from gamecat.exporters.json_exporter import export_json
from gamecat.importers.txt_importer import import_txt
from gamecat.importers.csv_importer import import_csv
from gamecat.importers.json_importer import import_json
from gamecat.importers.translation_importer import (
    ImportedTranslation,
    import_translation_csv,
    import_translation_json,
    import_translation_txt,
)
from gamecat.models.project import Project
from gamecat.models.glossary import GlossaryEntry
from gamecat.models.segment import Segment, SegmentStatus
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.tm.matcher import TMMatch, find_matches
from gamecat.exceptions import ImportFormatError


@dataclass(frozen=True, slots=True)
class TranslationImportResult:
    total: int
    updated: int
    unmatched: int


class ProjectService:
    """High-level project workflow independent of the GUI."""
    def __init__(self, database_path: Path, max_io_workers: int = 4):
        self.connection = open_database(database_path)
        initialize_schema(self.connection)
        self.projects = ProjectRepository(self.connection)
        self.segments = SegmentRepository(self.connection)
        self.glossary = GlossaryRepository(self.connection)
        self.translation_memory = TranslationMemoryRepository(self.connection)
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

    def _import_translation_file(
        self,
        project: Project,
        path: Path,
        csv_columns: tuple[str | None, str] | None = None,
    ) -> TranslationImportResult:
        if project.id is None:
            raise ValueError('project must be persisted before translation import')
        segments = self.list_segments(project.id)
        suffix = path.suffix.casefold()
        if suffix == '.txt':
            imported = list(import_translation_txt(path))
            if len(imported) > len(segments):
                raise ValueError('Plik tłumaczenia zawiera więcej wpisów niż projekt.')
        elif suffix == '.csv':
            key_column, target_column = csv_columns or ('id', 'target')
            imported = list(import_translation_csv(path, key_column, target_column))
        elif suffix == '.json':
            imported = list(import_translation_json(path))
        else:
            raise ValueError(f'Unsupported translation import format: {suffix}')

        by_position = {segment.position: segment for segment in segments}
        by_key: dict[str, Segment] = {}
        duplicate_keys: set[str] = set()
        for segment in segments:
            if segment.key is None:
                continue
            if segment.key in by_key:
                duplicate_keys.add(segment.key)
            else:
                by_key[segment.key] = segment
        for key in duplicate_keys:
            by_key.pop(key, None)

        updated = 0
        unmatched = 0
        for item in imported:
            segment: Segment | None = None
            if item.key is not None:
                if item.key in duplicate_keys:
                    raise ValueError(f'Niejednoznaczny klucz segmentu w projekcie: {item.key}')
                segment = by_key.get(item.key)
            elif item.position is not None:
                segment = by_position.get(item.position)
            if segment is None:
                unmatched += 1
                continue
            segment.target = item.target
            if item.target and segment.status is SegmentStatus.NEW:
                segment.status = SegmentStatus.TRANSLATED
            elif not item.target and segment.status is SegmentStatus.TRANSLATED:
                segment.status = SegmentStatus.NEW
            self.save_segment(segment)
            updated += 1
        return TranslationImportResult(total=len(imported), updated=updated, unmatched=unmatched)

    def import_translation_file_async(
        self,
        project: Project,
        path: Path,
        csv_columns: tuple[str | None, str] | None = None,
    ) -> Future[TranslationImportResult]:
        return self.io.submit(self._import_translation_file, project, path, csv_columns)

    def sync_project_to_tm(self, project: Project) -> int:
        if project.id is None:
            raise ValueError('project must be persisted before TM sync')
        created = 0
        for segment in self.list_segments(project.id):
            if not segment.target.strip():
                continue
            if self.translation_memory.contains_pair(
                segment.source, segment.target, project.source_language, project.target_language
            ):
                continue
            self.translation_memory.create(
                TranslationMemoryEntry(
                    source=segment.source,
                    target=segment.target,
                    source_language=project.source_language,
                    target_language=project.target_language,
                    origin_project=project.name,
                )
            )
            created += 1
        return created

    def find_tm_matches(
        self,
        project: Project,
        source: str,
        limit: int = 5,
        threshold: float = 0.5,
    ) -> list[TMMatch]:
        entries = self.translation_memory.list_for_languages(project.source_language, project.target_language)
        return find_matches(source, entries, limit=limit, threshold=threshold)

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
