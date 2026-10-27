"""Kontrola jakości (QA), wyszukiwanie i masowa zamiana w oknie głównym."""
from __future__ import annotations


from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from gamecat.gui.replace_dialog import BatchReplaceDialog
from gamecat.models.segment import Segment
from gamecat.utils.decorators import requires_project



class QualitySearchMixin:
    """Kontrola jakości (QA), wyszukiwanie i masowa zamiana w oknie głównym."""

    def _update_current_qa(self, segment: Segment) -> None:
        """Sprawdź bieżący stan edytora regułami QA w tle; nieaktualne wyniki są odrzucane."""
        self._qa_generation += 1
        token = self._qa_generation
        service, project = self.project_service, self.current_project
        if service is None or project is None or segment.id is None or self._closing:
            self.qa_panel.set_issues([])
            return
        sid, source, target = segment.id, segment.source, segment.target
        pending = self._qa_future
        if pending is not None:
            pending.cancel()
        future = service.check_segment_qa_async(project, source, target)
        self._qa_future = future

        def poll() -> None:
            if self._closing or token != self._qa_generation or self.project_service is not service:
                return
            if not future.done():
                QTimer.singleShot(50, poll)
                return
            active = self.segment_editor.current_segment()
            if active is None or active.id != sid or active.source != source or active.target != target:
                return
            try:
                self.qa_panel.set_issues(future.result())
            except Exception as exc:
                self.qa_panel.set_issues([])
                self.statusBar().showMessage(f'Błąd QA segmentu: {exc}', 5000)

        QTimer.singleShot(0, poll)

    def _select_qa_segment(self, segment_id: int) -> None:
        """Przejdź do segmentu wskazanego w wynikach QA projektu."""
        if not self.segment_editor.select_segment_by_id(segment_id, reveal=True):
            self.statusBar().showMessage(f'Nie znaleziono segmentu ID {segment_id}.', 4000)

    def _safe_run_project_qa(self) -> None:
        """Uruchom QA projektu, pokazując ewentualny błąd."""
        try:
            self.run_project_qa()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def run_project_qa(self) -> None:
        # @requires_project gwarantuje otwarty projekt; asserty zawężają typy.
        """Uruchom QA całego projektu w tle i pokaż raport, jeśli dane się nie zmieniły."""
        assert self.project_service is not None and self.current_project is not None
        project_id = self.current_project.id
        service = self.project_service
        content_version = self._content_generation
        future = service.run_project_qa_async(self.current_project)

        def show_report(report) -> None:
            if self.project_service is not service or self.current_project is None or self.current_project.id != project_id:
                return
            if content_version != self._content_generation:
                self.qa_panel.clear_project_report()
                self.statusBar().showMessage('Treść projektu zmieniła się podczas QA — uruchom skan ponownie.', 7000)
                return
            self.qa_panel.set_project_report(report)
            self._refresh_search_context()
            self.statusBar().showMessage(
                f'QA: {report.issue_count} problemów w {report.issue_segment_count} z {report.segment_count} segmentów.',
                7000,
            )
        self._watch_future(future, show_report, 'Kontrola QA')

    def _refresh_search_context(self, *_args, force_qa: bool = False) -> None:
        """Policz w tle indeksy filtrów QA/TM; nieaktualne wyniki są odrzucane."""
        self._quality_generation += 1
        token = self._quality_generation
        service, project = self.project_service, self.current_project
        if service is None or project is None or self._closing:
            self.segment_editor.set_search_context(qa_error_ids=set(), tm_match_ids=set())
            return
        quality = self.segment_editor.quality_filter.currentData()
        qa_needed = force_qa or quality == 'qa_errors'
        tm_needed = quality == 'tm_match'
        if not qa_needed and not tm_needed:
            return
        snapshot = self.segment_editor.all_segments()
        pending = getattr(self, '_quality_future', None)
        if pending is not None:
            pending.cancel()
        future = service.calculate_search_context_async(project, snapshot, qa=qa_needed, tm=tm_needed)
        self._quality_future = future
        current_project_id = project.id

        def poll() -> None:
            if self._closing or token != self._quality_generation or self.project_service is not service:
                return
            if self.current_project is None or self.current_project.id != current_project_id:
                return
            if not future.done():
                QTimer.singleShot(50, poll)
                return
            try:
                result = future.result()
            except Exception as exc:
                self.statusBar().showMessage(f'Nie można wyliczyć filtrów: {exc}', 5000)
                self._pending_qa_jump = None
                return
            self.segment_editor.set_search_context(**result)
            if self._pending_qa_jump is not None and 'qa_error_ids' in result:
                backwards, anchor_id = self._pending_qa_jump
                self._pending_qa_jump = None
                if not self.segment_editor.jump_to_next('qa_errors', backwards=backwards, anchor_id=anchor_id):
                    self.statusBar().showMessage('Nie znaleziono segmentu z błędem QA.', 3500)

        QTimer.singleShot(0, poll)

    def _jump_to_segment(self, kind: str, *, backwards: bool = False) -> None:
        """Przejdź do następnego/poprzedniego segmentu bez tłumaczenia lub z błędem QA."""
        if self.current_project is None:
            return
        current = self.segment_editor.current_segment()
        anchor_id = current.id if current is not None else None
        if kind == 'qa_errors':
            self._pending_qa_jump = (backwards, anchor_id)
            self._refresh_search_context(force_qa=True)
            return
        if not self.segment_editor.jump_to_next(kind, backwards=backwards, anchor_id=anchor_id):
            self.statusBar().showMessage('Nie znaleziono pasującego segmentu.', 3500)

    def _safe_replace_targets(self) -> None:
        """Wykonaj masową zamianę, pokazując ewentualny błąd."""
        try:
            self.replace_targets()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można zamienić tekstu:\n{exc}')

    @requires_project
    def replace_targets(self) -> None:
        """Pokaż podgląd zamiany w Target i zapisz zatwierdzone zmiany jedną transakcją."""
        assert self.project_service is not None and self.current_project is not None
        if self.segment_editor.search_busy:
            QMessageBox.information(self, 'GameCAT', 'Wyszukiwanie jeszcze trwa. Spróbuj ponownie po wyświetleniu wyników.')
            return
        if not self.segment_editor.search_valid:
            QMessageBox.warning(self, 'GameCAT', 'Popraw nieprawidłowy wzorzec wyszukiwania.')
            return
        if not self.segment_editor.visible_segments():
            QMessageBox.information(self, 'GameCAT', 'Brak widocznych segmentów do zamiany.')
            return
        dialog = BatchReplaceDialog(
            self.segment_editor.visible_segments(), self.segment_editor.selected_segments(), self
        )
        if not dialog.exec():
            return
        changes = dialog.replacements()
        if not changes:
            return
        changed = self.project_service.replace_targets(
            self.current_project, changes, include_reviewed=dialog.include_reviewed
        )
        self._reload_segments()
        self.statusBar().showMessage(f'Zmieniono Target w {changed} segmentach.', 6000)
