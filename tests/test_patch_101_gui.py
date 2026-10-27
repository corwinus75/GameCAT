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


def test_manual_change_requires_explicit_save():
    app = QApplication.instance() or QApplication([])
    editor = SegmentEditor()
    segment = Segment('Hello', 1, target='Cześć', status=SegmentStatus.APPROVED, id=1)
    editor.set_segments([segment])
    try:
        changes=[]
        editor.action_requested.connect(lambda *args: changes.append(args))
        editor.target_edit.setPlainText('Witaj')
        assert segment.status is SegmentStatus.APPROVED
        assert segment.target == 'Cześć'
        assert editor.project_progress().approved == 1
        assert editor.has_unsaved_drafts
        editor.save_translation_button.click()
        assert changes[-1][1] is SegmentStatus.TRANSLATED
        assert changes[-1][2] == 'Witaj'
        # Only ProjectService may acknowledge a successful database commit.
        segment.target = 'Witaj'; segment.status = SegmentStatus.TRANSLATED
        editor.accept_saved_segment(segment)
        assert not editor.has_unsaved_drafts
        editor.target_edit.clear()
        assert segment.status is SegmentStatus.TRANSLATED
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
        from PySide6.QtTest import QTest
        for _ in range(60):
            if seen:
                break
            QTest.qWait(25)
        assert seen and seen[-1].get('threshold') is None
        win._safe_use_project_tm_database()
        assert win.ai_panel.get_settings().instructions == 'keep names'
        assert service.get_ai_settings(project).instructions == 'keep names'
    finally:
        win.current_project = None
        win.project_service = None
        win.close()
        service.close()
