"""Testy regresyjne GUI: długie teksty muszą się zawijać bez obcinania."""
from __future__ import annotations

import importlib.util
import os

import pytest

HAS_QT = importlib.util.find_spec('PySide6') is not None
pytestmark = pytest.mark.skipif(not HAS_QT, reason='Requires PySide6')


@pytest.fixture
def qt_app():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_every_docked_list_wraps_without_eliding(qt_app):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListView
    from gamecat.gui.ai_panel import AIPanel
    from gamecat.gui.context_glossary_panel import ContextGlossaryPanel
    from gamecat.gui.history_panel import HistoryPanel
    from gamecat.gui.qa_panel import QAPanel
    from gamecat.gui.tm_panel import TMPanel
    from gamecat.gui.wrapping import WrappingItemDelegate

    panels = [HistoryPanel(), TMPanel(), QAPanel(), ContextGlossaryPanel(), AIPanel()]
    try:
        lists = [
            panels[0].list_widget,
            panels[1].list_widget,
            panels[2].current_list,
            panels[2].project_list,
            panels[3].list_widget,
            panels[4].suggestions,
        ]
        for widget in lists:
            assert widget.wordWrap()
            assert widget.textElideMode() == Qt.TextElideMode.ElideNone
            assert not widget.uniformItemSizes()
            assert widget.resizeMode() == QListView.ResizeMode.Adjust
            assert isinstance(widget.itemDelegate(), WrappingItemDelegate)
    finally:
        for panel in panels:
            panel.close()


def test_row_height_grows_for_narrow_panel(qt_app):
    from PySide6.QtWidgets import QListWidget, QStyleOptionViewItem
    from gamecat.gui.wrapping import enable_list_word_wrap

    view = QListWidget()
    enable_list_word_wrap(view)
    view.addItem('Very long string with translation context and placeholders. ' * 12)
    try:
        view.resize(540, 300)
        view.show()
        qt_app.processEvents()
        index = view.model().index(0, 0)
        option = QStyleOptionViewItem()
        wide = view.itemDelegate().sizeHint(option, index).height()

        view.resize(160, 300)
        qt_app.processEvents()
        narrow = view.itemDelegate().sizeHint(option, index).height()
        assert narrow > wide
    finally:
        view.close()


def test_full_glossary_wraps_columns_and_variants(qt_app):
    from PySide6.QtWidgets import QHeaderView, QPlainTextEdit
    from gamecat.gui.glossary_panel import GlossaryPanel
    from gamecat.gui.wrapping import WrappingItemDelegate

    panel = GlossaryPanel()
    try:
        assert panel.table.wordWrap()
        from gamecat.models.glossary import GlossaryTerm
        panel.set_terms([GlossaryTerm('ancient sword', ['miecz', 'długi miecz'])])
        assert panel.table.verticalHeader().sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents
        assert isinstance(panel.variants.itemDelegate(), WrappingItemDelegate)
        assert panel.description_edit.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    finally:
        panel.close()


def test_ai_displays_full_source_and_wraps_text_fields(qt_app):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QPlainTextEdit
    from gamecat.gui.ai_panel import AIPanel

    panel = AIPanel()
    try:
        very_long_source = 'Long line from a game dialogue: ' + ('Really important content. ' * 12)
        report = SimpleNamespace(
            results=[SimpleNamespace(segment_id=23, original_source=very_long_source,
                                     result=SimpleNamespace(qa_warnings=[]))],
            cancelled=False, budget_exhausted=False, skipped_existing=0, errors=[],
            input_tokens=0, output_tokens=0, spent_usd=0.0,
        )
        panel.show_batch(report)
        assert very_long_source in panel.suggestions.item(0).text()
        assert panel.instructions.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
        assert panel.preview.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    finally:
        panel.close()
