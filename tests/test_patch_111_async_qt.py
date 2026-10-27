"""Integration regression for GameCAT TM threshold callback (requires PySide6)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication, QMessageBox

from gamecat.gui.main_window import MainWindow
from gamecat.models.segment import Segment
from gamecat.services.project_service import ProjectService


def test_changing_tm_threshold_does_not_crash_async_callbacks(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    service = ProjectService(tmp_path / 'demo.sqlite')
    try:
        project = service.create_project('Demo', 'en', 'pl', 'txt')
        segment = service.segments.create(Segment('Hello', 1, project_id=project.id))
        window.current_project = project
        window.project_service = service
        window.segment_editor.set_segments([segment])
        monkeypatch.setattr(
            QMessageBox, 'warning',
            lambda *_args: pytest.fail('Threshold change must not display an error'),
        )
        window.tm_panel.threshold_spin.setValue(87)
        assert service.get_tm_threshold(project) == pytest.approx(0.87)
        assert window._tm_generation > 0
        assert window._qa_generation > 0
        assert window._tm_future is not None
    finally:
        window.current_project = None
        window.project_service = None
        window.close()
        service.close()
