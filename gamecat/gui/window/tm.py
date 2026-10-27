"""Obsługa pamięci tłumaczeniowej (TM) w oknie głównym."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox

from gamecat.gui.tm_analysis_dialog import TMAnalysisDialog
from gamecat.models.segment import Segment
from gamecat.utils.decorators import requires_project



class TranslationMemoryMixin:
    """Obsługa pamięci tłumaczeniowej (TM) w oknie głównym."""

    def _update_current_tm(self, segment: Segment) -> None:
        """Policz sugestie TM w tle dla bieżącego szkicu; nieaktualne wyniki są odrzucane."""
        self._tm_generation += 1
        token = self._tm_generation
        service, project = self.project_service, self.current_project
        if service is None or project is None or segment.id is None or self._closing:
            self.tm_panel.set_matches([])
            return
        segment_id, source, target, position = segment.id, segment.source, segment.target, segment.position
        # The editor may display an uncommitted target; use that exact draft
        # for current-segment highlighting rather than the SQLite snapshot.
        selected = self.segment_editor.current_segment()
        target_editor = getattr(self.segment_editor, 'target_edit', None)
        if selected is not None and selected.id == segment_id and target_editor is not None:
            target = target_editor.toPlainText()
        self._tm_last_requested = (segment_id, source, target)
        pending = getattr(self, '_tm_future', None)
        if pending is not None:
            pending.cancel()
        future = service.find_tm_matches_async(
            project, source, limit=5,
            current_segment_id=segment_id,
            current_target=target,
            current_position=position,
        )
        self._tm_future = future

        def poll() -> None:
            if self._closing or token != self._tm_generation or self.project_service is not service:
                return
            if not future.done():
                QTimer.singleShot(50, poll)
                return
            active = self.segment_editor.current_segment()
            active_editor = getattr(self.segment_editor, 'target_edit', None)
            active_target = active_editor.toPlainText() if active_editor is not None else (active.target if active else None)
            if (active is None or active.id != segment_id or active.source != source
                    or active_target != target):
                return
            try:
                self.tm_panel.set_matches(future.result())
            except Exception as exc:
                self.tm_panel.set_matches([])
                self.statusBar().showMessage(f'Błąd wyszukiwania TM: {exc}', 5000)

        QTimer.singleShot(0, poll)

    def _refresh_tm_context(self) -> None:
        """Odśwież sugestie TM dla bieżącego segmentu."""
        segment = self.segment_editor.current_segment()
        if segment is not None:
            self._update_current_tm(segment)
        else:
            self.tm_panel.set_matches([])

    def _update_tm_threshold(self, threshold: float) -> None:
        """Zapisz nowy próg sugestii TM; przy błędzie przywróć poprzednią wartość."""
        if self.project_service is None or self.current_project is None:
            return
        try:
            self.project_service.set_tm_threshold(self.current_project, threshold)
            self._refresh_tm_context()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można zmienić progu TM:\n{exc}')
            self.tm_panel.set_threshold(self.project_service.get_tm_threshold(self.current_project))

    def _safe_attach_tm_database(self) -> None:
        """Wybierz lub utwórz zewnętrzną bazę TM i powiąż ją z projektem."""
        if self.current_project is None or self.project_service is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, 'Otwórz lub utwórz zewnętrzną bazę TM',
            'translation_memory.sqlite', 'SQLite (*.sqlite *.db)'
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix('.sqlite')
        if path.suffix.casefold() not in {'.sqlite', '.db'}:
            QMessageBox.warning(self, 'GameCAT', 'Baza TM musi mieć rozszerzenie .sqlite lub .db.')
            return
        try:
            self.project_service.attach_tm_database(self.current_project, path)
        except Exception as exc:
            QMessageBox.critical(self, 'GameCAT', f'Nie można podłączyć TM:\n{exc}')
            return
        self.tm_panel.set_storage_path(path)
        self._refresh_tm_context()
        self._refresh_search_context()
        self.statusBar().showMessage(f'Aktywna zewnętrzna TM: {path}', 7000)

    def _safe_use_project_tm_database(self) -> None:
        """Przełącz projekt na TM zapisaną w pliku projektu."""
        if self.current_project is None or self.project_service is None:
            return
        try:
            self.project_service.use_project_tm_database(self.current_project)
        except Exception as exc:
            QMessageBox.critical(self, 'GameCAT', f'Nie można zmienić TM:\n{exc}')
            return
        self.tm_panel.set_storage_path(None)
        self._ai_preview_context = None
        self._refresh_tm_context()
        self._refresh_search_context()
        self.statusBar().showMessage('Aktywna pamięć TM w projekcie.', 5000)

    def _safe_import_tm(self) -> None:
        """Wybierz plik CSV/JSON i zaimportuj pary do aktywnej TM w tle."""
        if self.current_project is None or self.project_service is None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Importuj pamięć tłumaczeniową',
            filter='TM (*.csv *.json);;CSV (*.csv);;JSON (*.json)'
        )
        if not filename:
            return
        path = Path(filename)
        future = self.project_service.import_tm_file_async(self.current_project, path)
        self._watch_future(
            future,
            lambda count: self._tm_imported(count),
            'Import TM',
        )

    def _tm_imported(self, count: int) -> None:
        """Po imporcie TM odśwież sugestie i filtry oraz pokaż liczbę nowych par."""
        self._refresh_tm_context()
        self._refresh_search_context()
        self.statusBar().showMessage(f'TM: dodano {count} nowych par (bez duplikatów).', 6000)

    def _safe_export_tm(self) -> None:
        """Wybierz plik docelowy i wyeksportuj aktywną TM w tle."""
        if self.current_project is None or self.project_service is None:
            return
        filename, selected_filter = QFileDialog.getSaveFileName(
            self, 'Eksportuj aktywną TM', 'translation_memory.csv',
            'CSV (*.csv);;JSON (*.json)'
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix('.json' if selected_filter.startswith('JSON') else '.csv')
        if path.suffix.casefold() not in {'.json', '.csv'}:
            QMessageBox.warning(self, 'GameCAT', 'Eksport TM obsługuje tylko CSV/JSON.')
            return
        future = self.project_service.export_tm_file_async(self.current_project, path)
        self._watch_future(
            future,
            lambda count: self.statusBar().showMessage(
                f'Wyeksportowano {count} par TM do {path}.', 6000
            ),
            'Eksport TM',
        )

    def _safe_sync_tm(self) -> None:
        """Dodaj przetłumaczone segmenty do TM, pokazując ewentualny błąd."""
        try:
            self.sync_project_to_tm()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    def _safe_analyze_tm(self) -> None:
        """Otwórz analizę projektu względem TM, pokazując ewentualny błąd."""
        try:
            self.analyze_tm()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def analyze_tm(self) -> None:
        """Otwórz okno analizy projektu względem TM (sekwencyjnie / wątki / procesy)."""
        assert self.project_service is not None and self.current_project is not None
        dialog = TMAnalysisDialog(self.project_service, self.current_project, self)
        dialog.segments_changed.connect(self._reload_segments)
        dialog.exec()

    @requires_project
    def sync_project_to_tm(self) -> None:
        # @requires_project gwarantuje otwarty projekt; asserty zawężają typy.
        """Dodaj przetłumaczone segmenty projektu do aktywnej TM i odśwież sugestie."""
        assert self.project_service is not None and self.current_project is not None
        created = self.project_service.sync_project_to_tm(self.current_project)
        segment = self.segment_editor.current_segment()
        if segment is not None:
            self._update_current_tm(segment)
        self._refresh_search_context()
        self.statusBar().showMessage(f'TM: dodano {created} nowych par tłumaczeniowych.', 5000)
