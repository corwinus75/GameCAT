"""Pamięć tłumaczeniowa: magazyny TM, sugestie, analiza projektu i wymiana plików."""
from __future__ import annotations
from pathlib import Path
import math
from concurrent.futures import Future
from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_tm_storage, backup_duplicate_tm
from gamecat.database.repositories import TranslationMemoryRepository
from gamecat.models.project import Project
from gamecat.models.segment import Segment, SegmentStatus
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.tm.matcher import TMMatch, TMSegmentReference, find_matches
from gamecat.tm.exchange import read_tm, write_tm
from gamecat.tm.analysis import ExecutionMode, TMAnalysisReport, analyze
from gamecat.utils.decorators import measure_time


class TranslationMemoryMixin:
    """Pamięć tłumaczeniowa: magazyny TM, sugestie, analiza projektu i wymiana plików."""

    def invalidate_tm_cache(self) -> None:
        """Unieważnij migawki TM po zmianie magazynu lub jego zawartości."""
        with self._tm_cache_lock:
            self._tm_entries_cache.clear()

    def get_tm_entries(self, project: Project) -> tuple[TranslationMemoryEntry, ...]:
        """Zwróć (z cache) wpisy TM dla pary językowej projektu jako niemutowalną krotkę."""
        with self._tm_cache_lock:
            self._ensure_tm_project(project)
            key = (project.source_language, project.target_language)
            if key not in self._tm_entries_cache:
                self._tm_entries_cache[key] = tuple(self.translation_memory.list_for_languages(*key))
            return self._tm_entries_cache[key]

    def tm_sources(self, project: Project) -> frozenset[str]:
        """Zwróć zbiór tekstów źródłowych z TM (do filtra dopasowań dokładnych)."""
        return frozenset(entry.source for entry in self.get_tm_entries(project))

    def find_tm_matches_async(
        self, project: Project, source: str, limit: int = 5, *,
        current_segment_id: int | None = None,
        current_target: str | None = None,
        current_position: int | None = None,
    ) -> Future[list[TMMatch]]:
        """Policz sugestie TM dla bieżącego segmentu w puli wątków I/O."""
        return self.io.submit(
            self.find_tm_matches, project, source, limit,
            current_segment_id=current_segment_id,
            current_target=current_target,
            current_position=current_position,
        )

    def _ensure_tm_project(self, project: Project) -> None:
        """Upewnij się, że załadowany jest magazyn TM właściwy dla projektu."""
        if self._active_tm_project_id != self._tm_project_id(project):
            self.select_project(project)

    def sync_project_to_tm(self, project: Project) -> int:
        """Dodaj do TM wszystkie przetłumaczone segmenty projektu (bez duplikatów).

        Zwraca liczbę nowych wpisów.
        """
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
        *,
        current_segment_id: int | None = None,
        current_target: str | None = None,
        current_position: int | None = None,
    ) -> list[TMMatch]:
        """Znajdź sugestie TM dla tekstu źródłowego.

        Gdy podano bieżący segment, para identyczna z jego Source/Target trafia na
        początek listy i otrzymuje znacznik ``BIEŻĄCY``, a każda sugestia dostaje
        odwołania do segmentów projektu używających tej samej pary.
        """
        entries = self.get_tm_entries(project)
        effective_threshold = self.get_tm_threshold(project) if threshold is None else threshold
        matches = find_matches(source, entries, limit=limit, threshold=effective_threshold)
        if current_segment_id is None:
            # All existing callers (AI, analysis) retain their original behavior
            # and do not incur additional SQLite reads.
            return matches

        # Multiple TM entries may share a Source but differ in Target. If the
        # current bilingual pair exists, show it *first* even if there are more
        # than 'limit' equally ranked 100% matches.
        if current_target and limit > 0 and effective_threshold <= 1.0:
            selected_entry = next(
                (entry for entry in entries
                 if entry.source == source and entry.target == current_target), None
            )
            if selected_entry is not None:
                matches = [TMMatch(selected_entry, 1.0)] + [
                    match for match in matches if match.entry is not selected_entry
                ]
                matches = matches[:limit]

        refs_by_pair = self.segments.references_for_pairs(
            self._tm_project_id(project),
            ((match.entry.source, match.entry.target) for match in matches),
        )
        annotated: list[TMMatch] = []
        for match in matches:
            key = (match.entry.source, match.entry.target)
            refs = [TMSegmentReference(sid, pos) for sid, pos in refs_by_pair.get(key, ())]
            is_current = bool(current_target) and key == (source, current_target)
            if not is_current:
                # During autosave the database may still have the *previous*
                # translation of the active segment. Use the editor snapshot
                # as authoritative for that segment, not its stale DB row.
                refs = [ref for ref in refs if ref.id != current_segment_id]
            if is_current and not any(ref.id == current_segment_id for ref in refs):
                # The GUI Target can still be in autosave's debounce queue.
                if current_position is not None:
                    refs.append(TMSegmentReference(current_segment_id, current_position))
            refs.sort(key=lambda ref: (ref.position, ref.id))
            annotated.append(TMMatch(match.entry, match.score, tuple(refs), is_current))
        return annotated

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
        """Wstaw tylko dopasowania 100% (zachowanie publicznego API z wcześniejszych wersji)."""
        return self.apply_tm_matches(project, report, minimum_score=1.0)

    def apply_tm_matches(self, project: Project, report: TMAnalysisReport,
                         minimum_score: float = 1.0) -> int:
        """Wstaw tłumaczenia z raportu analizy do pustych segmentów.

        Dopasowania fuzzy wymagają jawnego obniżenia *minimum_score*. Raport innego
        projektu lub nieaktualny wobec zmienionego Source jest odrzucany. Zwraca
        liczbę uzupełnionych segmentów.

        :raises ValueError: raport innego projektu lub próg spoza [0, 1].
        """
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
        """Zwróć ID projektu wymagane przez operacje TM.

        :raises ValueError: gdy projekt nie jest zapisany.
        """
        if project.id is None:
            raise ValueError('project must be persisted before TM operations')
        return project.id

    def tm_database_path(self, project: Project) -> Path | None:
        """Zwróć ścieżkę zewnętrznej bazy TM projektu albo ``None`` (TM w pliku projektu)."""
        settings = self._tm_setting(project)
        return Path(settings['external_path']) if settings is not None and settings['external_path'] else None

    def _select_tm_storage(self, path: Path, create_new: bool = True) -> None:
        """Otwórz i przełącz się na zewnętrzną bazę TM.

        Plik musi być samodzielnym magazynem TM GameCAT; przy ponownym otwarciu
        projektu brakujący plik nie jest tworzony po cichu.

        :raises ValueError: plik projektu lub plik niebędący magazynem TM.
        :raises FileNotFoundError: brak katalogu lub wcześniej powiązanego pliku.
        """
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
        """Powiąż projekt z zewnętrzną bazą TM; przy błędzie poprzedni magazyn zostaje aktywny."""
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
        """Przełącz projekt z powrotem na TM przechowywaną w pliku projektu."""
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
        """Zaimportuj plik wymiany TM po walidacji całości; zwraca liczbę nowych wpisów."""
        self._ensure_tm_project(project)
        entries = read_tm(path)  # parse and validate entire file before writes
        count = self.translation_memory.create_unique_many(entries)
        self.invalidate_tm_cache()
        return count

    def export_tm_file(self, project: Project, path: Path) -> int:
        """Wyeksportuj całą aktywną TM do CSV/JSON; zwraca liczbę wpisów."""
        self._ensure_tm_project(project)
        return write_tm(path, self.translation_memory.list_all())

    def import_tm_file_async(self, project: Project, path: Path) -> Future[int]:
        """Zleć import pliku TM w puli wątków I/O."""
        return self.io.submit(self.import_tm_file, project, path)

    def export_tm_file_async(self, project: Project, path: Path) -> Future[int]:
        """Zleć eksport TM w puli wątków I/O."""
        return self.io.submit(self.export_tm_file, project, path)
