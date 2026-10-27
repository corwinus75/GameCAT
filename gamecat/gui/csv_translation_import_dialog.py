"""Okno mapowania kolumn CSV przy imporcie samych tłumaczeń."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout

from gamecat.gui.csv_import_dialog import CsvImportDialog


class CsvTranslationImportDialog(QDialog):
    """Pozwala wskazać opcjonalną kolumnę klucza i wymaganą kolumnę Target."""

    NO_KEY = '(kolejność wierszy)'

    def __init__(self, path: Path, parent=None):
        """Wczytaj nagłówki pliku i zaproponuj kolumny klucza oraz Target."""
        super().__init__(parent)
        self.setWindowTitle('Import tłumaczenia z CSV')
        fields = CsvImportDialog._read_fields(path)

        self.key_combo = QComboBox()
        self.target_combo = QComboBox()
        self.key_combo.addItem(self.NO_KEY)
        self.key_combo.addItems(fields)
        self.target_combo.addItems(fields)

        CsvImportDialog._select_best(self.key_combo, ('key', 'id', 'string_id', 'stringid'))
        CsvImportDialog._select_best(self.target_combo, ('target', 'polish', 'pl', 'translation'))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QFormLayout(self)
        layout.addRow('Klucz / ID:', self.key_combo)
        layout.addRow('Tłumaczenie:', self.target_combo)
        layout.addRow(buttons)

    def columns(self) -> tuple[str | None, str]:
        """Zwróć wybrane kolumny (klucz lub ``None``, Target)."""
        key = self.key_combo.currentText()
        return (None if key == self.NO_KEY else key, self.target_combo.currentText())
