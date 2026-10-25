from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from typing import Callable, TypeVar

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QFileDialog, QDockWidget, QMainWindow, QMessageBox, QStatusBar

from gamecat.gui.csv_import_dialog import CsvImportDialog
from gamecat.gui.file_formats import export_format_from_path, normalized_export_path
from gamecat.gui.glossary_panel import GlossaryPanel
from gamecat.gui.project_dialog import ProjectDialog
from gamecat.gui.qa_panel import QAPanel
from gamecat.gui.segment_editor import SegmentEditor
from gamecat.gui.tm_panel import TMPanel
from gamecat.models.project import Project
from gamecat.models.segment import Segment
from gamecat.qa.project_scan import scan_segments
from gamecat.qa.validator import validate_segment
from gamecat.services.project_service import ProjectService
from gamecat.utils.decorators import requires_project

T = TypeVar('T')


class MainWindow(QMainWindow):
    """Main GameCAT window with persistent projects and async file I/O."""

    def __init__(self):
        super().__init__()
        self.current_project: Project | None = None
        self.project_path: Path | None = None
        self.project_service: ProjectService | None = None
        self._busy = False

        self.setWindowTitle('GameCAT')
        self.resize(1200, 760)
        self.segment_editor = SegmentEditor(self)
        self.setCentralWidget(self.segment_editor)
        self.qa_panel = QAPanel(self)
        self.glossary_panel = GlossaryPanel(self)
        self.tm_panel = TMPanel(self)
        for title, widget in (
            ('QA', self.qa_panel),
            ('Glosariusz', self.glossary_panel),
            ('TM', self.tm_panel),
        ):
            dock = QDockWidget(title, self)
            dock.setWidget(widget)
            self.addDockWidget(
                __import__('PySide6').QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
                dock,
            )
        self.tm_panel.target_selected.connect(self.segment_editor.target_edit.setPlainText)
        self.segment_editor.segment_changed.connect(self._update_current_qa)
        self.segment_editor.segment_modified.connect(self._on_segment_modified)
        self.qa_panel.segment_requested.connect(self._select_qa_segment)
        self.setStatusBar(QStatusBar())
        self._build_actions()

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu('&Plik')
        new_action = QAction('Nowy projekt', self)
        new_action.triggered.connect(self.new_project)
        open_action = QAction('Otwórz', self)
        open_action.triggered.connect(self.open_project_dialog)
        self.import_action = QAction('Import', self)
        self.import_action.triggered.connect(self._safe_import)
        self.export_action = QAction('Eksport', self)
        self.export_action.triggered.connect(self._safe_export)
        self.save_action = QAction('Zapisz', self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._safe_save)
        exit_action = QAction('Wyjście', self)
        exit_action.triggered.connect(self.close)
        for action in (
            new_action,
            open_action,
            self.import_action,
            self.export_action,
            self.save_action,
            exit_action,
        ):
            file_menu.addAction(action)

        qa_menu = self.menuBar().addMenu('&QA')
        self.run_project_qa_action = QAction('Sprawdź cały projekt', self)
        self.run_project_qa_action.setShortcut(QKeySequence('Ctrl+Shift+Q'))
        self.run_project_qa_action.triggered.connect(self._safe_run_project_qa)
        qa_menu.addAction(self.run_project_qa_action)
        self._sync_actions()

    def _sync_actions(self) -> None:
        enabled = self.current_project is not None and not self._busy
        for action in (self.import_action, self.export_action, self.save_action, self.run_project_qa_action):
            action.setEnabled(enabled)

    def _replace_service(self, service: ProjectService | None) -> None:
        old = self.project_service
        self.project_service = service
        if old is not None and old is not service:
            old.close()

    def new_project(self) -> None:
        dialog = ProjectDialog(self)
        if not dialog.exec():
            return
        project = dialog.project()
        if not project.name:
            QMessageBox.warning(self, 'GameCAT', 'Nazwa projektu nie może być pusta.')
            return

        default_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in project.name).strip('_') or 'project'
        filename, _ = QFileDialog.getSaveFileName(
            self,
            'Zapisz projekt GameCAT',
            f'{default_name}.sqlite',
            'GameCAT SQLite (*.sqlite);;Wszystkie pliki (*)',
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix('.sqlite')
        try:
            service = ProjectService(path)
            persisted = service.create_project(
                project.name,
                project.source_language,
                project.target_language,
                project.source_format,
            )
        except Exception as exc:
            QMessageBox.critical(self, 'GameCAT', f'Nie można utworzyć projektu:\n{exc}')
            return

        self._replace_service(service)
        self.current_project = persisted
        self.project_path = path
        self.segment_editor.set_segments([])
        self.glossary_panel.set_entries([])
        self.qa_panel.set_issues([])
        self.qa_panel.clear_project_report()
        self.setWindowTitle(f'GameCAT — {persisted.name}')
        self.statusBar().showMessage(f'Projekt utworzony: {path}', 4000)
        self._sync_actions()

    def open_project_dialog(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            'Otwórz projekt',
            filter='GameCAT SQLite (*.sqlite *.db);;Wszystkie pliki (*)',
        )
        if not filename:
            return
        path = Path(filename)
        service: ProjectService | None = None
        try:
            service = ProjectService(path)
            projects = service.list_projects()
            if not projects:
                raise ValueError('Baza nie zawiera żadnego projektu GameCAT.')
            project = projects[0]
            segments = service.list_segments(project.id)
        except Exception as exc:
            if service is not None:
                service.close()
            QMessageBox.critical(self, 'GameCAT', f'Nie można otworzyć projektu:\n{exc}')
            return

        self._replace_service(service)
        self.current_project = project
        self.project_path = path
        self.glossary_panel.set_entries(service.list_glossary(project.id))
        self.qa_panel.clear_project_report()
        self.segment_editor.set_segments(segments)
        self.setWindowTitle(f'GameCAT — {project.name}')
        self.statusBar().showMessage(f'Otworzono: {path} ({len(segments)} segmentów)', 4000)
        self._sync_actions()

    @requires_project
    def save_project(self) -> None:
        if self.project_service is None:
            raise RuntimeError('Project service is unavailable')
        self.statusBar().showMessage('Projekt zapisany', 2500)

    def _safe_save(self) -> None:
        try:
            self.save_project()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    def _save_modified_segment(self, segment: Segment) -> None:
        if self.project_service is None or segment.id is None:
            return
        try:
            self.project_service.save_segment(segment)
        except Exception as exc:
            self.statusBar().showMessage(f'Błąd zapisu segmentu: {exc}', 5000)

    def _glossary_for_current_project(self):
        if self.project_service is None or self.current_project is None:
            return []
        return self.project_service.list_glossary(self.current_project.id)

    def _update_current_qa(self, segment: Segment) -> None:
        issues = validate_segment(segment.source, segment.target, self._glossary_for_current_project())
        self.qa_panel.set_issues(issues)

    def _on_segment_modified(self, segment: Segment) -> None:
        self._save_modified_segment(segment)
        self._update_current_qa(segment)

    def _select_qa_segment(self, segment_id: int) -> None:
        if not self.segment_editor.select_segment_by_id(segment_id, reveal=True):
            self.statusBar().showMessage(f'Nie znaleziono segmentu ID {segment_id}.', 4000)

    def _safe_run_project_qa(self) -> None:
        try:
            self.run_project_qa()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def run_project_qa(self) -> None:
        if self.project_service is None or self.current_project is None:
            raise RuntimeError('Project service is unavailable')
        segments = self.project_service.list_segments(self.current_project.id)
        glossary = self.project_service.list_glossary(self.current_project.id)
        report = scan_segments(segments, glossary)
        self.qa_panel.set_project_report(report)
        self.statusBar().showMessage(
            f'QA: {report.issue_count} problemów w {report.issue_segment_count} z {report.segment_count} segmentów.',
            7000,
        )

    def _watch_future(
        self,
        future: Future[T],
        on_success: Callable[[T], None],
        operation_name: str,
    ) -> None:
        self._busy = True
        self._sync_actions()

        def poll() -> None:
            if not future.done():
                QTimer.singleShot(50, poll)
                return
            self._busy = False
            self._sync_actions()
            try:
                result = future.result()
            except Exception as exc:
                QMessageBox.critical(self, 'GameCAT', f'{operation_name} nie powiódł się:\n{exc}')
                self.statusBar().showMessage(f'{operation_name}: błąd', 5000)
                return
            on_success(result)

        QTimer.singleShot(50, poll)

    def _safe_import(self) -> None:
        try:
            self.import_segments()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def import_segments(self) -> None:
        if self.project_service is None or self.current_project is None:
            raise RuntimeError('Project service is unavailable')
        filename, _ = QFileDialog.getOpenFileName(
            self,
            'Importuj plik źródłowy',
            filter='Obsługiwane pliki (*.txt *.csv *.json);;TXT (*.txt);;CSV (*.csv);;JSON (*.json)',
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.casefold() not in {'.txt', '.csv', '.json'}:
            QMessageBox.warning(self, 'GameCAT', f'Nieobsługiwany format pliku: {path.suffix or "brak rozszerzenia"}')
            return

        csv_columns: tuple[str, str, str | None] | None = None
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

        self.statusBar().showMessage(f'Importowanie: {path.name}...')
        future = self.project_service.import_file_async(self.current_project, path, csv_columns)

        def imported(new_segments: list[Segment]) -> None:
            assert self.project_service is not None
            assert self.current_project is not None
            all_segments = self.project_service.list_segments(self.current_project.id)
            self.qa_panel.clear_project_report()
            self.segment_editor.set_segments(all_segments)
            self.statusBar().showMessage(
                f'Zaimportowano {len(new_segments)} segmentów z {path.name}. Łącznie: {len(all_segments)}.',
                6000,
            )

        self._watch_future(future, imported, 'Import')

    def _safe_export(self) -> None:
        try:
            self.export_segments()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def export_segments(self) -> None:
        if self.project_service is None or self.current_project is None:
            raise RuntimeError('Project service is unavailable')
        segments = self.project_service.list_segments(self.current_project.id)
        if not segments:
            QMessageBox.information(self, 'GameCAT', 'Projekt nie zawiera segmentów do eksportu.')
            return

        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            'Eksportuj tłumaczenie',
            'translation.txt',
            'TXT (*.txt);;CSV (*.csv);;JSON (*.json)',
        )
        if not filename:
            return
        selected_format = 'csv' if selected_filter.startswith('CSV') else 'json' if selected_filter.startswith('JSON') else 'txt'
        path = normalized_export_path(Path(filename), selected_format)
        try:
            format_name = export_format_from_path(path)
        except ValueError as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))
            return

        self.statusBar().showMessage(f'Eksportowanie: {path.name}...')
        future = self.project_service.export_file_async(segments, path, format_name)

        def exported(_: None) -> None:
            self.statusBar().showMessage(
                f'Wyeksportowano {len(segments)} segmentów do {path}',
                6000,
            )

        self._watch_future(future, exported, 'Eksport')

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.project_service is not None:
            self.project_service.close()
            self.project_service = None
        super().closeEvent(event)
