import importlib.util, os, pytest
HAS_QT = importlib.util.find_spec('PySide6') is not None

@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable in sandbox')
def test_glossary_panel_filters_populates_and_emits_target():
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.glossary_panel import GlossaryPanel
    from gamecat.models.glossary import GlossaryTerm
    app=QApplication.instance() or QApplication([])
    panel=GlossaryPanel(); panel.set_terms([
        GlossaryTerm('sword',['miecz','ostrze'],'Broń',False,id=1,project_id=1),
        GlossaryTerm('shield',['tarcza'],id=2,project_id=1),
    ])
    assert panel.table.rowCount()==2
    panel.search_edit.setText('ostrze'); assert panel.table.rowCount()==1
    panel.search_edit.clear(); panel.table.selectRow(0); panel._load_selected()
    assert panel.source_edit.text()=='sword'
    assert panel.description_edit.toPlainText()=='Broń'
    assert panel.variants.count()==2
    selected=[]; panel.target_insert_requested.connect(selected.append)
    panel.variants.setCurrentRow(0); panel._emit_selected_variant()
    assert selected==['miecz']
    panel.close()
