import importlib.util, os, pytest
HAS_QT = importlib.util.find_spec('PySide6') is not None

@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable in sandbox')
def test_segment_editor_edit_navigation_filter_and_confirm():
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.segment_editor import SegmentEditor
    from gamecat.models.segment import Segment, SegmentStatus
    app=QApplication.instance() or QApplication([])
    segs=[Segment('Hello',1), Segment('World',2,target='Świat',status='TRANSLATED')]
    editor=SegmentEditor(); editor.set_segments(segs)
    assert editor.current_segment().source=='Hello'
    editor.target_edit.setPlainText('Cześć'); editor.confirm_current()
    assert segs[0].target=='Cześć' and segs[0].status is SegmentStatus.TRANSLATED
    editor.next_segment(); assert editor.current_segment().source=='World'
    editor.previous_segment(); assert editor.current_segment().source=='Hello'
    editor.search_edit.setText('world'); assert editor.segment_list.count()==1
    editor.close()
