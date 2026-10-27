from __future__ import annotations
from pathlib import Path
from threading import RLock
import json
import math
from collections.abc import Iterable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timezone
from gamecat.concurrency.io_workers import IOWorkerPool
from gamecat.concurrency.save_queue import SaveQueue
from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema, initialize_tm_storage, backup_duplicate_tm
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
from gamecat.tm.exchange import read_tm, write_tm
from gamecat.tm.analysis import ExecutionMode, TMAnalysisReport, analyze
from gamecat.exceptions import ImportFormatError
from gamecat.database.segment_iterator import SegmentBatchIterator
from gamecat.qa.project_scan import ProjectQAReport, scan_segments
from gamecat.qa.validator import validate_segment
from gamecat.utils.decorators import measure_time
from gamecat.workflow.status import ProjectProgress
from gamecat.services.glossary_service import GlossaryService
from gamecat.glossary.importers import GlossaryImportResult, import_glossary_csv, import_glossary_json
from gamecat.glossary.exporters import export_glossary_csv, export_glossary_json
from gamecat.ai.core import AISettings
from gamecat.localization.profiles import FormatProfile
from gamecat.localization.exchange import read_source, read_translations, export_translations


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
        self.database_path = Path(database_path).resolve()
        self.connection = open_database(self.database_path)
        try:
            backup_duplicate_tm(self.connection, self.database_path)
            initialize_schema(self.connection)
        except BaseException:
            self.connection.close()
            raise
        self.projects = ProjectRepository(self.connection)
        self.segments = SegmentRepository(self.connection)
        self.glossary = GlossaryRepository(self.connection)
        self._internal_tm = TranslationMemoryRepository(self.connection)
        self.translation_memory = self._internal_tm
        self._external_tm_connection = None
        # Do not select an arbitrary project's external TM on database open.
        self._active_tm_project_id: int | None = None
        self.io = IOWorkerPool(max_io_workers)
        self.save_queue = SaveQueue(self.segments, autosave_debounce_seconds)
        self._tm_cache_lock = RLock()
        self._tm_entries_cache: dict[tuple[str, str], tuple[TranslationMemoryEntry, ...]] = {}

    def set_format_profile(self, project: Project, profile: FormatProfile) -> None:
        """Persist format mapping per project and format; never store source files."""
        if project.id is None:
            raise ValueError('Project must be persisted')
        with self.connection:
            self.connection.execute(
                'INSERT INTO project_format_profiles(project_id,format,settings_json) VALUES(?,?,?) '
                'ON CONFLICT(project_id,format) DO UPDATE SET settings_json=excluded.settings_json',
                (project.id, profile.format, json.dumps(profile.to_dict(), ensure_ascii=False)),
            )

    def get_format_profile(self, project: Project, format_name: str) -> FormatProfile:
        if project.id is None:
            raise ValueError('Project must be persisted')
        row = self.connection.fetchone(
            'SELECT settings_json FROM project_format_profiles WHERE project_id=? AND format=?',
            (project.id, format_name),
        )
        if row is None:
            return FormatProfile(format_name)
        return FormatProfile.from_dict(json.loads(row['settings_json']))

    def clear_format_profile(self, project: Project, format_name: str) -> None:
        if project.id is None:
            raise ValueError('Project must be persisted')
        with self.connection:
            self.connection.execute('DELETE FROM project_format_profiles WHERE project_id=? AND format=?',
                                    (project.id, format_name))

    def has_format_profile(self, project: Project, format_name: str) -> bool:
        if project.id is None:
            return False
        return self.connection.fetchone(
            'SELECT 1 FROM project_format_profiles WHERE project_id=? AND format=?',
            (project.id, format_name),
        ) is not None

    def get_ai_settings(self, project: Project) -> AISettings:
        if project.id is None:
            raise ValueError('Project must be persisted')
        with self.connection:
            row = self.connection.fetchone(
                'SELECT * FROM ai_project_settings WHERE project_id=?', (project.id,)
            )
        if row is None:
            return AISettings()
        return AISettings(row['model'], row['instructions'], row['input_price_per_million'],
                          row['output_price_per_million'], row['max_output_tokens'])

    def set_ai_settings(self, project: Project, settings: AISettings) -> None:
        if project.id is None:
            raise ValueError('Project must be persisted')
        with self.connection:
            self.connection.execute('''INSERT INTO ai_project_settings
                (project_id,model,instructions,input_price_per_million,output_price_per_million,max_output_tokens)
                VALUES(?,?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET
                model=excluded.model, instructions=excluded.instructions,
                input_price_per_million=excluded.input_price_per_million,
                output_price_per_million=excluded.output_price_per_million,
                max_output_tokens=excluded.max_output_tokens''',
                (project.id, settings.model, settings.instructions, settings.input_price_per_million,
                 settings.output_price_per_million, settings.max_output_tokens))

    def apply_ai_translation(
        self, project: Project, segment_id: int, translation: str, model: str,
        *, replace: bool = False, include_reviewed: bool = False,
        expected_source: str | None = None, expected_target: str | None = None,
    ) -> None:
        # Apply AI output with a fresh ownership and conflict check.
        if project.id is None:
            raise ValueError('Project must be persisted')
        if not translation.strip() or not model.strip():
            raise ValueError('AI translation and model are required')
        self.flush_saves()
        with self.connection:
            segment = self.segments.get(segment_id)
            if segment.project_id != project.id:
                raise ValueError('Segment does not belong to current project')
            if expected_source is not None and segment.source != expected_source:
                raise ValueError('Segment source changed during AI translation')
            if expected_target is not None and segment.target != expected_target:
                raise ValueError('Segment target changed during AI translation')
            if segment.target.strip() and not replace:
                raise ValueError('Cannot overwrite existing translation without consent')
            if segment.status in {SegmentStatus.REVIEWED, SegmentStatus.APPROVED} and not include_reviewed:
                raise ValueError('Reviewed and approved segments are protected')
            segment.target = translation
            segment.ai_generated = True
            segment.status = SegmentStatus.TRANSLATED
            self.segments.update(segment)

    def create_project(self, name: str, source_language: str, target_language: str, source_format: str) -> Project:
        project = self.projects.create(Project(name, source_language, target_language, source_format))
        # Newly created projects become the active project in the caller.
        self.select_project(project)
        return project

    def load_project(self, project_id: int | None) -> Project:
        if project_id is None:
            raise ValueError('project_id is required')
        return self.projects.get(project_id)

    def list_projects(self) -> list[Project]:
        projects = self.projects.list_all()
        # Preserve 1.0.1 semantics for files that contain exactly one project.
        # With several projects, an explicit selection is mandatory.
        if len(projects) == 1 and self._active_tm_project_id is None:
            self.select_project(projects[0])
        return projects

    @property
    def active_project_id(self) -> int | None:
        return self._active_tm_project_id

    def select_project(self, project: Project) -> None:
        """Activate a project's persisted TM without switching on failed opens."""
        with self._tm_cache_lock:
            project_id = self._tm_project_id(project)
            self.projects.get(project_id)  # project must belong to this database
            if project_id == self._active_tm_project_id:
                return
            setting = self._tm_setting(project)
            external = setting['external_path'] if setting is not None else None
            if external:
                self._select_tm_storage(Path(external), create_new=False)
            else:
                self.translation_memory = self._internal_tm
                if self._external_tm_connection is not None:
                    self._external_tm_connection.close()
                    self._external_tm_connection = None
            self._active_tm_project_id = project_id
            self.invalidate_tm_cache()

    def invalidate_tm_cache(self) -> None:
        """Discard TM snapshots after storage or entries change."""
        with self._tm_cache_lock:
            self._tm_entries_cache.clear()

    def get_tm_entries(self, project: Project) -> tuple[TranslationMemoryEntry, ...]:
        """Cache the current language pair; never return a live SQLite cursor."""
        with self._tm_cache_lock:
            self._ensure_tm_project(project)
            key = (project.source_language, project.target_language)
            if key not in self._tm_entries_cache:
                self._tm_entries_cache[key] = tuple(self.translation_memory.list_for_languages(*key))
            return self._tm_entries_cache[key]

    def tm_sources(self, project: Project) -> frozenset[str]:
        return frozenset(entry.source for entry in self.get_tm_entries(project))

    def get_segment(self, segment_id: int) -> Segment:
        return self.segments.get(segment_id)

    def count_segments(self, project_id: int | None) -> int:
        return self.segments.count_for_project(project_id) if project_id is not None else 0

    def calculate_search_context(
        self, project: Project, segments: Iterable[Segment], *, qa: bool = False, tm: bool = False,
    ) -> dict[str, set[int]]:
        """Calculate quality indexes off the UI thread using immutable snapshots."""
        snapshot = tuple((segment.id, segment.source, segment.target) for segment in segments
                         if segment.id is not None)
        return self._calculate_search_snapshot(project, snapshot, qa, tm)

    def _calculate_search_snapshot(
        self, project: Project, snapshot: tuple[tuple[int, str, str], ...], qa: bool, tm: bool,
    ) -> dict[str, set[int]]:
        result: dict[str, set[int]] = {}
        if qa:
            glossary = self.list_glossary(project.id)
            result['qa_error_ids'] = {sid for sid, source, target in snapshot
                                      if validate_segment(source, target, glossary)}
        if tm:
            sources = self.tm_sources(project)
            result['tm_match_ids'] = {sid for sid, source, _ in snapshot if source in sources}
        return result

    def calculate_search_context_async(
        self, project: Project, segments: Iterable[Segment], *, qa: bool = False, tm: bool = False,
    ) -> Future[dict[str, set[int]]]:
        """Snapshot mutable editor state before dispatch; no Qt usage in worker."""
        # Copy only immutable fields on the UI thread; no costly Segment objects.
        snapshot = tuple((s.id, s.source, s.target) for s in segments if s.id is not None)
        return self.io.submit(self._calculate_search_snapshot, project, snapshot, qa, tm)

    def find_tm_matches_async(
        self, project: Project, source: str, limit: int = 5,
    ) -> Future[list[TMMatch]]:
        return self.io.submit(self.find_tm_matches, project, source, limit)

    def run_project_qa_async(self, project: Project) -> Future[ProjectQAReport]:
        return self.io.submit(self.run_project_qa, project)

    def _ensure_tm_project(self, project: Project) -> None:
        if self._active_tm_project_id != self._tm_project_id(project):
            self.select_project(project)

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

    def check_segment_qa_async(self, project: Project, source: str, target: str):
        """Validate an unsaved editor snapshot off the GUI thread."""
        def check():
            return validate_segment(source, target, self.list_glossary(project.id))
        return self.io.submit(check)

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
            imported = import_csv(path, key_column, source_column, target_column,
                                  self.get_format_profile(project, 'csv').comment_field)
        elif suffix == '.json' and not self.has_format_profile(project, 'json'):
            imported = import_json(path)
        elif suffix in {'.json', '.tsv', '.xlsx', '.xml'}:
            imported = read_source(path, self.get_format_profile(project, suffix.lstrip('.')))
        else:
            raise ValueError(f'Unsupported import format: {suffix}')
        # Wyrażenie generujące: parsowanie pliku i budowa segmentów odbywa się
        # leniwie, wewnątrz jednej transakcji – błąd w połowie pliku cofa całość.
        segments = (
            Segment(item.source, item.position, item.key, item.target, project_id=project.id,
                    status=SegmentStatus.TRANSLATED if item.target.strip() else SegmentStatus.NEW,
                    comment=item.comment)
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
        projects_for_approval = []
        if resolved is SegmentStatus.APPROVED:
            for project_id in sorted({item.project_id for item in items if item.project_id is not None}):
                project = self.load_project(project_id)
                # Validate all TM connections before changing a persisted status.
                self._ensure_tm_project(project)
                projects_for_approval.append(project)
        for segment in items:
            segment.status = resolved
        count = self.segments.update_many(items)
        if resolved is SegmentStatus.APPROVED:
            for project in projects_for_approval:
                project_id = project.id
                self._ensure_tm_project(project)
                new_entries = [TranslationMemoryEntry(
                    item.source, item.target, project.source_language, project.target_language,
                    origin_project=project.name,
                ) for item in items if item.project_id == project_id
                    and item.target.strip() and item.source.strip()]
                self.translation_memory.create_unique_many(new_entries)
            self.invalidate_tm_cache()
        return count

    def replace_targets(
        self, project: Project, replacements: Mapping[int, str], *,
        include_reviewed: bool = False,
    ) -> int:
        """Atomically replace targets within one project after draining pending autosaves.

        All ids and statuses are verified before any update. No Source is modified.
        """
        if project.id is None:
            raise ValueError('Project must be persisted before batch replacement')
        if not replacements:
            return 0
        if any(not isinstance(key, int) or not isinstance(value, str)
               for key, value in replacements.items()):
            raise ValueError('Replacement mapping must contain segment ids and text targets')
        self.flush_saves()
        with self.connection:
            ids = list(replacements)
            rows = []
            for segment_id in ids:
                row = self.connection.fetchone(
                    'SELECT project_id, status, target FROM segments WHERE id=?', (segment_id,)
                )
                if row is None or row['project_id'] != project.id:
                    raise ValueError(f'Segment {segment_id} does not belong to the selected project')
                status = SegmentStatus(row['status'])
                if not include_reviewed and status in {SegmentStatus.REVIEWED, SegmentStatus.APPROVED}:
                    raise ValueError('Cannot replace reviewed or approved segments without explicit consent')
                target = replacements[segment_id]
                if row['target'] == target:
                    continue
                if not target.strip():
                    next_status = SegmentStatus.NEW
                elif status in {SegmentStatus.NEW, SegmentStatus.REVIEWED, SegmentStatus.APPROVED}:
                    # Any edited reviewed text must be reviewed again.
                    next_status = SegmentStatus.TRANSLATED
                else:
                    next_status = status
                rows.append((target, next_status.value, datetime.now(timezone.utc).isoformat(), segment_id, project.id))
            self.connection.executemany(
                'UPDATE segments SET target=?,status=?,updated_at=?,ai_generated=0 WHERE id=? AND project_id=?', rows
            )
            return len(rows)

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
        format_profile: FormatProfile | None = None,
        legacy_json: bool = False,
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
        elif suffix == '.json' and (legacy_json or (format_profile is None and not self.has_format_profile(project, 'json'))):
            imported = list(import_translation_json(path))
        elif suffix in {'.json', '.tsv', '.xlsx', '.xml'}:
            mapping = format_profile or self.get_format_profile(project, suffix.lstrip('.'))
            imported = list(read_translations(path, mapping))
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
            if segment.target != item.target:
                # An imported revision invalidates prior human review/approval.
                # Never leave REVIEWED/APPROVED attached to a different Target.
                segment.target = item.target
                segment.status = (SegmentStatus.TRANSLATED if item.target.strip()
                                  else SegmentStatus.NEW)
            elif item.target.strip() and segment.status is SegmentStatus.NEW:
                segment.status = SegmentStatus.TRANSLATED
            elif not item.target.strip() and segment.status is SegmentStatus.TRANSLATED:
                segment.status = SegmentStatus.NEW
            changed.append(segment)
        updated = self.segments.update_many(changed)
        return TranslationImportResult(total=len(imported), updated=updated, unmatched=unmatched)

    def import_translation_file_async(
        self,
        project: Project,
        path: Path,
        csv_columns: tuple[str | None, str] | None = None,
        *, format_profile: FormatProfile | None = None,
        legacy_json: bool = False,
    ) -> Future[TranslationImportResult]:
        return self.io.submit(self._import_translation_file, project, path, csv_columns,
                              format_profile, legacy_json)

    def sync_project_to_tm(self, project: Project) -> int:
        if project.id is None:
            raise ValueError('project must be persisted before TM sync')
        self._ensure_tm_project(project)
        entries = (
            TranslationMemoryEntry(segment.source, segment.target,
                                   project.source_language, project.target_language,
                                   origin_project=project.name)
            for segment in self.list_segments(project.id)
            if segment.target.strip() and segment.source.strip()
        )
        count = self.translation_memory.create_unique_many(entries)
        self.invalidate_tm_cache()
        return count

    def find_tm_matches(
        self,
        project: Project,
        source: str,
        limit: int = 5,
        threshold: float | None = None,
    ) -> list[TMMatch]:
        entries = self.get_tm_entries(project)
        return find_matches(source, entries, limit=limit, threshold=(self.get_tm_threshold(project) if threshold is None else threshold))

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
        self._ensure_tm_project(project)
        tm = [(e.source, e.target) for e in self.get_tm_entries(project)]
        items = ((segment.id, segment.source) for segment in self.iter_segments(project.id)
                 if segment.id is not None)
        report = analyze(items, tm, mode=mode, workers=workers, min_parallel=min_parallel)
        report.project_id = project.id
        report.project_database = str(self.database_path)
        report.source_language = project.source_language
        report.target_language = project.target_language
        return report

    def analyze_project_tm_async(self, project: Project, **kwargs) -> Future[TMAnalysisReport]:
        """Uruchom analizę z wątku I/O, aby pula procesów nie blokowała GUI."""
        return self.io.submit(self.analyze_project_tm, project, **kwargs)

    def apply_exact_matches(self, project: Project, report: TMAnalysisReport) -> int:
        """Preserve the existing public 100%-only pretranslation behavior."""
        return self.apply_tm_matches(project, report, minimum_score=1.0)

    def apply_tm_matches(self, project: Project, report: TMAnalysisReport,
                         minimum_score: float = 1.0) -> int:
        """Pretranslate untranslated segments; fuzzy matches require explicit opt-in."""
        if project.id is None:
            raise ValueError('project must be persisted before pretranslation')
        if ((report.project_id is not None and report.project_id != project.id)
                or (report.project_database is not None and report.project_database != str(self.database_path))
                or (report.source_language is not None and report.source_language != project.source_language)
                or (report.target_language is not None and report.target_language != project.target_language)):
            raise ValueError('TM analysis report does not belong to this project')
        if not math.isfinite(minimum_score) or not 0 <= minimum_score <= 1:
            raise ValueError('minimum_score must be between 0 and 1')
        matched = {m.segment_id: (m.tm_target, m.segment_source) for m in report.matches
                   if m.score >= minimum_score and m.tm_target and m.tm_source}
        changed: list[Segment] = []
        for segment in self.iter_segments(project.id):
            matched_value = matched.get(segment.id) if segment.id is not None else None
            if matched_value is None or segment.target.strip():
                continue
            target, original_source = matched_value
            # Never apply a stale report to a different/modified source segment.
            if original_source is not None and segment.source != original_source:
                continue
            segment.target = target
            if segment.status is SegmentStatus.NEW:
                segment.status = SegmentStatus.TRANSLATED
            changed.append(segment)
        return self.segments.update_many(changed)

    # --- TM 0.8: per-project settings, optional external SQLite TM storage ---
    def _tm_project_id(self, project: Project) -> int:
        if project.id is None:
            raise ValueError('project must be persisted before TM operations')
        return project.id

    def _tm_setting(self, project: Project):
        return self.connection.fetchone(
            'SELECT external_path,threshold FROM tm_project_settings WHERE project_id=?',
            (self._tm_project_id(project),),
        )

    def get_tm_threshold(self, project: Project) -> float:
        settings = self._tm_setting(project)
        return float(settings['threshold']) if settings is not None else 0.45

    def set_tm_threshold(self, project: Project, value: float) -> None:
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('TM threshold must be in [0, 1]')
        with self.connection:
            self.connection.execute(
                'INSERT INTO tm_project_settings(project_id, threshold) VALUES(?,?) '
                'ON CONFLICT(project_id) DO UPDATE SET threshold=excluded.threshold',
                (self._tm_project_id(project), float(value)),
            )

    def tm_database_path(self, project: Project) -> Path | None:
        settings = self._tm_setting(project)
        return Path(settings['external_path']) if settings is not None and settings['external_path'] else None

    def _select_tm_storage(self, path: Path, create_new: bool = True) -> None:
        path = path.expanduser().resolve()
        if path == self.database_path:
            raise ValueError('External TM file must be different from project database')
        if not path.parent.is_dir():
            raise FileNotFoundError(path.parent)
        if not create_new and not path.is_file():
            raise FileNotFoundError(f'Linked external TM database is missing: {path}')
        # Do not silently create a missing *previously linked* TM during project reopen.
        candidate = open_database(path)
        try:
            table_names = {row['name'] for row in candidate.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if table_names - {'translation_memory', 'sqlite_sequence'}:
                raise ValueError('Selected file is not a standalone GameCAT TM store')
            if not create_new and 'translation_memory' not in table_names:
                raise ValueError('Linked external TM does not contain TM data')
            backup_duplicate_tm(candidate, path)
            initialize_tm_storage(candidate)
            replacement = TranslationMemoryRepository(candidate)
        except BaseException:
            candidate.close()
            raise
        old = self._external_tm_connection
        self._external_tm_connection = candidate
        self.translation_memory = replacement
        if old is not None:
            old.close()

    def attach_tm_database(self, project: Project, path: Path) -> None:
        path = Path(path).expanduser().resolve()
        with self._tm_cache_lock:
            # Preserve current storage and preference when selection fails.
            self.projects.get(self._tm_project_id(project))
            self._select_tm_storage(path)
            self._active_tm_project_id = project.id
            self.invalidate_tm_cache()
            with self.connection:
                self.connection.execute(
                    'INSERT INTO tm_project_settings(project_id,external_path) VALUES(?,?) '
                    'ON CONFLICT(project_id) DO UPDATE SET external_path=excluded.external_path',
                    (self._tm_project_id(project), str(path)),
                )

    def use_project_tm_database(self, project: Project) -> None:
        with self._tm_cache_lock:
            self.projects.get(self._tm_project_id(project))
            with self.connection:
                self.connection.execute(
                    'INSERT INTO tm_project_settings(project_id,external_path) VALUES(?,NULL) '
                    'ON CONFLICT(project_id) DO UPDATE SET external_path=NULL',
                    (self._tm_project_id(project),),
                )
            self.translation_memory = self._internal_tm
            if self._external_tm_connection is not None:
                self._external_tm_connection.close()
                self._external_tm_connection = None
            self._active_tm_project_id = project.id
            self.invalidate_tm_cache()

    def import_tm_file(self, project: Project, path: Path) -> int:
        self._ensure_tm_project(project)
        entries = read_tm(path)  # parse and validate entire file before writes
        count = self.translation_memory.create_unique_many(entries)
        self.invalidate_tm_cache()
        return count

    def export_tm_file(self, project: Project, path: Path) -> int:
        self._ensure_tm_project(project)
        return write_tm(path, self.translation_memory.list_all())

    def import_tm_file_async(self, project: Project, path: Path) -> Future[int]:
        return self.io.submit(self.import_tm_file, project, path)

    def export_tm_file_async(self, project: Project, path: Path) -> Future[int]:
        return self.io.submit(self.export_tm_file, project, path)

    @staticmethod
    @measure_time
    def _export_file(segments: Iterable[Segment], path: Path, format_name: str, *, ordered: bool = False) -> None:
        if format_name == 'txt':
            export_txt(segments, path, ordered=ordered)
        elif format_name == 'csv':
            export_csv(segments, path, ordered=ordered)
        elif format_name == 'json':
            export_json(segments, path, 'list', ordered=ordered)
        else:
            raise ValueError(f'Unsupported export format: {format_name}')

    def export_file_async(self, segments: list[Segment], path: Path, format_name: str) -> Future[None]:
        return self.io.submit(self._export_file, segments, path, format_name)

    def _export_project(self, project: Project, path: Path, format_name: str) -> int:
        if project.id is None:
            raise ValueError('project must be persisted before export')
        iterator = self.iter_segments(project.id)
        if format_name in {'tsv', 'xlsx', 'xml'}:
            return export_translations(iterator, path, self.get_format_profile(project, format_name))
        counted = _CountingIterator(iterator)
        self._export_file(counted, path, format_name, ordered=True)
        return counted.count

    def _export_using_template(self, project: Project, template: Path, destination: Path) -> int:
        if project.id is None:
            raise ValueError('project must be persisted before export')
        if template.suffix.lower() != destination.suffix.lower():
            raise ValueError('Original file and output file must use the same format')
        fmt = template.suffix.lower().lstrip('.')
        if fmt not in {'csv', 'tsv', 'xlsx', 'json', 'xml'}:
            raise ValueError(f'Template export does not support: {fmt}')
        if not self.has_format_profile(project, fmt):
            raise ValueError('First import a source file with a saved format profile')
        return export_translations(
            self.iter_segments(project.id), destination, self.get_format_profile(project, fmt),
            template_path=template,
        )

    def export_using_template_async(self, project: Project, template: Path, destination: Path) -> Future[int]:
        return self.io.submit(self._export_using_template, project, template, destination)

    def export_project_async(self, project: Project, path: Path, format_name: str) -> Future[int]:
        """Eksportuj projekt w wątku I/O, czytając segmenty partiami z bazy."""
        return self.io.submit(self._export_project, project, path, format_name)

    def close(self) -> None:
        # Stop accepting project work only after every queued edit reached SQLite.
        self.save_queue.close()
        self.io.close()
        if self._external_tm_connection is not None:
            self._external_tm_connection.close()
            self._external_tm_connection = None
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
