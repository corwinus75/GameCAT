"""Test dymny Qt panelu AI; uruchamiany, gdy dostępny jest PySide6 (także offscreen)."""
from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
qt = pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtWidgets import QApplication

from gamecat.gui.main_window import MainWindow
from gamecat.ai.core import AISettings


def test_ai_panel_widgets_and_persistent_config(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert window.ai_panel.single_button.text() == 'Tłumacz bieżący'
        assert window.ai_panel.batch_button.isEnabled()
        cfg = AISettings(model='gpt-5-mini', instructions='Bez komentarzy',
                         input_price_per_million=0.5, output_price_per_million=2)
        window.ai_panel.set_settings(cfg)
        assert window.ai_panel.get_settings().instructions == 'Bez komentarzy'
        assert window.ai_panel.api_key.echoMode() == qt.QLineEdit.EchoMode.Password
    finally:
        window.close()


def test_gui_ai_result_preview_requires_apply():
    from gamecat.ai.core import AIResult, AIUsage
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        result = AIResult('Otwórz bramę.', 'gpt-5-mini', AIUsage(10, 8), None)
        window.ai_panel.display_result(42, result)
        assert '42' in window.ai_panel.preview_caption.text()
        assert window.ai_panel.apply_button.isEnabled()
        assert window.ai_panel.preview.toPlainText() == 'Otwórz bramę.'
    finally:
        window.close()
