import importlib.util, os, pytest
HAS_QT = importlib.util.find_spec('PySide6') is not None

@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable in sandbox')
def test_segment_editor_edit_navigation_filter_and_confirm():
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.segment_editor import SegmentEditor
    from gamecat.models.segment import Segment, SegmentStatus
    app=QApplication.instance() or QApplication([])
    segs=[Segment('Hello',1,id=1), Segment('World',2,target='Świat',status='TRANSLATED',id=2)]
    editor=SegmentEditor(); editor.set_segments(segs)
    assert editor.current_segment().source=='Hello'
    def approve(segment,status,target,comment):
        segment.target=target; segment.status=status; segment.comment=comment
        editor.accept_saved_segment(segment)
    editor.action_requested.connect(approve)
    editor.target_edit.setPlainText('Cześć')
    assert segs[0].target == ''  # RAM-only draft
    editor.confirm_current()
    assert segs[0].target=='Cześć' and segs[0].status is SegmentStatus.TRANSLATED
    editor.next_segment(); assert editor.current_segment().source=='World'
    editor.previous_segment(); assert editor.current_segment().source=='Hello'
    editor.search_edit.setText('world'); assert editor.segment_list.count()==1
    editor.close()

@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable in sandbox')
def test_segment_editor_status_workflow_and_bulk_selection():
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtCore import QItemSelectionModel
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.segment_editor import SegmentEditor
    from gamecat.models.segment import Segment, SegmentStatus

    app = QApplication.instance() or QApplication([])
    segs = [
        Segment('One', 1, target='Jeden', status=SegmentStatus.REVIEWED, id=1),
        Segment('Two', 2, target='Dwa', status=SegmentStatus.TRANSLATED, id=2),
    ]
    editor = SegmentEditor(); editor.set_segments(segs)
    assert editor.segment_list.item(0).text().startswith('[R]')

    def persist(segment,status,target,comment):
        segment.target=target; segment.status=status; segment.comment=comment
        editor.accept_saved_segment(segment)
    editor.action_requested.connect(persist)
    editor.review_button.click()
    assert segs[0].status is SegmentStatus.REVIEWED

    editor.segment_list.setCurrentRow(0)
    editor.segment_list.item(0).setSelected(True)
    editor.segment_list.item(1).setSelected(True)
    assert editor.set_selected_status(SegmentStatus.APPROVED) == 2
    assert [s.status for s in segs] == [SegmentStatus.APPROVED, SegmentStatus.APPROVED]
    assert editor.project_progress().approved == 2
    editor.close()
