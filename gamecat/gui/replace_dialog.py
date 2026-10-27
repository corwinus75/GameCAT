"""Jawny podgląd i potwierdzenie masowej zamiany tekstu w Target."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from gamecat.models.segment import Segment
from gamecat.search.operations import TargetReplacement, preview_replacements


class BatchReplaceDialog(QDialog):
    """Przygotowuje zmiany bez modyfikowania segmentów; zapis wykonuje wywołujący po akceptacji."""

    def __init__(self, visible: list[Segment], selected: list[Segment], parent=None):
        """Zbuduj formularz wyszukiwania i zamiany oraz tabelę podglądu."""
        super().__init__(parent)
        self.setWindowTitle('Zamień w Target — podgląd zmian')
        self.resize(900, 580)
        self._visible = visible
        self._selected = selected
        self._preview: list[TargetReplacement] = []
        self.find_edit = QLineEdit()
        self.replace_edit = QLineEdit()
        self.regex_check = QCheckBox('Regex (grupy: \\1, \\g<name>)')
        self.case_check = QCheckBox('Rozróżniaj wielkość liter')
        self.reviewed_check = QCheckBox('Uwzględnij REVIEWED / APPROVED (ryzykowne)')
        self.selection_check = QCheckBox(f'Tylko zaznaczone ({len(selected)})')
        self.selection_check.setEnabled(len(selected) > 1)
        self.selection_check.setChecked(len(selected) > 1)
        form = QFormLayout()
        form.addRow('Znajdź w Target:', self.find_edit)
        form.addRow('Zamień na:', self.replace_edit)
        opts = QHBoxLayout()
        for widget in (self.regex_check, self.case_check, self.reviewed_check, self.selection_check):
            opts.addWidget(widget)
        self.summary = QLabel('Najpierw kliknij „Podgląd”. Source nie będzie zmieniany.')
        self.preview_button = QPushButton('Podgląd zmian')
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Source', 'Target — przed', 'Target — po'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Zastosuj zmiany')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(opts)
        layout.addWidget(self.preview_button)
        layout.addWidget(self.summary)
        layout.addWidget(self.table)
        layout.addWidget(self.buttons)
        self.preview_button.clicked.connect(self._refresh_preview)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        for edit in (self.find_edit, self.replace_edit):
            edit.textChanged.connect(self._invalidate)
        for check in (self.regex_check, self.case_check, self.reviewed_check, self.selection_check):
            check.toggled.connect(self._invalidate)

    def _invalidate(self, *_args) -> None:
        """Unieważnij podgląd po zmianie parametrów i zablokuj przycisk OK."""
        self._preview = []
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.summary.setText('Parametry zmienione — odśwież podgląd przed zastosowaniem.')
        self.table.setRowCount(0)

    def _refresh_preview(self, *_args) -> None:
        """Policz podgląd zamian dla widocznych lub zaznaczonych segmentów."""
        candidates = self._selected if self.selection_check.isChecked() else self._visible
        try:
            self._preview = preview_replacements(
                candidates, self.find_edit.text(), self.replace_edit.text(),
                regex=self.regex_check.isChecked(),
                case_sensitive=self.case_check.isChecked(),
                include_reviewed=self.reviewed_check.isChecked(),
            )
        except ValueError as exc:
            self._invalidate()
            QMessageBox.warning(self, 'GameCAT', str(exc))
            return
        self.table.setRowCount(min(100, len(self._preview)))
        for row, item in enumerate(self._preview[:100]):
            for column, value in enumerate((item.source, item.original, item.target)):
                self.table.setItem(row, column, QTableWidgetItem(value[:1000]))
        count = sum(item.occurrences for item in self._preview)
        self.summary.setText(
            f'Segmenty do zmiany: {len(self._preview)}; zastąpienia: {count}. '
            'Podgląd pokazuje maks. 100 rekordów.'
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self._preview))

    def replacements(self) -> dict[int, str]:
        """Zwróć zatwierdzone zmiany jako słownik ``ID segmentu -> nowy Target``."""
        return {item.segment_id: item.target for item in self._preview}

    @property
    def include_reviewed(self) -> bool:
        """Czy użytkownik zgodził się zmieniać segmenty zrecenzowane i zatwierdzone."""
        return self.reviewed_check.isChecked()
