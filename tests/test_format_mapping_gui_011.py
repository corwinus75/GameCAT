import os
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')

from pathlib import Path
from PySide6.QtWidgets import QApplication
from gamecat.gui.format_mapping_dialog import FormatMappingDialog
from gamecat.localization.profiles import FormatProfile


def test_json_dialog_classic_and_custom_mapping():
    app = QApplication.instance() or QApplication([])
    dialog = FormatMappingDialog(Path('source.json'))
    assert dialog.selected_profile() is None
    dialog.legacy.setChecked(False)
    dialog.records_path.setText('data.lines')
    assert dialog.selected_profile().records_path == 'data.lines'
    dialog.close()


def test_format_mapping_dialog_preserves_saved_fields():
    app = QApplication.instance() or QApplication([])
    expected = FormatProfile('xlsx', sheet_name='Localization', key_field='string_id',
                             source_field='English', target_field='Polish')
    dialog = FormatMappingDialog(Path('localization.xlsx'), expected)
    assert dialog.selected_profile() == expected
    dialog.close()
