import importlib.util
import os
from pathlib import Path

import pytest

HAS_QT = importlib.util.find_spec('PySide6') is not None


@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable')
def test_tm_analysis_dialog_shows_report_and_pretranslates(tmp_path: Path):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication, QMessageBox
    from gamecat.gui.tm_analysis_dialog import TMAnalysisDialog
    from gamecat.models.translation_memory import TranslationMemoryEntry
    from gamecat.services.project_service import ProjectService

    app = QApplication.instance() or QApplication([])
    src = tmp_path / 'src.txt'; src.write_text('Open the gate.\nSomething else\n', encoding='utf-8')
    service = ProjectService(tmp_path / 'p.sqlite')
    project = service.create_project('P', 'en', 'pl', 'txt')
    try:
        service.import_file_async(project, src).result(timeout=5)
        service.translation_memory.create(TranslationMemoryEntry('Open the gate.', 'Otwórz bramę.', 'en', 'pl'))
        dialog = TMAnalysisDialog(service, project)
        report = service.analyze_project_tm(project, mode='sequential')
        dialog.show_report(report)
        assert dialog.table.item(0, 1).text() == '1'
        assert dialog.apply_button.isEnabled()
        emitted = []
        dialog.segments_changed.connect(lambda: emitted.append(True))
        original = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        try:
            dialog.apply_exact_matches()
        finally:
            QMessageBox.information = original
        assert emitted == [True]
        assert service.list_segments(project.id)[0].target == 'Otwórz bramę.'
        dialog.close()
    finally:
        service.close()
