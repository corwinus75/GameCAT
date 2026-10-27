"""Testy dymne GUI wyszukiwania (wymagają PySide6)."""
from __future__ import annotations

import importlib.util
import os
import pytest

pytestmark = pytest.mark.skipif(importlib.util.find_spec('PySide6') is None,
                                reason='PySide6 is not installed in this environment')


def test_editor_filters_and_invalid_regex():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.segment_editor import SegmentEditor
    from gamecat.models.segment import Segment

    app = QApplication.instance() or QApplication([])
    editor = SegmentEditor()
    editor.set_segments([
        Segment('Dragon', 1, target='Smok', id=1),
        Segment('Hello', 2, target='Cześć', id=2),
    ])
    editor.search_edit.setText('Dragon')
    assert editor.segment_list.count() == 1
    editor.regex_check.setChecked(True)
    editor.search_edit.setText('(')
    assert not editor.search_valid
    assert editor.segment_list.count() == 0
    editor.search_edit.setText('Hello')
    assert editor.search_valid
    assert editor.segment_list.count() == 1
    editor.close()


def test_replace_dialog_preview_invalidate_and_protection():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.replace_dialog import BatchReplaceDialog
    from gamecat.models.segment import Segment

    app = QApplication.instance() or QApplication([])
    rows = [Segment('hello', 1, target='cat', id=1),
            Segment('bye', 2, target='cat', status='APPROVED', id=2)]
    dlg = BatchReplaceDialog(rows, [])
    dlg.find_edit.setText('cat')
    dlg.replace_edit.setText('dog')
    dlg._refresh_preview()
    assert dlg.replacements() == {1: 'dog'}
    dlg.reviewed_check.setChecked(True)
    assert not dlg.replacements()
    dlg._refresh_preview()
    assert dlg.replacements() == {1: 'dog', 2: 'dog'}
    dlg.close()
