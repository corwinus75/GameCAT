import importlib.util
import os
import pytest

HAS_QT = importlib.util.find_spec('PySide6') is not None

@pytest.mark.skipif(not HAS_QT, reason='PySide6 unavailable in sandbox')
def test_main_window_smoke():
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.current_project is None
    with pytest.raises(RuntimeError, match='No project is open'):
        window.save_project()
    window.close()
