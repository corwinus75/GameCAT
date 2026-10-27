"""Okno główne aplikacji GameCAT (PySide6)."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from queue import Queue
from threading import Event
from pathlib import Path
from typing import Callable, TypeVar

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow, QMessageBox, QStatusBar, QDialog, QVBoxLayout

from gamecat.gui.history_panel import HistoryPanel
from gamecat.gui.glossary_panel import GlossaryPanel
from gamecat.gui.context_glossary_panel import ContextGlossaryPanel
from gamecat.gui.ai_panel import AIPanel
from gamecat.ai.core import AIResult, BatchItem
from gamecat.ai.credentials import CredentialStore
from gamecat.gui.qa_panel import QAPanel
from gamecat.gui.segment_editor import SegmentEditor
from gamecat.gui.tm_panel import TMPanel
from gamecat.models.project import Project
from gamecat.services.project_service import ProjectService
from gamecat.gui.window.ai import AIMixin
from gamecat.gui.window.editing import EditingMixin
from gamecat.gui.window.files import FileExchangeMixin
from gamecat.gui.window.glossary import GlossaryMixin
from gamecat.gui.window.menu import MenuMixin
from gamecat.gui.window.project import ProjectMixin
from gamecat.gui.window.quality import QualitySearchMixin
from gamecat.gui.window.tm import TranslationMemoryMixin

T = TypeVar('T')


class MainWindow(
    MenuMixin,
    ProjectMixin,
    EditingMixin,
    GlossaryMixin,
    TranslationMemoryMixin,
    QualitySearchMixin,
    FileExchangeMixin,
    AIMixin,
    QMainWindow,
):
    """Okno główne GameCAT.

    Klasa tworzy widżety, panele boczne i połączenia sygnałów, a logikę
    poszczególnych obszarów dziedziczy z mixinów z pakietu
    :mod:`gamecat.gui.window`. Operacje plikowe i analizy są wykonywane
    asynchronicznie, a wynik odbierany w wątku GUI przez ``QTimer``.
    """

    def __init__(self) -> None:
        """Zbuduj okno, panele i połączenia sygnałów; projekt nie jest otwarty."""
        super().__init__()
        self.current_project: Project | None = None
        self.project_path: Path | None = None
        self.project_service: ProjectService | None = None
        self._busy = False
        # Async callbacks can fire as soon as widget signals are connected.
        # Initialize every generation counter, future, and lifecycle flag first.
        self._closing = False
        self._tm_generation = 0
        self._qa_generation = 0
        self._quality_generation = 0
        self._content_generation = 0
        self._tm_future: Future | None = None
        self._tm_last_requested: tuple[int, str, str] | None = None
        self._qa_future: Future | None = None
        self._quality_future: Future | None = None
        self._pending_qa_jump: tuple[bool, int | None] | None = None
        self._ai_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='gamecat-openai')
        self._ai_cancel = Event()
        self._ai_running = False
        self._ai_preview_context: tuple[int, int, str, str, AIResult] | None = None
        self._ai_batch_results: list[BatchItem] = []
        self._ai_progress_queue: Queue[tuple[int, int]] = Queue()
        self._credentials = CredentialStore()

        self.setWindowTitle('GameCAT')
        self.resize(1200, 760)
        self.segment_editor = SegmentEditor(self)
        self.setCentralWidget(self.segment_editor)
        self.qa_panel = QAPanel(self)
        self.glossary_dialog = QDialog(self)
        self.glossary_dialog.setWindowTitle('GameCAT — cały glosariusz')
        self.glossary_dialog.resize(850, 630)
        self.glossary_panel = GlossaryPanel(self.glossary_dialog)
        QVBoxLayout(self.glossary_dialog).addWidget(self.glossary_panel)
        self.context_glossary_panel = ContextGlossaryPanel(self)
        self.tm_panel = TMPanel(self)
        self.ai_panel = AIPanel(self)
        self.history_panel = HistoryPanel(self)
        self._dock_widgets = {}
        for title, widget in (
            ('QA', self.qa_panel),
            ('Glosariusz', self.context_glossary_panel),
            ('TM', self.tm_panel),
            ('Historia', self.history_panel),
            ('OpenAI', self.ai_panel),
        ):
            dock = QDockWidget(title, self)
            dock.setWidget(widget)
            self._dock_widgets[title] = dock
            if title == 'OpenAI':
                self._ai_dock = dock
            self.addDockWidget(
                __import__('PySide6').QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
                dock,
            )
        # All right-side docks share one tab group on first launch.
        docks = list(self._dock_widgets.values())
        for other in docks[1:]:
            self.tabifyDockWidget(docks[0], other)
        docks[0].raise_()
        self.tm_panel.target_selected.connect(self.segment_editor.target_edit.setPlainText)
        self.tm_panel.threshold_changed.connect(self._update_tm_threshold)
        self.segment_editor.segment_changed.connect(self._update_current_qa)
        self.segment_editor.segment_changed.connect(self._update_current_tm)
        self.segment_editor.segment_changed.connect(self._update_glossary_context)
        self.segment_editor.segment_modified.connect(self._on_segment_modified)
        self.segment_editor.action_requested.connect(self._on_segment_action_requested)
        self.segment_editor.draft_changed.connect(self._on_editor_draft_changed)
        self.segment_editor.segment_changed.connect(self._update_history)
        self.segment_editor.segment_changed.connect(
            lambda segment: self._on_editor_draft_changed(segment, self.segment_editor.target_edit.toPlainText())
            if segment.id in self.segment_editor._drafts else None)
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
        self.context_glossary_panel.target_insert_requested.connect(self.segment_editor.insert_target_text)
        self.context_glossary_panel.open_full_requested.connect(self._open_full_glossary)
        self.segment_editor.source_edit.target_insert_requested.connect(self.segment_editor.insert_target_text)
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
        self.ai_panel.save_requested.connect(self._save_ai_settings)
        self.ai_panel.test_requested.connect(self._test_ai_connection)
        self.ai_panel.translate_requested.connect(self._translate_ai_current)
        self.ai_panel.batch_requested.connect(self._translate_ai_batch)
        self.ai_panel.cancel_requested.connect(self._cancel_ai_batch)
        self.ai_panel.apply_requested.connect(self._apply_ai_preview)
        self.ai_panel.batch_item_requested.connect(self._preview_ai_batch_item)
        self._build_actions()


    def _replace_service(self, service: ProjectService | None) -> None:
        """Podmień aktywną usługę projektu i zamknij poprzednią (opróżnia kolejkę zapisów)."""
        old = self.project_service
        self.project_service = service
        if old is not None and old is not service:
            old.close()


    def _watch_future(
        self,
        future: Future[T],
        on_success: Callable[[T], None],
        operation_name: str,
    ) -> None:
        """Obserwuj zadanie z puli wątków i wywołaj *on_success* w wątku GUI.

        Stan ``Future`` jest odpytywany co 50 ms przez ``QTimer``, więc widżety
        nigdy nie są modyfikowane z wątku roboczego. Wyjątek z zadania jest
        pokazywany użytkownikowi jako komunikat o błędzie operacji.
        """
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


    def closeEvent(self, event: QCloseEvent) -> None:
        """Zamknij okno po potwierdzeniu szkiców i zadań AI; utrwal zapisy w SQLite."""
        if self.segment_editor.has_unsaved_drafts:
            answer = QMessageBox.question(
                self, 'Niezapisane tłumaczenia',
                'Istnieją niezapisane szkice. Zamknąć program i je odrzucić?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self._ai_running:
            answer = QMessageBox.question(
                self, 'OpenAI', 'Tłumaczenie API nadal trwa. Anulować dalsze żądania i zamknąć?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._ai_cancel.set()
        self._closing = True
        self._tm_generation += 1
        self._qa_generation += 1
        self._quality_generation += 1
        for pending in (self._tm_future, self._qa_future, self._quality_future):
            if pending is not None:
                pending.cancel()
        if self.project_service is not None:
            try:
                self.project_service.close()
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    'GameCAT',
                    f'Nie udało się zapisać wszystkich zmian przed zamknięciem:\n{exc}',
                )
                self._closing = False
                event.ignore()
                return
            self.project_service = None
        self.segment_editor.stop_search()
        self._ai_executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)
