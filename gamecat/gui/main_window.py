from __future__ import annotations
from pathlib import Path
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QStatusBar, QWidget, QDockWidget
from gamecat.models.project import Project
from gamecat.utils.decorators import requires_project
from gamecat.gui.project_dialog import ProjectDialog
from gamecat.gui.segment_editor import SegmentEditor
from gamecat.gui.qa_panel import QAPanel
from gamecat.gui.glossary_panel import GlossaryPanel
from gamecat.gui.tm_panel import TMPanel


class MainWindow(QMainWindow):
    """Main GameCAT window; heavy work is delegated outside widgets."""
    def __init__(self):
        super().__init__()
        self.current_project: Project | None = None
        self.project_path: Path | None = None
        self.setWindowTitle('GameCAT')
        self.resize(1200, 760)
        self.segment_editor = SegmentEditor(self)
        self.setCentralWidget(self.segment_editor)
        self.qa_panel = QAPanel(self); self.glossary_panel = GlossaryPanel(self); self.tm_panel = TMPanel(self)
        for title, widget in [('QA', self.qa_panel), ('Glosariusz', self.glossary_panel), ('TM', self.tm_panel)]:
            dock = QDockWidget(title, self); dock.setWidget(widget); self.addDockWidget(__import__('PySide6').QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.tm_panel.target_selected.connect(self.segment_editor.target_edit.setPlainText)
        self.setStatusBar(QStatusBar())
        self._build_actions()

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu('&Plik')
        new_action = QAction('Nowy projekt', self); new_action.triggered.connect(self.new_project)
        open_action = QAction('Otwórz', self); open_action.triggered.connect(self.open_project_dialog)
        self.import_action = QAction('Import', self); self.import_action.triggered.connect(self.import_segments)
        self.export_action = QAction('Eksport', self); self.export_action.triggered.connect(self.export_segments)
        self.save_action = QAction('Zapisz', self); self.save_action.setShortcut(QKeySequence.StandardKey.Save); self.save_action.triggered.connect(self._safe_save)
        exit_action = QAction('Wyjście', self); exit_action.triggered.connect(self.close)
        for action in (new_action, open_action, self.import_action, self.export_action, self.save_action, exit_action): file_menu.addAction(action)
        self._sync_actions()

    def _sync_actions(self) -> None:
        enabled = self.current_project is not None
        for action in (self.import_action, self.export_action, self.save_action): action.setEnabled(enabled)

    def new_project(self) -> None:
        dialog = ProjectDialog(self)
        if dialog.exec():
            project = dialog.project()
            if not project.name:
                QMessageBox.warning(self, 'GameCAT', 'Nazwa projektu nie może być pusta.')
                return
            self.current_project = project
            self.statusBar().showMessage(f'Projekt: {project.name}')
            self._sync_actions()

    def open_project_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'Otwórz projekt', filter='GameCAT SQLite (*.sqlite *.db);;Wszystkie pliki (*)')
        if path:
            self.project_path = Path(path)
            self.statusBar().showMessage(f'Wybrano: {path}')

    @requires_project
    def save_project(self) -> None:
        self.statusBar().showMessage('Projekt zapisany', 2500)

    def _safe_save(self) -> None:
        try: self.save_project()
        except RuntimeError as exc: QMessageBox.warning(self, 'GameCAT', str(exc))

    @requires_project
    def import_segments(self) -> None:
        self.statusBar().showMessage('Import będzie wykonany w tle')

    @requires_project
    def export_segments(self) -> None:
        self.statusBar().showMessage('Eksport będzie wykonany w tle')
