"""Import i eksport plików lokalizacyjnych z poziomu okna głównego."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from gamecat.gui.csv_import_dialog import CsvImportDialog
from gamecat.gui.format_mapping_dialog import FormatMappingDialog
from gamecat.localization.profiles import FormatProfile
from gamecat.gui.csv_translation_import_dialog import CsvTranslationImportDialog
from gamecat.gui.file_formats import export_format_from_path, normalized_export_path
from gamecat.models.segment import Segment
from gamecat.utils.decorators import requires_project



class FileExchangeMixin:
    """Import i eksport plików lokalizacyjnych z poziomu okna głównego."""

    def _configure_mapping(self, path: Path) -> bool:
        """Skonfiguruj mapowanie pól dla formatów strukturalnych; zwraca ``False`` po anulowaniu."""
        assert self.project_service is not None and self.current_project is not None
        fmt = path.suffix.lower().lstrip('.')
        if fmt not in {'json', 'tsv', 'xlsx', 'xml'}:
            return True
        current = (self.project_service.get_format_profile(self.current_project, fmt)
                   if self.project_service.has_format_profile(self.current_project, fmt) else None)
        dialog = FormatMappingDialog(path, current, self)
        if not dialog.exec():
            return False
        profile = dialog.selected_profile()
        if profile is None:
            self.project_service.clear_format_profile(self.current_project, fmt)
        else:
            self.project_service.set_format_profile(self.current_project, profile)
        return True

    def _safe_import(self) -> None:
        """Importuj plik źródłowy, pokazując ewentualny błąd w oknie komunikatu."""
        try:
            self.import_segments()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def import_segments(self) -> None:
        # @requires_project gwarantuje otwarty projekt; asserty zawężają typy.
        """Wybierz plik źródłowy, skonfiguruj mapowanie i zaimportuj segmenty w tle."""
        assert self.project_service is not None and self.current_project is not None
        filename, _ = QFileDialog.getOpenFileName(
            self,
            'Importuj plik źródłowy',
            filter='Obsługiwane pliki (*.txt *.csv *.json *.tsv *.xlsx *.xml);;TXT (*.txt);;CSV (*.csv);;JSON (*.json);;TSV (*.tsv);;Excel (*.xlsx);;XML (*.xml)',
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.casefold() not in {'.txt', '.csv', '.json', '.tsv', '.xlsx', '.xml'}:
            QMessageBox.warning(self, 'GameCAT', f'Nieobsługiwany format pliku: {path.suffix or "brak rozszerzenia"}')
            return

        csv_columns: tuple[str | None, str, str | None] | None = None
        if path.suffix.casefold() == '.csv':
            try:
                csv_dialog = CsvImportDialog(path, self)
            except (OSError, UnicodeError, ValueError) as exc:
                QMessageBox.critical(self, 'GameCAT', f'Nie można odczytać nagłówka CSV:\n{exc}')
                return
            if not csv_dialog.exec():
                return
            csv_columns = csv_dialog.columns()
            if csv_columns[0] == csv_columns[1]:
                QMessageBox.warning(self, 'GameCAT', 'Kolumna klucza i tekstu źródłowego muszą być różne.')
                return
            self.project_service.set_format_profile(self.current_project, FormatProfile(
                'csv', key_field=csv_columns[0] or '', source_field=csv_columns[1],
                target_field=csv_columns[2] or 'target',
                comment_field=csv_dialog.comment_column() or '',
            ))

        if not self._configure_mapping(path):
            return
        self.statusBar().showMessage(f'Importowanie: {path.name}...')
        future = self.project_service.import_file_async(self.current_project, path, csv_columns)

        def imported(new_segments: list[Segment]) -> None:
            assert self.project_service is not None
            assert self.current_project is not None
            all_segments = self.project_service.list_segments(self.current_project.id)
            self.qa_panel.clear_project_report()
            self.segment_editor.set_segments(all_segments)
            self._refresh_search_context()
            self._refresh_progress()
            self.statusBar().showMessage(
                f'Zaimportowano {len(new_segments)} segmentów z {path.name}. Łącznie: {len(all_segments)}.',
                6000,
            )

        self._watch_future(future, imported, 'Import')

    def _safe_import_translation(self) -> None:
        """Importuj tłumaczenie, pokazując ewentualny błąd w oknie komunikatu."""
        try:
            self.import_translation()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def import_translation(self) -> None:
        # @requires_project gwarantuje otwarty projekt; asserty zawężają typy.
        """Wybierz plik tłumaczenia i przypisz Target do istniejących segmentów w tle."""
        assert self.project_service is not None and self.current_project is not None
        if not self.project_service.list_segments(self.current_project.id):
            QMessageBox.information(self, 'GameCAT', 'Najpierw zaimportuj plik źródłowy.')
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            'Importuj tłumaczenie',
            filter='Obsługiwane pliki (*.txt *.csv *.json *.tsv *.xlsx *.xml);;TXT (*.txt);;CSV (*.csv);;JSON (*.json);;TSV (*.tsv);;Excel (*.xlsx);;XML (*.xml)',
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.casefold() not in {'.txt', '.csv', '.json', '.tsv', '.xlsx', '.xml'}:
            QMessageBox.warning(self, 'GameCAT', f'Nieobsługiwany format pliku: {path.suffix or "brak rozszerzenia"}')
            return

        csv_columns: tuple[str | None, str] | None = None
        if path.suffix.casefold() == '.csv':
            try:
                dialog = CsvTranslationImportDialog(path, self)
            except (OSError, UnicodeError, ValueError) as exc:
                QMessageBox.critical(self, 'GameCAT', f'Nie można odczytać nagłówka CSV:\n{exc}')
                return
            if not dialog.exec():
                return
            csv_columns = dialog.columns()
            if csv_columns[0] is not None and csv_columns[0] == csv_columns[1]:
                QMessageBox.warning(self, 'GameCAT', 'Kolumna klucza i tłumaczenia muszą być różne.')
                return

        translation_profile = None
        legacy_json = False
        fmt = path.suffix.lower().lstrip('.')
        if fmt in {'json', 'tsv', 'xlsx', 'xml'}:
            current = (self.project_service.get_format_profile(self.current_project, fmt)
                       if self.project_service.has_format_profile(self.current_project, fmt) else None)
            dialog = FormatMappingDialog(path, current, self)
            if not dialog.exec():
                return
            translation_profile = dialog.selected_profile()
            legacy_json = fmt == 'json' and translation_profile is None
        self.statusBar().showMessage(f'Importowanie tłumaczenia: {path.name}...')
        future = self.project_service.import_translation_file_async(
            self.current_project, path, csv_columns,
            format_profile=translation_profile, legacy_json=legacy_json,
        )

        def imported(result) -> None:
            assert self.project_service is not None
            assert self.current_project is not None
            rows = self.project_service.list_segments(self.current_project.id)
            self.qa_panel.clear_project_report()
            self.segment_editor.set_segments(rows)
            self._refresh_search_context()
            self._refresh_progress()
            self.statusBar().showMessage(
                f'Import tłumaczenia: zaktualizowano {result.updated}/{result.total}; '
                f'niedopasowane: {result.unmatched}.',
                7000,
            )

        self._watch_future(future, imported, 'Import tłumaczenia')

    def _safe_export(self) -> None:
        """Eksportuj tłumaczenie, pokazując ewentualny błąd w oknie komunikatu."""
        try:
            self.export_segments()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def export_segments(self) -> None:
        # @requires_project gwarantuje otwarty projekt; asserty zawężają typy.
        """Wybierz plik docelowy i wyeksportuj tłumaczenie projektu w tle."""
        assert self.project_service is not None and self.current_project is not None
        if self.project_service.count_segments(self.current_project.id) == 0:
            QMessageBox.information(self, 'GameCAT', 'Projekt nie zawiera segmentów do eksportu.')
            return

        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            'Eksportuj tłumaczenie',
            'translation',
            'TXT (*.txt);;CSV (*.csv);;JSON (*.json);;TSV (*.tsv);;Excel (*.xlsx);;XML (*.xml)',
        )
        if not filename:
            return
        selected_format = next((fmt for label, fmt in (('CSV','csv'),('JSON','json'),('TSV','tsv'),('Excel','xlsx'),('XML','xml')) if selected_filter.startswith(label)), 'txt')
        path = normalized_export_path(Path(filename), selected_format)
        try:
            format_name = export_format_from_path(path)
        except ValueError as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))
            return

        self.statusBar().showMessage(f'Eksportowanie: {path.name}...')
        future = self.project_service.export_project_async(self.current_project, path, format_name)

        def exported(count: int) -> None:
            self.statusBar().showMessage(
                f'Wyeksportowano {count} segmentów do {path}',
                6000,
            )

        self._watch_future(future, exported, 'Eksport')

    def _safe_export_template(self) -> None:
        """Eksportuj do szablonu, pokazując ewentualny błąd w oknie komunikatu."""
        try:
            self.export_template()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def export_template(self) -> None:
        """Skopiuj oryginalny plik gry i podmień w kopii tylko zmapowane wartości Target."""
        assert self.project_service is not None and self.current_project is not None
        template, _ = QFileDialog.getOpenFileName(
            self, 'Wskaż oryginalny plik gry (szablon)',
            filter='Formaty strukturalne (*.csv *.tsv *.xlsx *.json *.xml)',
        )
        if not template:
            return
        source = Path(template)
        fmt = source.suffix.lower().lstrip('.')
        if not self.project_service.has_format_profile(self.current_project, fmt):
            QMessageBox.warning(self, 'GameCAT',
                'Brak zapisanego profilu mapowania dla tego formatu. '
                'Najpierw zaimportuj plik źródłowy i skonfiguruj mapowanie.')
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, 'Zapisz wynik (nie zastępuj oryginału)',
            f'{source.stem}_pl{source.suffix}',
            f'{fmt.upper()} (*{source.suffix})',
        )
        if not destination:
            return
        output = Path(destination)
        if not output.suffix:
            output = output.with_suffix(source.suffix)
        if output.resolve() == source.resolve():
            QMessageBox.warning(self, 'GameCAT', 'Nie można nadpisać pliku źródłowego.')
            return
        if output.exists() and QMessageBox.question(
            self, 'GameCAT', f'Plik {output.name} już istnieje. Nadpisać?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.statusBar().showMessage('Eksport według szablonu w toku...')
        future = self.project_service.export_using_template_async(self.current_project, source, output)
        self._watch_future(future, lambda count: self.statusBar().showMessage(
            f'Zapisano {count} tłumaczeń w strukturze {output.name}.', 7000), 'Eksport według szablonu')
