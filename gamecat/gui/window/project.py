"""Tworzenie, otwieranie i zapisywanie projektów w oknie głównym."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog

from gamecat.ai.core import AISettings
from gamecat.gui.project_dialog import ProjectDialog
from gamecat.services.project_service import ProjectService
from gamecat.utils.decorators import requires_project



class ProjectMixin:
    """Tworzenie, otwieranie i zapisywanie projektów w oknie głównym."""

    def _confirm_discard_drafts(self) -> bool:
        """Zapytaj o odrzucenie niezapisanych szkiców; ``True``, gdy można kontynuować."""
        if not self.segment_editor.has_unsaved_drafts:
            return True
        return QMessageBox.question(
            self, 'Niezapisane szkice', 'Odrzucić niezapisane szkice?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def new_project(self) -> None:
        """Utwórz nowy projekt w wybranym pliku SQLite i ustaw go jako bieżący."""
        if self._ai_running:
            QMessageBox.warning(self, 'OpenAI', 'Poczekaj na zakończenie tłumaczenia AI.')
            return
        if not self._confirm_discard_drafts():
            return
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
        self.history_panel.set_history([])
        self.glossary_panel.set_terms([])
        self.context_glossary_panel.set_terms([])
        self.segment_editor.source_edit.set_glossary_terms([])
        self.tm_panel.set_matches([])
        self.tm_panel.set_threshold(0.45)
        self.tm_panel.set_storage_path(None)
        self.ai_panel.set_settings(AISettings())
        self._ai_preview_context = None
        self.qa_panel.set_issues([])
        self.qa_panel.clear_project_report()
        self.setWindowTitle(f'GameCAT — {persisted.name}')
        self._refresh_progress()
        self.statusBar().showMessage(f'Projekt utworzony: {path}', 4000)
        self._sync_actions()

    def open_project_dialog(self) -> None:
        """Otwórz istniejący plik projektu.

        Gdy plik zawiera kilka projektów, użytkownik wybiera jeden z nich; wraz
        z projektem ładowana jest powiązana z nim zewnętrzna TM.
        """
        if getattr(getattr(self, 'segment_editor', None), 'has_unsaved_drafts', False):
            answer = QMessageBox.question(
                self, 'Niezapisane szkice',
                'Odrzucić niezapisane szkice i otworzyć inny projekt?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if self._ai_running:
            QMessageBox.warning(self, 'OpenAI', 'Poczekaj na zakończenie tłumaczenia AI.')
            return
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
            if len(projects) == 1:
                project = projects[0]
            else:
                labels = [
                    f'{p.name}  [ID: {p.id}]  {p.source_language} → {p.target_language}'
                    for p in projects
                ]
                label, accepted = QInputDialog.getItem(
                    self, 'Wybierz projekt', 'Projekt w bazie:', labels, 0, False
                )
                if not accepted:
                    service.close()
                    return
                project = projects[labels.index(label)]
            service.select_project(project)
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
        self.context_glossary_panel.set_terms(service.list_glossary(project.id))
        self.segment_editor.source_edit.set_glossary_terms(service.list_glossary(project.id))
        self.tm_panel.set_matches([])
        self.tm_panel.set_threshold(service.get_tm_threshold(project))
        self.tm_panel.set_storage_path(service.tm_database_path(project))
        self.ai_panel.set_settings(service.get_ai_settings(project))
        self._ai_preview_context = None
        self.qa_panel.clear_project_report()
        self.segment_editor.clear_filters()
        self.segment_editor.set_segments(segments)
        self._refresh_progress()
        self._update_history(self.segment_editor.current_segment()) if self.segment_editor.current_segment() else self.history_panel.set_history([])
        self.setWindowTitle(f'GameCAT — {project.name}')
        self.statusBar().showMessage(f'Otworzono: {path} ({len(segments)} segmentów)', 4000)
        self._sync_actions()

    @requires_project
    def save_project(self) -> None:
        """Opróżnij kolejkę zapisów w tle (granica trwałości) i potwierdź zapis na pasku stanu."""
        assert self.project_service is not None
        self.project_service.flush_saves()
        self._refresh_autosave_status()
        self.statusBar().showMessage('Projekt zapisany', 2500)
