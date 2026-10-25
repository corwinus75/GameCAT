import importlib.util, os, pytest
HAS_QT = importlib.util.find_spec('PySide6') is not None

@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable in sandbox')
def test_panels_render_content():
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.qa_panel import QAPanel
    from gamecat.gui.glossary_panel import GlossaryPanel
    from gamecat.gui.tm_panel import TMPanel
    from gamecat.models.glossary import GlossaryEntry
    from gamecat.models.translation_memory import TranslationMemoryEntry
    from gamecat.qa.validator import validate_segment
    from gamecat.tm.matcher import TMMatch
    app=QApplication.instance() or QApplication([])
    qa=QAPanel(); qa.set_issues(validate_segment('Hello {x}','Hej'))
    assert qa.list_widget.count() >= 1
    gl=GlossaryPanel(); gl.set_entries([GlossaryEntry('quest','zadanie')]); assert gl.table.rowCount()==1
    tm=TMPanel(); tm.set_matches([TMMatch(TranslationMemoryEntry('Hi','Cześć','en','pl'),0.9)]); assert tm.list_widget.count()==1
    qa.close(); gl.close(); tm.close()
