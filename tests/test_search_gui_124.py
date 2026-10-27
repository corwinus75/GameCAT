"""Testy GUI opóźnionego filtrowania i wirtualnej listy segmentów (wymagają Qt)."""
from __future__ import annotations

import importlib.util
import os
import time

import pytest

pytestmark = pytest.mark.skipif(importlib.util.find_spec('PySide6') is None,
                                reason='PySide6 is unavailable')


def _pump(app, predicate, timeout=7.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.015)
    return False


def test_large_search_does_not_construct_one_qt_item_per_segment():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.segment_editor import SegmentEditor
    from gamecat.models.segment import Segment
    app = QApplication.instance() or QApplication([])
    editor = SegmentEditor()
    try:
        rows = [Segment(f'Line {i}', i, target='Przekład', id=i) for i in range(12000)]
        rows[9173].source = 'Distinct source'
        editor.set_segments(rows)
        assert _pump(app, lambda: not editor.search_busy and editor.segment_list.count() == 12000)
        assert editor.segment_list.model().rowCount() == 12000
        assert editor.segment_list.item(0).text().startswith('[N]')
        editor.search_edit.setText('Disti')
        editor.search_edit.setText('Distinct')
        assert editor.search_busy
        assert _pump(app, lambda: not editor.search_busy and editor.segment_list.count() == 1)
        assert editor.current_segment().id == 9173
        assert editor.segment_list.item(0).data(256) == 9173
    finally:
        editor.close()


def test_large_search_reveal_and_draft_remain_safe():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.segment_editor import SegmentEditor
    from gamecat.models.segment import Segment
    app = QApplication.instance() or QApplication([])
    editor = SegmentEditor()
    try:
        rows = [Segment(f'Text {i}', i, id=i) for i in range(4000)]
        editor.set_segments(rows)
        assert _pump(app, lambda: not editor.search_busy)
        editor.target_edit.setPlainText('Szkic bez zapisu')
        assert editor.has_unsaved_drafts
        editor.search_edit.setText('Text 3999')
        assert _pump(app, lambda: not editor.search_busy and editor.segment_list.count() == 1)
        assert editor.select_segment_by_id(0, reveal=True)
        assert _pump(app, lambda: not editor.search_busy and editor.current_segment().id == 0)
        assert editor.target_edit.toPlainText() == 'Szkic bez zapisu'
        assert rows[0].target == ''
    finally:
        editor.close()
