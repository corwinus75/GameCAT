"""Contextual translation-memory suggestions and per-project fuzzy threshold."""
from PySide6.QtCore import QSignalBlocker, Signal
from pathlib import Path
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QListWidget, QSpinBox, QVBoxLayout

from gamecat.tm.matcher import TMMatch


class TMPanel(QGroupBox):
    target_selected = Signal(str)
    threshold_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__('Translation Memory', parent)
        self._matches: list[TMMatch] = []
        self.storage_label = QLabel('TM projektu')
        self.storage_label.setToolTip('Pamięć TM jest zapisana w bazie projektu.')
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._use_match)
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 100)
        self.threshold_spin.setSuffix('%')
        self.threshold_spin.setValue(45)
        self.threshold_spin.setToolTip('Minimalne podobieństwo sugestii TM dla bieżącego projektu')
        self.threshold_spin.valueChanged.connect(self._on_threshold_change)
        controls = QHBoxLayout()
        controls.addWidget(QLabel('Minimalne podobieństwo:'))
        controls.addWidget(self.threshold_spin)
        controls.addStretch()
        layout = QVBoxLayout(self)
        layout.addWidget(self.storage_label)
        layout.addLayout(controls)
        layout.addWidget(self.list_widget)

    def set_storage_path(self, path: Path | None) -> None:
        if path is None:
            self.storage_label.setText('TM projektu')
            self.storage_label.setToolTip('Pamięć TM jest zapisana w bazie projektu.')
        else:
            self.storage_label.setText(f'Zewnętrzna TM: {path.name}')
            self.storage_label.setToolTip(str(path))

    def set_threshold(self, threshold: float) -> None:
        with QSignalBlocker(self.threshold_spin):
            self.threshold_spin.setValue(round(100 * threshold))

    def _on_threshold_change(self, percent: int) -> None:
        self.threshold_changed.emit(percent / 100.0)

    def set_matches(self, matches: list[TMMatch]) -> None:
        self._matches = matches
        self.list_widget.clear()
        for match in matches:
            self.list_widget.addItem(
                f'{match.score:.0%}  {match.entry.source} → {match.entry.target}'
            )

    def _use_match(self, item) -> None:
        index = self.list_widget.row(item)
        if 0 <= index < len(self._matches):
            self.target_selected.emit(self._matches[index].entry.target)
