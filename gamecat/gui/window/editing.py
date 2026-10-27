"""Obsługa edycji segmentów: szkice, zapis, historia, statusy i postęp."""
from __future__ import annotations


from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from gamecat.models.segment import Segment, SegmentStatus



class EditingMixin:
    """Obsługa edycji segmentów: szkice, zapis, historia, statusy i postęp."""

    def _safe_commit_current(self) -> None:
        """Plik → Zapisz / Ctrl+S to jawny zapis ze statusem ``TRANSLATED``, nie autosave."""
        self.segment_editor.request_action(SegmentStatus.TRANSLATED)

    def _update_history(self, segment: Segment) -> None:
        """Wczytaj historię zatwierdzeń wybranego segmentu do panelu Historia."""
        if self.project_service is None or self.current_project is None or segment.id is None:
            self.history_panel.set_history([])
            return
        try:
            self.history_panel.set_history(self.project_service.segment_history(self.current_project, segment.id))
        except Exception as exc:
            self.history_panel.set_history([])
            self.statusBar().showMessage(f'Błąd historii: {exc}', 5000)

    def _on_segment_action_requested(
        self, segment: Segment, status: SegmentStatus, target: str, comment: str,
    ) -> None:
        """Utrwal akcję workflow segmentu w bazie i odśwież listę, postęp oraz panele."""
        if self.project_service is None or self.current_project is None or segment.id is None:
            return
        try:
            persisted = self.project_service.commit_segment_action(
                self.current_project, segment.id, target, status, comment=comment)
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie zapisano tłumaczenia:\n{exc}')
            return
        self.segment_editor.accept_saved_segment(persisted)
        self._content_generation += 1
        self._refresh_autosave_status()
        self._refresh_progress()
        current = self.segment_editor.current_segment()
        if current is not None:
            self._update_history(current)
            self._update_current_tm(current)
            self._update_current_qa(current)
        self.qa_panel.clear_project_report()
        self.statusBar().showMessage(f'{status.value}: zapisano segment #{segment.id}', 3500)

    def _on_editor_draft_changed(self, segment: Segment, target: str) -> None:
        """Odśwież QA i sugestie TM na podstawie szkicu z RAM – bez zapisu szkicu do bazy."""
        if self.project_service is None or self.current_project is None:
            return
        preview = Segment(segment.source, segment.position, segment.key, target,
                          segment.status, segment.comment, segment.id, segment.project_id)
        self._update_current_qa(preview)
        signature = (segment.id, segment.source, target)
        if signature == self._tm_last_requested:
            return
        self._tm_last_requested = signature
        self._tm_generation += 1
        token = self._tm_generation
        if self._tm_future is not None:
            self._tm_future.cancel()
        self.tm_panel.set_matches([])

        def refresh_after_edit() -> None:
            if self._closing or token != self._tm_generation:
                return
            current = self.segment_editor.current_segment()
            if current is None or current.id != segment.id or self.segment_editor.target_edit.toPlainText() != target:
                return
            self._update_current_tm(preview)

        QTimer.singleShot(250, refresh_after_edit)

    def _safe_save(self) -> None:
        """Zapisz projekt, pokazując ewentualny błąd w oknie komunikatu."""
        try:
            self.save_project()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    def _save_modified_segment(self, segment: Segment) -> None:
        """Dodaj zmieniony segment do kolejki zapisów w tle."""
        if self.project_service is None or segment.id is None:
            return
        try:
            self.project_service.queue_segment_save(segment)
            self._refresh_autosave_status()
        except Exception as exc:
            self._save_indicator.setText('Błąd zapisu')
            self.statusBar().showMessage(f'Błąd zapisu segmentu: {exc}', 5000)

    def _refresh_autosave_status(self) -> None:
        """Pokaż na pasku stanu liczbę oczekujących zapisów i niezapisanych szkiców."""
        if self.project_service is None:
            self._save_indicator.setText('Brak projektu')
            return
        pending = self.project_service.pending_save_count
        if pending:
            self._save_indicator.setText(f'Autosave: zapisuję… ({pending})')
        else:
            pending_drafts = len(self.segment_editor._drafts)
            self._save_indicator.setText(f'Szkice niezapisane: {pending_drafts}' if pending_drafts else 'Zapisano')

    def _refresh_progress(self) -> None:
        """Odśwież wskaźnik postępu (przetłumaczone / zrecenzowane / zatwierdzone)."""
        progress = self.segment_editor.project_progress()
        if progress.total == 0:
            self._progress_indicator.setText('Postęp: 0 segmentów')
            self._progress_indicator.setToolTip('Projekt nie zawiera segmentów')
            return
        self._progress_indicator.setText(
            f'T: {progress.translated_or_better}/{progress.total} ({progress.translation_percent:.1f}%)  '
            f'R: {progress.reviewed_or_better}/{progress.total} ({progress.review_percent:.1f}%)  '
            f'A: {progress.approved}/{progress.total} ({progress.approval_percent:.1f}%)'
        )
        self._progress_indicator.setToolTip(
            f'NEW: {progress.new} | TRANSLATED: {progress.translated} | '
            f'REVIEWED: {progress.reviewed} | APPROVED: {progress.approved}'
        )

    def _on_segments_status_modified(self, segments: list[Segment]) -> None:
        """Zapisz masową zmianę statusów, grupując segmenty według nowego statusu."""
        if self.project_service is None or not segments:
            return
        groups: dict[SegmentStatus, list[Segment]] = {}
        for segment in segments:
            groups.setdefault(segment.status, []).append(segment)
        try:
            for status, items in groups.items():
                self.project_service.set_segment_statuses(items, status)
        except Exception as exc:
            self.statusBar().showMessage(f'Błąd zmiany statusu: {exc}', 5000)
            self._reload_segments()
            return
        self._refresh_progress()
        self._refresh_search_context()
        selected = self.segment_editor.current_segment()
        if selected is not None:
            self._update_current_tm(selected)
        self.statusBar().showMessage(
            f'Zmieniono status {len(segments)} segmentów.', 3000
        )

    def _on_segment_modified(self, segment: Segment) -> None:
        """Obsłuż zmianę segmentu: zapis w tle, QA, postęp i opóźnione odświeżenie TM."""
        self._content_generation += 1
        self._save_modified_segment(segment)
        self._update_current_qa(segment)
        self._refresh_progress()
        # A Target edit changes which exact TM pair belongs to the selected
        # segment. Debounce recomputation while typing, invalidate any pending
        # result immediately, and do not recalculate for comment-only edits.
        signature = (segment.id, segment.source, segment.target)
        if signature != self._tm_last_requested:
            self._tm_last_requested = signature
            self._tm_generation += 1
            token = self._tm_generation
            if self._tm_future is not None:
                self._tm_future.cancel()
            self.tm_panel.set_matches([])

            def refresh_after_edit() -> None:
                if self._closing or token != self._tm_generation:
                    return
                selected = self.segment_editor.current_segment()
                if selected is not None and (selected.id, selected.source, selected.target) == signature:
                    self._update_current_tm(selected)

            QTimer.singleShot(200, refresh_after_edit)
        if self._pending_qa_jump is not None or self.segment_editor.quality_filter.currentData() in {'qa_errors', 'tm_match'}:
            self._refresh_search_context(force_qa=self._pending_qa_jump is not None)

    def _reload_segments(self) -> None:
        """Wczytaj ponownie segmenty projektu z bazy, zachowując szkice."""
        if self.project_service is None or self.current_project is None:
            return
        self.segment_editor.set_segments(self.project_service.list_segments(self.current_project.id), preserve_drafts=True)
        self._refresh_search_context()
        self._refresh_progress()
        self.qa_panel.clear_project_report()
