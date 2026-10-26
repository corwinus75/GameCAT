"""Qt regression tests; skipped when optional PySide6 is not installed."""
from __future__ import annotations

import importlib.util
import os

import pytest

HAS_QT = importlib.util.find_spec('PySide6') is not None


@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable in build environment')
def test_tm_panel_threshold_and_suggestion():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.tm_panel import TMPanel
    from gamecat.models.translation_memory import TranslationMemoryEntry
    from gamecat.tm.matcher import TMMatch

    app = QApplication.instance() or QApplication([])
    panel = TMPanel()
    try:
        values = []
        panel.threshold_changed.connect(values.append)
        panel.set_threshold(.45)
        assert values == []
        panel.threshold_spin.setValue(85)
        assert values == [.85]
        panel.set_matches([TMMatch(TranslationMemoryEntry('Take sword', 'Weź miecz', 'en', 'pl'), 1.0)])
        assert panel.list_widget.count() == 1
        selected = []
        panel.target_selected.connect(selected.append)
        panel._use_match(panel.list_widget.item(0))
        assert selected == ['Weź miecz']
    finally:
        panel.close()


@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable in build environment')
def test_tm_analysis_dialog_fuzzy_requires_confirmation(tmp_path, monkeypatch):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication, QMessageBox
    from gamecat.gui.tm_analysis_dialog import TMAnalysisDialog
    from gamecat.models.translation_memory import TranslationMemoryEntry
    from gamecat.services.project_service import ProjectService

    app = QApplication.instance() or QApplication([])
    service = ProjectService(tmp_path / 'p.sqlite')
    project = service.create_project('P', 'en', 'pl', 'txt')
    try:
        path = tmp_path / 's.txt'
        path.write_text('Open the gate now.\n', encoding='utf-8')
        service.import_file_async(project, path).result(timeout=5)
        service.translation_memory.create(TranslationMemoryEntry('Open the gate.', 'Otwórz bramę.', 'en', 'pl'))
        report = service.analyze_project_tm(project, mode='sequential')
        dialog = TMAnalysisDialog(service, project)
        try:
            dialog.show_report(report)
            dialog.pretranslate_spin.setValue(50)
            assert dialog.apply_button.isEnabled()
            monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.No)
            dialog.apply_exact_matches()
            assert service.list_segments(project.id)[0].target == ''
            monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
            monkeypatch.setattr(QMessageBox, 'information', lambda *a, **k: None)
            dialog.apply_exact_matches()
            assert service.list_segments(project.id)[0].target == 'Otwórz bramę.'
        finally:
            dialog.close()
    finally:
        service.close()
