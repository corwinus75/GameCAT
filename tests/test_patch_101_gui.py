"""Real PySide6 integration regressions (offscreen when available)."""
from __future__ import annotations

import os
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtWidgets import QApplication
from gamecat.gui.segment_editor import SegmentEditor
from gamecat.gui.main_window import MainWindow
from gamecat.models.segment import Segment, SegmentStatus
from gamecat.ai.core import AISettings
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.services.project_service import ProjectService


def test_manual_change_updates_status_and_progress_without_spurious_changes():
    app = QApplication.instance() or QApplication([])
    editor = SegmentEditor()
    segment = Segment('Hello', 1, target='Cześć', status=SegmentStatus.APPROVED, id=1)
    editor.set_segments([segment])
    try:
        changed = []
        editor.segment_modified.connect(changed.append)
        editor.target_edit.setPlainText('Cześć')
        assert segment.status is SegmentStatus.APPROVED and changed == []
        editor.target_edit.setPlainText('Witaj')
        assert segment.status is SegmentStatus.TRANSLATED
        assert editor.status_combo.currentText() == SegmentStatus.TRANSLATED.value
        assert editor.project_progress().approved == 0
        assert changed == [segment]
        editor.target_edit.clear()
        assert segment.status is SegmentStatus.NEW
    finally:
        editor.close()


def test_tm_threshold_and_switching_backend_does_not_reset_ai(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    service = ProjectService(tmp_path/'p.sqlite')
    project = service.create_project('P','en','pl','txt')
    settings = AISettings(model='gpt-5-mini', instructions='keep names', input_price_per_million=2)
    service.set_ai_settings(project, settings)
    win.project_service = service
    win.current_project = project
    win.ai_panel.set_settings(service.get_ai_settings(project))
    segment = service.segments.create(Segment('Hello', 1, project_id=project.id))
    service.translation_memory.create(TranslationMemoryEntry('Hello', 'Cześć', 'en','pl'))
    try:
        win.tm_panel.set_threshold(.90)
        service.set_tm_threshold(project, .90)
        seen = []
        original = service.find_tm_matches
        def capture(*args, **kwargs):
            seen.append(kwargs)
            return original(*args, **kwargs)
        monkeypatch.setattr(service, 'find_tm_matches', capture)
        win._update_current_tm(segment)
        assert seen and seen[-1].get('threshold') is None
        win._safe_use_project_tm_database()
        assert win.ai_panel.get_settings().instructions == 'keep names'
        assert service.get_ai_settings(project).instructions == 'keep names'
    finally:
        win.current_project = None
        win.project_service = None
        win.close()
        service.close()
