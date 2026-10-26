from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from typing import Callable, TypeVar

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QFileDialog, QDockWidget, QLabel, QMainWindow, QMessageBox, QStatusBar

from gamecat.gui.csv_import_dialog import CsvImportDialog
from gamecat.gui.csv_translation_import_dialog import CsvTranslationImportDialog
from gamecat.gui.file_formats import export_format_from_path, normalized_export_path
from gamecat.gui.glossary_panel import GlossaryPanel
from gamecat.gui.project_dialog import ProjectDialog
from gamecat.gui.replace_dialog import BatchReplaceDialog
from gamecat.gui.qa_panel import QAPanel
from gamecat.gui.segment_editor import SegmentEditor
from gamecat.gui.tm_panel import TMPanel
from gamecat.gui.tm_analysis_dialog import TMAnalysisDialog
from gamecat.models.project import Project
from gamecat.models.glossary import GlossaryTerm
from gamecat.models.segment import Segment, SegmentStatus
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
        self.tm_panel.threshold_changed.connect(self._update_tm_threshold)
        self.segment_editor.segment_changed.connect(self._update_current_qa)
        self.segment_editor.segment_changed.connect(self._update_current_tm)
        self.segment_editor.segment_changed.connect(self._update_glossary_context)
        self.segment_editor.segment_modified.connect(self._on_segment_modified)
        self.segment_editor.search_context_requested.connect(self._refresh_search_context)
        self.segment_editor.segments_status_modified.connect(self._on_segments_status_modified)
        self.qa_panel.segment_requested.connect(self._select_qa_segment)
        self.glossary_panel.term_create_requested.connect(self._safe_create_glossary_term)
        self.glossary_panel.term_save_requested.connect(self._safe_save_glossary_term)
        self.glossary_panel.term_delete_requested.connect(self._safe_delete_glossary_term)
        self.glossary_panel.variant_add_requested.connect(self._safe_add_glossary_variant)
        self.glossary_panel.variant_delete_requested.connect(self._safe_remove_glossary_variant)
        self.glossary_panel.import_requested.connect(self._safe_import_glossary)
        self.glossary_panel.export_requested.connect(self._safe_export_glossary)
        self.glossary_panel.target_insert_requested.connect(self.segment_editor.insert_target_text)
        self.setStatusBar(QStatusBar())
        self._progress_indicator = QLabel('Postęp: —')
        self._progress_indicator.setToolTip('Postęp tłumaczenia / recenzji / zatwierdzania')
        self.statusBar().addPermanentWidget(self._progress_indicator)
        self._save_indicator = QLabel('Brak projektu')
        self.statusBar().addPermanentWidget(self._save_indicator)
        self._autosave_status_timer = QTimer(self)
        self._autosave_status_timer.setInterval(150)
        self._autosave_status_timer.timeout.connect(self._refresh_autosave_status)
        self._autosave_status_timer.start()
        self._build_actions()

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu('&Plik')
        new_action = QAction('Nowy projekt', self)
        new_action.triggered.connect(self.new_project)
        open_action = QAction('Otwórz', self)
        open_action.triggered.connect(self.open_project_dialog)
        self.import_action = QAction('Importuj plik źródłowy…', self)
        self.import_action.triggered.connect(self._safe_import)
        self.import_translation_action = QAction('Importuj tłumaczenie…', self)
        self.import_translation_action.triggered.connect(self._safe_import_translation)
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
            self.import_translation_action,
            self.export_action,
            self.save_action,
            exit_action,
        ):
            file_menu.addAction(action)

        edit_menu = self.menuBar().addMenu('&Edycja')
        self.replace_action = QAction('Zamień w Target…', self)
        self.replace_action.setShortcut(QKeySequence('Ctrl+H'))
        self.replace_action.triggered.connect(self._safe_replace_targets)
        edit_menu.addAction(self.replace_action)
        edit_menu.addSeparator()
        self.next_untranslated_action = QAction('Następny bez tłumaczenia', self)
        self.next_untranslated_action.setShortcut(QKeySequence('Ctrl+Alt+Down'))
        self.next_untranslated_action.triggered.connect(lambda: self._jump_to_segment('untranslated'))
        edit_menu.addAction(self.next_untranslated_action)
        self.prev_untranslated_action = QAction('Poprzedni bez tłumaczenia', self)
        self.prev_untranslated_action.setShortcut(QKeySequence('Ctrl+Alt+Up'))
        self.prev_untranslated_action.triggered.connect(lambda: self._jump_to_segment('untranslated', backwards=True))
        edit_menu.addAction(self.prev_untranslated_action)
        self.next_qa_action = QAction('Następny błąd QA', self)
        self.next_qa_action.setShortcut(QKeySequence('F8'))
        self.next_qa_action.triggered.connect(lambda: self._jump_to_segment('qa_errors'))
        edit_menu.addAction(self.next_qa_action)
        self.prev_qa_action = QAction('Poprzedni błąd QA', self)
        self.prev_qa_action.setShortcut(QKeySequence('Shift+F8'))
        self.prev_qa_action.triggered.connect(lambda: self._jump_to_segment('qa_errors', backwards=True))
        edit_menu.addAction(self.prev_qa_action)

        qa_menu = self.menuBar().addMenu('&QA')
        self.run_project_qa_action = QAction('Sprawdź cały projekt', self)
        self.run_project_qa_action.setShortcut(QKeySequence('Ctrl+Shift+Q'))
        self.run_project_qa_action.triggered.connect(self._safe_run_project_qa)
        qa_menu.addAction(self.run_project_qa_action)

        workflow_menu = self.menuBar().addMenu('&Workflow')
        self.status_actions: list[QAction] = []
        status_shortcuts = {
            SegmentStatus.NEW: 'Ctrl+1',
            SegmentStatus.TRANSLATED: 'Ctrl+2',
            SegmentStatus.REVIEWED: 'Ctrl+3',
            SegmentStatus.APPROVED: 'Ctrl+4',
        }
        for status in SegmentStatus:
            action = QAction(f'Ustaw {status.value}', self)
            action.setShortcut(QKeySequence(status_shortcuts[status]))
            action.triggered.connect(
                lambda checked=False, selected=status: self.segment_editor.set_selected_status(selected)
            )
            workflow_menu.addAction(action)
            self.status_actions.append(action)

        tm_menu = self.menuBar().addMenu('&TM')
        self.sync_tm_action = QAction('Dodaj tłumaczenia projektu do pamięci', self)
        self.sync_tm_action.triggered.connect(self._safe_sync_tm)
        tm_menu.addAction(self.sync_tm_action)
        self.analyze_tm_action = QAction('Analiza projektu względem TM…', self)
        self.analyze_tm_action.setShortcut(QKeySequence('Ctrl+Shift+A'))
        self.analyze_tm_action.triggered.connect(self._safe_analyze_tm)
        tm_menu.addAction(self.analyze_tm_action)
        tm_menu.addSeparator()
        self.attach_tm_action = QAction('Wybierz zewnętrzną bazę TM…', self)
        self.attach_tm_action.triggered.connect(self._safe_attach_tm_database)
        tm_menu.addAction(self.attach_tm_action)
        self.internal_tm_action = QAction('Użyj TM w bazie projektu', self)
        self.internal_tm_action.triggered.connect(self._safe_use_project_tm_database)
        tm_menu.addAction(self.internal_tm_action)
        tm_menu.addSeparator()
        self.import_tm_action = QAction('Importuj TM (CSV/JSON)…', self)
        self.import_tm_action.triggered.connect(self._safe_import_tm)
        tm_menu.addAction(self.import_tm_action)
        self.export_tm_action = QAction('Eksportuj TM (CSV/JSON)…', self)
        self.export_tm_action.triggered.connect(self._safe_export_tm)
        tm_menu.addAction(self.export_tm_action)
        self._sync_actions()

    def _sync_actions(self) -> None:
        enabled = self.current_project is not None and not self._busy
        for action in (self.import_action, self.import_translation_action, self.export_action, self.save_action, self.run_project_qa_action, self.sync_tm_action, self.analyze_tm_action, self.attach_tm_action, self.internal_tm_action, self.import_tm_action, self.export_tm_action, self.replace_action, self.next_untranslated_action, self.prev_untranslated_action, self.next_qa_action, self.prev_qa_action):
            action.setEnabled(enabled)
        for action in self.status_actions:
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
        self.segment_editor.clear_filters()
        self.segment_editor.set_segments([])
        self.glossary_panel.set_terms([])
        self.tm_panel.set_matches([])
        self.tm_panel.set_threshold(0.45)
        self.tm_panel.set_storage_path(None)
        self.qa_panel.set_issues([])
        self.qa_panel.clear_project_report()
        self.setWindowTitle(f'GameCAT — {persisted.name}')
        self._refresh_progress()
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
        self.glossary_panel.set_terms(service.list_glossary(project.id))
        self.tm_panel.set_matches([])
        self.tm_panel.set_threshold(service.get_tm_threshold(project))
        self.tm_panel.set_storage_path(service.tm_database_path(project))
        self.qa_panel.clear_project_report()
        self.segment_editor.clear_filters()
        self.segment_editor.set_segments(segments)
        self._refresh_progress()
        self.setWindowTitle(f'GameCAT — {project.name}')
        self.statusBar().showMessage(f'Otworzono: {path} ({len(segments)} segmentów)', 4000)
        self._sync_actions()

    @requires_project
    def save_project(self) -> None:
        assert self.project_service is not None
        self.project_service.flush_saves()
        self._refresh_autosave_status()
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
            self.project_service.queue_segment_save(segment)
            self._refresh_autosave_status()
        except Exception as exc:
            self._save_indicator.setText('Błąd zapisu')
            self.statusBar().showMessage(f'Błąd zapisu segmentu: {exc}', 5000)

    def _refresh_autosave_status(self) -> None:
        if self.project_service is None:
            self._save_indicator.setText('Brak projektu')
            return
        pending = self.project_service.pending_save_count
        if pending:
            self._save_indicator.setText(f'Autosave: zapisuję… ({pending})')
        else:
            self._save_indicator.setText('Autosave: zapisano')

    def _refresh_progress(self) -> None:
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

    def _refresh_glossary(self) -> None:
        if self.project_service is None or self.current_project is None:
            self.glossary_panel.set_terms([])
            return
        self.glossary_panel.set_terms(self.project_service.list_glossary(self.current_project.id))
        segment = self.segment_editor.current_segment()
        self.glossary_panel.set_source_context(segment.source if segment else '')

    def _update_glossary_context(self, segment: Segment) -> None:
        self.glossary_panel.set_source_context(segment.source)

    def _after_glossary_change(self, message: str) -> None:
        self._refresh_glossary()
        self._refresh_search_context()
        self.qa_panel.clear_project_report()
        segment = self.segment_editor.current_segment()
        if segment is not None:
            self._update_current_qa(segment)
        self.statusBar().showMessage(message, 5000)

    def _safe_create_glossary_term(self, term: GlossaryTerm) -> None:
        try:
            assert self.project_service is not None and self.current_project is not None
            self.project_service.create_glossary_term(self.current_project.id, term)
            self._after_glossary_change('Dodano termin do glosariusza.')
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można dodać terminu:\n{exc}')

    def _safe_save_glossary_term(self, term: GlossaryTerm) -> None:
        try:
            assert self.project_service is not None and self.current_project is not None
            self.project_service.save_glossary_term(self.current_project.id, term)
            self._after_glossary_change('Zapisano termin glosariusza.')
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można zapisać terminu:\n{exc}')

    def _safe_delete_glossary_term(self, term_id: int) -> None:
        try:
            assert self.project_service is not None and self.current_project is not None
            self.project_service.delete_glossary_term(self.current_project.id, term_id)
            self._after_glossary_change('Usunięto termin glosariusza.')
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można usunąć terminu:\n{exc}')

    def _safe_add_glossary_variant(self, term_id: int, target: str) -> None:
        try:
            assert self.project_service is not None and self.current_project is not None
            self.project_service.add_glossary_variant(self.current_project.id, term_id, target)
            self._after_glossary_change('Dodano wariant tłumaczenia.')
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można dodać wariantu:\n{exc}')

    def _safe_remove_glossary_variant(self, term_id: int, target: str) -> None:
        try:
            assert self.project_service is not None and self.current_project is not None
            self.project_service.remove_glossary_variant(self.current_project.id, term_id, target)
            self._after_glossary_change('Usunięto wariant tłumaczenia.')
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można usunąć wariantu:\n{exc}')
            self._refresh_glossary()

    def _safe_import_glossary(self) -> None:
        try:
            self.import_glossary()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def import_glossary(self) -> None:
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
        try:
            self.export_glossary()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def export_glossary(self) -> None:
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

    def _glossary_for_current_project(self):
        if self.project_service is None or self.current_project is None:
            return []
        return self.project_service.list_glossary(self.current_project.id)

    def _update_current_qa(self, segment: Segment) -> None:
        issues = validate_segment(segment.source, segment.target, self._glossary_for_current_project())
        self.qa_panel.set_issues(issues)

    def _update_current_tm(self, segment: Segment) -> None:
        if self.project_service is None or self.current_project is None:
            self.tm_panel.set_matches([])
            return
        matches = self.project_service.find_tm_matches(
            self.current_project, segment.source, limit=5, threshold=0.45
        )
        self.tm_panel.set_matches(matches)

    def _refresh_tm_context(self) -> None:
        segment = self.segment_editor.current_segment()
        if segment is not None:
            self._update_current_tm(segment)
        else:
            self.tm_panel.set_matches([])

    def _update_tm_threshold(self, threshold: float) -> None:
        if self.project_service is None or self.current_project is None:
            return
        try:
            self.project_service.set_tm_threshold(self.current_project, threshold)
            self._refresh_tm_context()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można zmienić progu TM:\n{exc}')
            self.tm_panel.set_threshold(self.project_service.get_tm_threshold(self.current_project))

    def _safe_attach_tm_database(self) -> None:
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
        if self.current_project is None or self.project_service is None:
            return
        try:
            self.project_service.use_project_tm_database(self.current_project)
        except Exception as exc:
            QMessageBox.critical(self, 'GameCAT', f'Nie można zmienić TM:\n{exc}')
            return
        self.tm_panel.set_storage_path(None)
        self._refresh_tm_context()
        self._refresh_search_context()
        self.statusBar().showMessage('Aktywna pamięć TM w projekcie.', 5000)

    def _safe_import_tm(self) -> None:
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
        self._refresh_tm_context()
        self._refresh_search_context()
        self.statusBar().showMessage(f'TM: dodano {count} nowych par (bez duplikatów).', 6000)

    def _safe_export_tm(self) -> None:
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
        try:
            self.sync_project_to_tm()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    def _safe_analyze_tm(self) -> None:
        try:
            self.analyze_tm()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def analyze_tm(self) -> None:
        assert self.project_service is not None and self.current_project is not None
        dialog = TMAnalysisDialog(self.project_service, self.current_project, self)
        dialog.segments_changed.connect(self._reload_segments)
        dialog.exec()

    def _reload_segments(self) -> None:
        if self.project_service is None or self.current_project is None:
            return
        self.segment_editor.set_segments(self.project_service.list_segments(self.current_project.id))
        self._refresh_search_context()
        self._refresh_progress()
        self.qa_panel.clear_project_report()

    @requires_project
    def sync_project_to_tm(self) -> None:
        # @requires_project gwarantuje otwarty projekt; asserty zawężają typy.
        assert self.project_service is not None and self.current_project is not None
        created = self.project_service.sync_project_to_tm(self.current_project)
        segment = self.segment_editor.current_segment()
        if segment is not None:
            self._update_current_tm(segment)
        self._refresh_search_context()
        self.statusBar().showMessage(f'TM: dodano {created} nowych par tłumaczeniowych.', 5000)

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
        # @requires_project gwarantuje otwarty projekt; asserty zawężają typy.
        assert self.project_service is not None and self.current_project is not None
        report = self.project_service.run_project_qa(self.current_project)
        self.qa_panel.set_project_report(report)
        self._refresh_search_context()
        self.statusBar().showMessage(
            f'QA: {report.issue_count} problemów w {report.issue_segment_count} z {report.segment_count} segmentów.',
            7000,
        )

    def _refresh_search_context(self, *_args, force_qa: bool = False) -> None:
        """Calculate quality indexes only when a filter/navigation needs them."""
        if self.project_service is None or self.current_project is None:
            self.segment_editor.set_search_context(qa_error_ids=set(), tm_match_ids=set())
            return
        quality = self.segment_editor.quality_filter.currentData()
        kwargs: dict[str, set[int]] = {}
        if force_qa or quality == 'qa_errors':
            glossary = self.project_service.list_glossary(self.current_project.id)
            kwargs['qa_error_ids'] = {
                segment.id for segment in self.segment_editor.all_segments()
                if segment.id is not None and validate_segment(segment.source, segment.target, glossary)
            }
        if quality == 'tm_match':
            project = self.current_project
            tm_sources = {
                entry.source for entry in self.project_service.translation_memory.list_for_languages(
                    project.source_language, project.target_language
                )
            }
            kwargs['tm_match_ids'] = {
                segment.id for segment in self.segment_editor.all_segments()
                if segment.id is not None and segment.source in tm_sources
            }
        self.segment_editor.set_search_context(**kwargs)

    def _jump_to_segment(self, kind: str, *, backwards: bool = False) -> None:
        if self.current_project is None:
            return
        current = self.segment_editor.current_segment()
        anchor_id = current.id if current is not None else None
        if kind == 'qa_errors':
            self._refresh_search_context(force_qa=True)
        if not self.segment_editor.jump_to_next(kind, backwards=backwards, anchor_id=anchor_id):
            self.statusBar().showMessage('Nie znaleziono pasującego segmentu.', 3500)

    def _safe_replace_targets(self) -> None:
        try:
            self.replace_targets()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', f'Nie można zamienić tekstu:\n{exc}')

    @requires_project
    def replace_targets(self) -> None:
        """Apply previewed changes to Target only, never silently to reviewed segments."""
        assert self.project_service is not None and self.current_project is not None
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
        # @requires_project gwarantuje otwarty projekt; asserty zawężają typy.
        assert self.project_service is not None and self.current_project is not None
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
            self._refresh_search_context()
            self._refresh_progress()
            self.statusBar().showMessage(
                f'Zaimportowano {len(new_segments)} segmentów z {path.name}. Łącznie: {len(all_segments)}.',
                6000,
            )

        self._watch_future(future, imported, 'Import')

    def _safe_import_translation(self) -> None:
        try:
            self.import_translation()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def import_translation(self) -> None:
        # @requires_project gwarantuje otwarty projekt; asserty zawężają typy.
        assert self.project_service is not None and self.current_project is not None
        if not self.project_service.list_segments(self.current_project.id):
            QMessageBox.information(self, 'GameCAT', 'Najpierw zaimportuj plik źródłowy.')
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            'Importuj tłumaczenie',
            filter='Obsługiwane pliki (*.txt *.csv *.json);;TXT (*.txt);;CSV (*.csv);;JSON (*.json)',
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.casefold() not in {'.txt', '.csv', '.json'}:
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

        self.statusBar().showMessage(f'Importowanie tłumaczenia: {path.name}...')
        future = self.project_service.import_translation_file_async(
            self.current_project, path, csv_columns
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
        try:
            self.export_segments()
        except Exception as exc:
            QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def export_segments(self) -> None:
        # @requires_project gwarantuje otwarty projekt; asserty zawężają typy.
        assert self.project_service is not None and self.current_project is not None
        if self.project_service.segments.count_for_project(self.current_project.id) == 0:
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
        future = self.project_service.export_project_async(self.current_project, path, format_name)

        def exported(count: int) -> None:
            self.statusBar().showMessage(
                f'Wyeksportowano {count} segmentów do {path}',
                6000,
            )

        self._watch_future(future, exported, 'Eksport')

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.project_service is not None:
            try:
                self.project_service.close()
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    'GameCAT',
                    f'Nie udało się zapisać wszystkich zmian przed zamknięciem:\n{exc}',
                )
                event.ignore()
                return
            self.project_service = None
        super().closeEvent(event)
