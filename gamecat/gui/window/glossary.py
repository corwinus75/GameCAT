"""Obsługa glosariusza projektu w oknie głównym."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from gamecat.models.glossary import GlossaryTerm
from gamecat.models.segment import Segment
from gamecat.utils.decorators import requires_project



class GlossaryMixin:
    """Obsługa glosariusza projektu w oknie głównym."""

    def _open_full_glossary(self) -> None:
        """Pokaż okno pełnego glosariusza."""
        self.glossary_dialog.show()
        self.glossary_dialog.raise_()
        self.glossary_dialog.activateWindow()

    def _refresh_glossary(self) -> None:
        """Wczytaj glosariusz projektu do wszystkich paneli i pola Source."""
        terms = (self.project_service.list_glossary(self.current_project.id)
                 if self.project_service is not None and self.current_project is not None else [])
        self.glossary_panel.set_terms(terms)
        self.context_glossary_panel.set_terms(terms)
        self.segment_editor.source_edit.set_glossary_terms(terms)
        segment = self.segment_editor.current_segment()
        self._update_glossary_context(segment)

    def _update_glossary_context(self, segment: Segment | None) -> None:
        """Przekaż Source bieżącego segmentu do paneli glosariusza."""
        source = segment.source if segment else ''
        self.context_glossary_panel.set_source_context(source)
        self.glossary_panel.set_source_context(source)

    def _after_glossary_change(self, message: str) -> None:
        """Po zmianie glosariusza odśwież panele, filtry i QA oraz pokaż komunikat."""
        self._refresh_glossary()
        self._refresh_search_context()
        self.qa_panel.clear_project_report()
        segment = self.segment_editor.current_segment()
        if segment is not None:
            self._update_current_qa(segment)
        self.statusBar().showMessage(message, 5000)

    def _safe_create_glossary_term(self, term: GlossaryTerm) -> None:
        """Dodaj termin glosariusza, pokazując ewentualny błąd."""
        try:
            assert self.project_service is not None and self.current_project is not None
            self.project_service.create_glossary_term(self.current_project.id, term)
            self._after_glossary_change('Dodano termin do glosariusza.')
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można dodać terminu:\n{exc}')

    def _safe_save_glossary_term(self, term: GlossaryTerm) -> None:
        """Zapisz termin glosariusza, pokazując ewentualny błąd."""
        try:
            assert self.project_service is not None and self.current_project is not None
            self.project_service.save_glossary_term(self.current_project.id, term)
            self._after_glossary_change('Zapisano termin glosariusza.')
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można zapisać terminu:\n{exc}')

    def _safe_delete_glossary_term(self, term_id: int) -> None:
        """Usuń termin glosariusza, pokazując ewentualny błąd."""
        try:
            assert self.project_service is not None and self.current_project is not None
            self.project_service.delete_glossary_term(self.current_project.id, term_id)
            self._after_glossary_change('Usunięto termin glosariusza.')
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można usunąć terminu:\n{exc}')

    def _safe_add_glossary_variant(self, term_id: int, target: str) -> None:
        """Dodaj wariant terminu, pokazując ewentualny błąd."""
        try:
            assert self.project_service is not None and self.current_project is not None
            self.project_service.add_glossary_variant(self.current_project.id, term_id, target)
            self._after_glossary_change('Dodano wariant tłumaczenia.')
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można dodać wariantu:\n{exc}')

    def _safe_remove_glossary_variant(self, term_id: int, target: str) -> None:
        """Usuń wariant terminu; przy błędzie przywróć stan panelu."""
        try:
            assert self.project_service is not None and self.current_project is not None
            self.project_service.remove_glossary_variant(self.current_project.id, term_id, target)
            self._after_glossary_change('Usunięto wariant tłumaczenia.')
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można usunąć wariantu:\n{exc}')
            self._refresh_glossary()

    def _safe_import_glossary(self) -> None:
        """Importuj glosariusz, pokazując ewentualny błąd."""
        try:
            self.import_glossary()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def import_glossary(self) -> None:
        """Wybierz plik CSV/JSON i zaimportuj glosariusz w tle."""
        assert self.project_service is not None and self.current_project is not None
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Importuj glosariusz', filter='Glosariusz (*.csv *.json);;CSV (*.csv);;JSON (*.json)'
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.casefold() not in {'.csv', '.json'}:
            QMessageBox.warning(self, 'GameCAT', 'Glosariusz obsługuje tylko CSV i JSON.')
            return
        future = self.project_service.import_glossary_file_async(self.current_project.id, path)

        def imported(result) -> None:
            self._after_glossary_change(
                f'Import glosariusza: nowe terminy {result.new_terms}, warianty {result.new_variants}, '
                f'duplikaty {result.duplicates}, błędne rekordy {result.invalid_rows}.'
            )
        self._watch_future(future, imported, 'Import glosariusza')

    def _safe_export_glossary(self) -> None:
        """Eksportuj glosariusz, pokazując ewentualny błąd."""
        try:
            self.export_glossary()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def export_glossary(self) -> None:
        """Wybierz plik docelowy i wyeksportuj glosariusz w tle."""
        assert self.project_service is not None and self.current_project is not None
        filename, selected_filter = QFileDialog.getSaveFileName(
            self, 'Eksportuj glosariusz', 'glossary.csv', 'CSV (*.csv);;JSON (*.json)'
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix('.json' if selected_filter.startswith('JSON') else '.csv')
        if path.suffix.casefold() not in {'.csv', '.json'}:
            QMessageBox.warning(self, 'GameCAT', 'Glosariusz obsługuje tylko CSV i JSON.')
            return
        future = self.project_service.export_glossary_file_async(self.current_project.id, path)
        self._watch_future(
            future,
            lambda count: self.statusBar().showMessage(f'Wyeksportowano {count} terminów/wariantów do {path}.', 6000),
            'Eksport glosariusza',
        )

    def _glossary_for_current_project(self) -> list[GlossaryTerm]:
        """Zwróć glosariusz otwartego projektu (pusta lista bez projektu)."""
        if self.project_service is None or self.current_project is None:
            return []
        return self.project_service.list_glossary(self.current_project.id)
