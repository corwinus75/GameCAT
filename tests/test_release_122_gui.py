"""Interaction regressions exercised with offscreen Qt when PySide6 is available."""
import importlib.util
import os
import pytest

HAS_QT = importlib.util.find_spec('PySide6') is not None


@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable')
def test_editor_keeps_target_in_ram_until_explicit_action():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.segment_editor import SegmentEditor
    from gamecat.models.segment import Segment, SegmentStatus
    app = QApplication.instance() or QApplication([])
    s1=Segment('Open gate', 1, id=1, target='Otwórz bramę', status='APPROVED')
    s2=Segment('Close gate', 2, id=2)
    editor=SegmentEditor(); editor.set_segments([s1,s2])
    try:
        editor.target_edit.setPlainText('Otwórz furtkę')
        assert s1.target == 'Otwórz bramę' and s1.status is SegmentStatus.APPROVED
        assert editor.has_unsaved_drafts
        editor.next_segment()
        assert s2.target == ''
        editor.previous_segment()
        assert editor.target_edit.toPlainText() == 'Otwórz furtkę'
        requested = []
        editor.action_requested.connect(lambda *args: requested.append(args))
        editor.save_translation_button.click()
        assert requested[0][1:] == (SegmentStatus.TRANSLATED, 'Otwórz furtkę', '')
        assert s1.target == 'Otwórz bramę'  # The service—not the widget—persists.
    finally:
        editor.close()


@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable')
def test_glossary_context_only_and_source_inserts_variant():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.context_glossary_panel import ContextGlossaryPanel
    from gamecat.gui.segment_editor import SegmentEditor
    from gamecat.models.glossary import GlossaryTerm
    from gamecat.models.segment import Segment
    app = QApplication.instance() or QApplication([])
    terms=[GlossaryTerm('sword',['miecz']),GlossaryTerm('shield',['tarcza'])]
    panel=ContextGlossaryPanel()
    panel.set_terms(terms); panel.set_source_context('This sword is sharp')
    assert panel.list_widget.count() == 1
    assert 'sword' in panel.list_widget.item(0).text()
    editor=SegmentEditor(); editor.set_segments([Segment('This sword is sharp',1,id=12)])
    try:
        editor.source_edit.set_glossary_terms(terms)
        editor.source_edit.target_insert_requested.connect(editor.insert_target_text)
        assert len(editor.source_edit._clickable)==1
        term=editor.source_edit._clickable[0][2]
        editor.source_edit._choose_translation(term, editor.source_edit.rect().center())
        assert editor.target_edit.toPlainText() == 'miecz'
        assert editor.current_segment().target == ''  # Draft only.
    finally:
        panel.close(); editor.close()


@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable')
def test_main_window_tabs_history_and_separate_full_glossary():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow()
    try:
        qa=window._dock_widgets['QA']
        assert len(window.tabifiedDockWidgets(qa))==4
        assert window.glossary_panel.parent() is window.glossary_dialog
        assert window.context_glossary_panel is window._dock_widgets['Glosariusz'].widget()
        assert window._dock_widgets['Historia'].widget() is window.history_panel
    finally:
        window.close()
