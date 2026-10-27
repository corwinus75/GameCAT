"""Operacje na segmentach: odczyt, zapis, historia, statusy i zamiana."""
from __future__ import annotations
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from gamecat.models.project import Project
from gamecat.models.segment import Segment, SegmentStatus
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.database.segment_iterator import SegmentBatchIterator
from gamecat.workflow.status import ProjectProgress


class SegmentOperationsMixin:
    """Operacje na segmentach: odczyt, zapis, historia, statusy i zamiana."""

    def get_segment(self, segment_id: int) -> Segment:
        """Wczytaj segment o podanym ID."""
        return self.segments.get(segment_id)

    def count_segments(self, project_id: int | None) -> int:
        """Zwróć liczbę segmentów projektu (0 bez projektu)."""
        return self.segments.count_for_project(project_id) if project_id is not None else 0

    def list_segments(self, project_id: int | None) -> list[Segment]:
        """Zwróć wszystkie segmenty projektu po opróżnieniu kolejki zapisów."""
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

    @property
    def pending_save_count(self) -> int:
        """Liczba zapisów oczekujących w kolejce autosave."""
        return self.save_queue.pending_count

    def commit_segment_action(
        self, project: Project, segment_id: int, target: str,
        status: SegmentStatus | str, *, comment: str | None = None,
    ) -> Segment:
        """Zapisz ręczną akcję (Zapisz/Zatwierdź/LQA) i wpis historii w jednej transakcji.

        Zmiany w edytorze są szkicami – dopiero ta metoda utrwala je jako bieżące
        tłumaczenie. Każda akcja (także ponowne zatwierdzenie) tworzy datowany wpis
        w historii. Zatwierdzenie (``APPROVED``) dodaje parę do aktywnej TM.
        Zwraca świeżo wczytany segment.

        :raises ValueError: projekt niezapisany, status ``NEW`` lub pusty Target.
        :raises DatabaseError: błąd zapisu segmentu lub historii.
        """
        from datetime import datetime, timezone
        from gamecat.exceptions import DatabaseError
        if project.id is None:
            raise ValueError('Project is not persisted')
        resolved = SegmentStatus(status)
        if resolved is SegmentStatus.NEW:
            raise ValueError('History actions require a translated status')
        if not isinstance(target, str) or not target.strip():
            raise ValueError('Nie można zatwierdzić pustego tłumaczenia.')
        self.flush_saves()
        if resolved is SegmentStatus.APPROVED:
            self._ensure_tm_project(project)
        stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        try:
            with self.connection:
                row = self.connection.fetchone(
                    'SELECT * FROM segments WHERE id=? AND project_id=?',
                    (segment_id, project.id),
                )
                if row is None:
                    raise KeyError(segment_id)
                existing_comment = row['comment'] if comment is None else comment
                self.connection.execute("""UPDATE segments SET target=?, status=?, comment=?,
                    updated_at=?, ai_generated=0 WHERE id=? AND project_id=?""",
                    (target, resolved.value, existing_comment, stamp, segment_id, project.id))
                self.connection.execute("""INSERT INTO segment_history
                    (segment_id,project_id,status,target,created_at) VALUES (?,?,?,?,?)""",
                    (segment_id,project.id,resolved.value,target,stamp))
        except sqlite3.Error as exc:
            raise DatabaseError(f'Nie można zapisać segmentu i historii: {exc}') from exc
        segment = self.segments.get(segment_id)
        if resolved is SegmentStatus.APPROVED and segment.source.strip():
            self.translation_memory.create_unique_many([TranslationMemoryEntry(
                segment.source, segment.target, project.source_language,
                project.target_language, origin_project=project.name,
            )])
            self.invalidate_tm_cache()
        return segment

    def segment_history(self, project: Project, segment_id: int) -> list[dict]:
        """Zwróć migawki z historii segmentu od najnowszej; nigdy nie zawiera niezapisanych szkiców."""
        if project.id is None:
            return []
        rows = self.connection.fetchall("""SELECT id, status, target, created_at
            FROM segment_history WHERE project_id=? AND segment_id=? ORDER BY id DESC""",
            (project.id, segment_id))
        return [dict(row) for row in rows]

    def queue_segment_save(self, segment: Segment) -> None:
        """Dodaj segment do kolejki zapisów w tle."""
        self.save_queue.enqueue(segment)

    def flush_saves(self) -> None:
        """Poczekaj, aż kolejka zapisów w tle zostanie opróżniona."""
        self.save_queue.flush()

    def save_segment(self, segment: Segment) -> None:
        """Zapisz segment synchronicznie, zachowując kolejność względem autosave."""
        self.queue_segment_save(segment)
        self.flush_saves()

    def set_segment_statuses(
        self,
        segments: Iterable[Segment],
        status: SegmentStatus | str,
    ) -> int:
        """Ustaw jeden status workflow dla wielu segmentów (bez wyścigu z autosave).

        Przy zatwierdzaniu najpierw sprawdzane są połączenia z TM, a potem pary
        Source/Target trafiają do pamięci tłumaczeniowej. Zwraca liczbę segmentów.
        """
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
        """Atomowo zamień Target wielu segmentów jednego projektu.

        Przed zmianą opróżniana jest kolejka zapisów, a wszystkie ID i statusy są
        weryfikowane. Source nie jest zmieniany; zmieniony tekst po recenzji wraca
        do ``TRANSLATED``. Zwraca liczbę zmienionych segmentów.

        :raises ValueError: obcy segment, chroniony status bez zgody lub błędne dane.
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
        """Zwróć postęp projektu policzony z aktualnych statusów w bazie."""
        if project_id is None:
            return ProjectProgress()
        self.flush_saves()
        return ProjectProgress.from_counts(self.segments.status_counts(project_id))

    def apply_ai_translation(
        self, project: Project, segment_id: int, translation: str, model: str,
        *, replace: bool = False, include_reviewed: bool = False,
        expected_source: str | None = None, expected_target: str | None = None,
    ) -> None:
        # Apply AI output with a fresh ownership and conflict check.
        """Wstaw tłumaczenie AI do segmentu po ponownym sprawdzeniu konfliktów.

        Weryfikowane są przynależność do projektu, niezmieniony Source/Target od
        chwili wysłania żądania oraz ochrona istniejącego tłumaczenia i statusów
        po recenzji.

        :raises ValueError: przy konflikcie lub braku zgody na nadpisanie.
        """
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
