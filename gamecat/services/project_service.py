from __future__ import annotations
from pathlib import Path
from collections.abc import Iterable
from concurrent.futures import Future
from dataclasses import dataclass
from gamecat.concurrency.io_workers import IOWorkerPool
from gamecat.concurrency.save_queue import SaveQueue
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
from gamecat.models.glossary import GlossaryTerm
from gamecat.models.segment import Segment, SegmentStatus
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.tm.matcher import TMMatch, find_matches
from gamecat.tm.analysis import ExecutionMode, TMAnalysisReport, analyze
from gamecat.exceptions import ImportFormatError
from gamecat.database.segment_iterator import SegmentBatchIterator
from gamecat.qa.project_scan import ProjectQAReport, scan_segments
from gamecat.utils.decorators import measure_time
from gamecat.workflow.status import ProjectProgress
from gamecat.services.glossary_service import GlossaryService
from gamecat.glossary.importers import GlossaryImportResult, import_glossary_csv, import_glossary_json
from gamecat.glossary.exporters import export_glossary_csv, export_glossary_json


@dataclass(frozen=True, slots=True)
class TranslationImportResult:
    total: int
    updated: int
    unmatched: int


class ProjectService:
    """High-level project workflow independent of the GUI."""
    def __init__(
        self,
        database_path: Path,
        max_io_workers: int = 4,
        autosave_debounce_seconds: float = 0.20,
    ):
        self.connection = open_database(database_path)
        initialize_schema(self.connection)
        self.projects = ProjectRepository(self.connection)
        self.segments = SegmentRepository(self.connection)
        self.glossary = GlossaryRepository(self.connection)
        self.translation_memory = TranslationMemoryRepository(self.connection)
        self.io = IOWorkerPool(max_io_workers)
        self.save_queue = SaveQueue(self.segments, autosave_debounce_seconds)

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
        # Any read used by QA/export/TM must observe the latest editor state.
        self.flush_saves()
        return self.segments.list_for_project(project_id)

    def iter_segments(self, project_id: int, batch_size: int = 500) -> SegmentBatchIterator:
        """Iterator po segmentach projektu czytający bazę partiami.

        Przed utworzeniem iteratora opróżniana jest kolejka autosave, aby
        operacje na całym projekcie (QA, eksport, analiza TM) widziały
        najnowsze zmiany z edytora.
        """
        self.flush_saves()
        return self.segments.iter_for_project(project_id, batch_size)

    @measure_time
    def run_project_qa(self, project: Project) -> ProjectQAReport:
        """Sprawdź cały projekt, czytając segmenty strumieniowo z bazy."""
        if project.id is None:
            raise ValueError('project must be persisted before QA')
        return scan_segments(self.iter_segments(project.id), self.list_glossary(project.id))

    def glossary_service(self, project_id: int | None) -> GlossaryService:
        return GlossaryService(self.glossary, project_id)

    def list_glossary(self, project_id: int | None) -> list[GlossaryTerm]:
        if project_id is None:
            return []
        return self.glossary.list_terms(project_id)

    def create_glossary_term(self, project_id: int | None, term: GlossaryTerm) -> GlossaryTerm:
        return self.glossary_service(project_id).create_term(term)

    def save_glossary_term(self, project_id: int | None, term: GlossaryTerm) -> GlossaryTerm:
        return self.glossary_service(project_id).save_term(term)

    def delete_glossary_term(self, project_id: int | None, term_id: int) -> None:
        self.glossary_service(project_id).delete_term(term_id)

    def add_glossary_variant(self, project_id: int | None, term_id: int, target: str) -> bool:
        return self.glossary_service(project_id).add_variant(term_id, target)

    def remove_glossary_variant(self, project_id: int | None, term_id: int, target: str) -> None:
        self.glossary_service(project_id).remove_variant(term_id, target)

    def _import_glossary_file(self, project_id: int, path: Path) -> GlossaryImportResult:
        suffix = path.suffix.casefold()
        if suffix == '.csv':
            return import_glossary_csv(path, self.glossary, project_id)
        if suffix == '.json':
            return import_glossary_json(path, self.glossary, project_id)
        raise ValueError(f'Unsupported glossary format: {suffix}')

    def import_glossary_file_async(self, project_id: int | None, path: Path) -> Future[GlossaryImportResult]:
        if project_id is None:
            raise ValueError('project_id is required')
        return self.io.submit(self._import_glossary_file, project_id, path)

    def _export_glossary_file(self, project_id: int, path: Path) -> int:
        terms = self.glossary.list_terms(project_id)
        suffix = path.suffix.casefold()
        if suffix == '.csv':
            return export_glossary_csv(path, terms)
        if suffix == '.json':
            return export_glossary_json(path, terms)
        raise ValueError(f'Unsupported glossary format: {suffix}')

    def export_glossary_file_async(self, project_id: int | None, path: Path) -> Future[int]:
        if project_id is None:
            raise ValueError('project_id is required')
        return self.io.submit(self._export_glossary_file, project_id, path)

    @measure_time
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
        # Wyrażenie generujące: parsowanie pliku i budowa segmentów odbywa się
        # leniwie, wewnątrz jednej transakcji – błąd w połowie pliku cofa całość.
        segments = (
            Segment(item.source, item.position, item.key, item.target, project_id=project.id)
            for item in imported
        )
        try:
            return self.segments.create_many(segments)
        except (UnicodeError, ValueError, KeyError) as exc:
            raise ImportFormatError(f'Cannot import {path.name}: {exc}') from exc

    def import_file_async(
        self,
        project: Project,
        path: Path,
        csv_columns: tuple[str, str, str | None] | None = None,
    ) -> Future[list[Segment]]:
        return self.io.submit(self._import_file, project, path, csv_columns)

    @property
    def pending_save_count(self) -> int:
        return self.save_queue.pending_count

    def queue_segment_save(self, segment: Segment) -> None:
        self.save_queue.enqueue(segment)

    def flush_saves(self) -> None:
        self.save_queue.flush()

    def save_segment(self, segment: Segment) -> None:
        """Persist a segment synchronously while preserving autosave ordering."""
        self.queue_segment_save(segment)
        self.flush_saves()

    def set_segment_statuses(
        self,
        segments: Iterable[Segment],
        status: SegmentStatus | str,
    ) -> int:
        """Set one workflow status for many segments without racing queued autosaves."""
        resolved = status if isinstance(status, SegmentStatus) else SegmentStatus(status)
        items = list(segments)
        if not items:
            return 0
        self.flush_saves()
        for segment in items:
            segment.status = resolved
        return self.segments.update_many(items)

    def project_progress(self, project_id: int | None) -> ProjectProgress:
        if project_id is None:
            return ProjectProgress()
        self.flush_saves()
        return ProjectProgress.from_counts(self.segments.status_counts(project_id))

    @measure_time
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

        changed: list[Segment] = []
        unmatched = 0
        # Najpierw dopasowanie w pamięci, dopiero potem jeden zapis: błąd
        # (np. niejednoznaczny klucz) nie zostawia częściowo zaimportowanego pliku.
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
            changed.append(segment)
        updated = self.segments.update_many(changed)
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

    @measure_time
    def analyze_project_tm(
        self,
        project: Project,
        mode: ExecutionMode | str = ExecutionMode.PROCESSES,
        workers: int | None = None,
        min_parallel: int = 200,
    ) -> TMAnalysisReport:
        """Porównaj wszystkie segmenty projektu z TM tej pary językowej."""
        if project.id is None:
            raise ValueError('project must be persisted before TM analysis')
        tm = [(e.source, e.target) for e in
              self.translation_memory.list_for_languages(project.source_language, project.target_language)]
        items = ((segment.id, segment.source) for segment in self.iter_segments(project.id)
                 if segment.id is not None)
        return analyze(items, tm, mode=mode, workers=workers, min_parallel=min_parallel)

    def analyze_project_tm_async(self, project: Project, **kwargs) -> Future[TMAnalysisReport]:
        """Uruchom analizę z wątku I/O, aby pula procesów nie blokowała GUI."""
        return self.io.submit(self.analyze_project_tm, project, **kwargs)

    def apply_exact_matches(self, project: Project, report: TMAnalysisReport) -> int:
        """Pretranslacja: wstaw dopasowania 100% do segmentów bez tłumaczenia."""
        if project.id is None:
            raise ValueError('project must be persisted before pretranslation')
        exact = {match.segment_id: match.tm_target for match in report.exact_matches()}
        changed: list[Segment] = []
        for segment in self.iter_segments(project.id):
            target = exact.get(segment.id) if segment.id is not None else None
            if target is None or segment.target:
                continue
            segment.target = target
            if segment.status is SegmentStatus.NEW:
                segment.status = SegmentStatus.TRANSLATED
            changed.append(segment)
        return self.segments.update_many(changed)

    @staticmethod
    @measure_time
    def _export_file(segments: Iterable[Segment], path: Path, format_name: str) -> None:
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

    def _export_project(self, project: Project, path: Path, format_name: str) -> int:
        if project.id is None:
            raise ValueError('project must be persisted before export')
        iterator = self.iter_segments(project.id)
        counted = _CountingIterator(iterator)
        self._export_file(counted, path, format_name)
        return counted.count

    def export_project_async(self, project: Project, path: Path, format_name: str) -> Future[int]:
        """Eksportuj projekt w wątku I/O, czytając segmenty partiami z bazy."""
        return self.io.submit(self._export_project, project, path, format_name)

    def close(self) -> None:
        # Stop accepting project work only after every queued edit reached SQLite.
        self.save_queue.close()
        self.io.close()
        self.connection.close()


class _CountingIterator:
    """Przezroczysta nakładka zliczająca elementy przechodzące przez iterator."""

    def __init__(self, inner: Iterable[Segment]):
        self._inner = iter(inner)
        self.count = 0

    def __iter__(self) -> _CountingIterator:
        return self

    def __next__(self) -> Segment:
        item = next(self._inner)
        self.count += 1
        return item
