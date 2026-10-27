"""Budowa menu, akcji i skrótów klawiszowych okna głównego."""
from __future__ import annotations


from PySide6.QtGui import QAction, QKeySequence

from gamecat.models.segment import SegmentStatus



class MenuMixin:
    """Budowa menu, akcji i skrótów klawiszowych okna głównego."""

    def _build_actions(self) -> None:
        """Utwórz menu, akcje i skróty klawiszowe oraz połącz je z metodami okna."""
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
        self.export_template_action = QAction('Eksportuj według oryginalnego szablonu…', self)
        self.export_template_action.triggered.connect(self._safe_export_template)
        self.save_action = QAction('Zapisz segment (TRANSLATED)', self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._safe_commit_current)
        exit_action = QAction('Wyjście', self)
        exit_action.triggered.connect(self.close)
        for action in (
            new_action,
            open_action,
            self.import_action,
            self.import_translation_action,
            self.export_action,
            self.export_template_action,
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
        ai_menu = self.menuBar().addMenu('OpenAI')
        ai_menu.addAction(self._ai_dock.toggleViewAction())
        ai_menu.addSeparator()
        ai_single = QAction('Tłumacz bieżący segment', self)
        ai_single.triggered.connect(self._translate_ai_current)
        ai_single.setShortcut(QKeySequence('Ctrl+Shift+T'))
        ai_menu.addAction(ai_single)
        ai_batch = QAction('Tłumacz wsadowo…', self)
        ai_batch.triggered.connect(self._translate_ai_batch)
        ai_menu.addAction(ai_batch)
        ai_settings = QAction('Zapisz ustawienia AI', self)
        ai_settings.triggered.connect(self._save_ai_settings)
        ai_menu.addAction(ai_settings)
        self._sync_actions()

    def _sync_actions(self) -> None:
        """Włącz akcje wymagające projektu tylko przy otwartym projekcie i bez trwającej operacji."""
        enabled = self.current_project is not None and not self._busy
        for action in (self.import_action, self.import_translation_action, self.export_action, self.export_template_action, self.save_action, self.run_project_qa_action, self.sync_tm_action, self.analyze_tm_action, self.attach_tm_action, self.internal_tm_action, self.import_tm_action, self.export_tm_action, self.replace_action, self.next_untranslated_action, self.prev_untranslated_action, self.next_qa_action, self.prev_qa_action):
            action.setEnabled(enabled)
        for action in self.status_actions:
            action.setEnabled(enabled)
