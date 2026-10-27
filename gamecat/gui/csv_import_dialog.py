from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout


class CsvImportDialog(QDialog):
    """Let the user map CSV columns to GameCAT key/source/target fields."""

    NO_TARGET = '(brak)'

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Mapowanie kolumn CSV')
        fields = self._read_fields(path)

        self.key_combo = QComboBox()
        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        self.comment_combo = QComboBox()
        self.key_combo.addItems(fields)
        self.source_combo.addItems(fields)
        self.target_combo.addItem(self.NO_TARGET)
        self.target_combo.addItems(fields)
        self.comment_combo.addItem(self.NO_TARGET)
        self.comment_combo.addItems(fields)

        self._select_best(self.key_combo, ('key', 'id', 'string_id', 'stringid'))
        self._select_best(self.source_combo, ('source', 'english', 'en', 'text'))
        self._select_best(self.target_combo, ('target', 'polish', 'pl', 'translation'))
        self._select_best(self.comment_combo, ('comment', 'context', 'speaker', 'notes'))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QFormLayout(self)
        layout.addRow('Klucz / ID:', self.key_combo)
        layout.addRow('Tekst źródłowy:', self.source_combo)
        layout.addRow('Tłumaczenie (opcjonalnie):', self.target_combo)
        layout.addRow('Kontekst / komentarz (opcjonalnie):', self.comment_combo)
        layout.addRow(buttons)

    @staticmethod
    def _read_fields(path: Path) -> list[str]:
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            reader = csv.reader(handle)
            try:
                fields = next(reader)
            except StopIteration as exc:
                raise ValueError('Plik CSV jest pusty.') from exc
        fields = [field.strip() for field in fields if field.strip()]
        if not fields:
            raise ValueError('Plik CSV nie zawiera nagłówków kolumn.')
        return fields

    @staticmethod
    def _select_best(combo: QComboBox, candidates: tuple[str, ...]) -> None:
        lookup = {combo.itemText(i).casefold(): i for i in range(combo.count())}
        for candidate in candidates:
            if candidate.casefold() in lookup:
                combo.setCurrentIndex(lookup[candidate.casefold()])
                return

    def columns(self) -> tuple[str, str, str | None]:
        target = self.target_combo.currentText()
        return (
            self.key_combo.currentText(),
            self.source_combo.currentText(),
            None if target == self.NO_TARGET else target,
        )

    def comment_column(self) -> str | None:
        value = self.comment_combo.currentText()
        return None if value == self.NO_TARGET else value
