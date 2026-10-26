"""Declarative mapping editor for GameCAT localization formats."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QCheckBox,
)

from gamecat.localization.profiles import FormatProfile


class FormatMappingDialog(QDialog):
    """Mapping fields; JSON legacy mode preserves pre-0.11 import behavior."""

    def __init__(self, path: Path, existing: FormatProfile | None = None, parent=None):
        super().__init__(parent)
        fmt = path.suffix.lower().lstrip('.')
        self.format = fmt
        self.setWindowTitle(f'Mapowanie lokalizacji {fmt.upper()}')
        default = existing or FormatProfile(fmt)
        if fmt == 'xml' and existing is None:
            default = FormatProfile('xml', records_path='.//entry', key_field='@id')
        self.legacy = QCheckBox('Klasyczny format JSON (bez mapowania)')
        self.legacy.setChecked(fmt == 'json' and existing is None)
        self.records_path = QLineEdit(default.records_path)
        self.key_field = QLineEdit(default.key_field)
        self.source_field = QLineEdit(default.source_field)
        self.target_field = QLineEdit(default.target_field)
        self.sheet_name = QLineEdit(default.sheet_name)
        self._fields = (self.records_path, self.key_field, self.source_field,
                        self.target_field, self.sheet_name)
        layout = QFormLayout(self)
        if fmt == 'json':
            layout.addRow(self.legacy)
            self.legacy.toggled.connect(self._toggle)
        if fmt in {'json', 'xml'}:
            layout.addRow('Ścieżka kolekcji (XML: XPath):', self.records_path)
        layout.addRow('Klucz / ID (opcjonalnie; XML: @atrybut):', self.key_field)
        layout.addRow('Pole Source:', self.source_field)
        layout.addRow('Pole Target:', self.target_field)
        if fmt == 'xlsx':
            layout.addRow('Arkusz (puste = pierwszy):', self.sheet_name)
        help_text = (
            'JSON: ścieżki rozdzielone kropkami (np. data.lines, text.en).\n'
            'XML: XPath względny (np. .//entry), pola jako tag lub @id.\n'
            'TSV/XLSX: wpisz nazwy kolumn z wiersza nagłówków.\n'
            'Mapowanie jest zapisywane osobno dla każdego projektu i formatu.'
        )
        label = QLabel(help_text)
        label.setWordWrap(True)
        layout.addRow(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self._toggle()

    def _toggle(self, *_):
        enabled = not (self.format == 'json' and self.legacy.isChecked())
        for field in self._fields:
            field.setEnabled(enabled)

    def selected_profile(self) -> FormatProfile | None:
        if self.format == 'json' and self.legacy.isChecked():
            return None
        return FormatProfile(
            self.format,
            records_path=self.records_path.text().strip(),
            key_field=self.key_field.text().strip(),
            source_field=self.source_field.text().strip(),
            target_field=self.target_field.text().strip(),
            sheet_name=self.sheet_name.text().strip(),
        )
