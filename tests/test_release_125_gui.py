"""UI mapping checks: run with PySide6 when available."""
import os
from pathlib import Path

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication

from gamecat.gui.csv_import_dialog import CsvImportDialog
from gamecat.gui.csv_translation_import_dialog import CsvTranslationImportDialog


def test_source_dialog_recognizes_id_loca_columns(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / 'fg2.csv'
    path.write_text('Id;Loca\nA;"Hello, traveler"\n', encoding='utf-8')
    dialog = CsvImportDialog(path)
    try:
        assert dialog.columns() == ('Id', 'Loca', None)
    finally:
        dialog.close()


def test_translation_dialog_recognizes_semicolon_columns(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / 'target.csv'
    path.write_text('id;target\nA;Witaj\n', encoding='utf-8')
    dialog = CsvTranslationImportDialog(path)
    try:
        assert dialog.columns() == ('id', 'target')
    finally:
        dialog.close()
