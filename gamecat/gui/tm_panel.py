"""Panel kontekstowych sugestii pamięci tłumaczeniowej z progiem dopasowania projektu."""
from PySide6.QtCore import QSignalBlocker, Signal
from pathlib import Path
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSpinBox, QVBoxLayout

from gamecat.gui.wrapping import enable_list_word_wrap
from gamecat.tm.matcher import TMMatch
from gamecat.tm.presentation import display_tm_match


class TMPanel(QGroupBox):
    """Sugestie TM dla bieżącego segmentu; dwuklik wstawia tłumaczenie do Target."""
    target_selected = Signal(str)
    threshold_changed = Signal(float)

    def __init__(self, parent=None):
        """Zbuduj etykietę magazynu TM, listę sugestii i pole progu."""
        super().__init__('Translation Memory', parent)
        self._matches: list[TMMatch] = []
        self.storage_label = QLabel('TM projektu')
        self.storage_label.setWordWrap(True)
        self.storage_label.setToolTip('Pamięć TM jest zapisana w bazie projektu.')
        self.list_widget = QListWidget()
        enable_list_word_wrap(self.list_widget)
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
        """Pokaż, czy aktywna jest TM projektu, czy zewnętrzna baza."""
        if path is None:
            self.storage_label.setText('TM projektu')
            self.storage_label.setToolTip('Pamięć TM jest zapisana w bazie projektu.')
        else:
            self.storage_label.setText(f'Zewnętrzna TM: {path.name}')
            self.storage_label.setToolTip(str(path))

    def set_threshold(self, threshold: float) -> None:
        """Ustaw próg w polu bez emitowania sygnału zmiany."""
        with QSignalBlocker(self.threshold_spin):
            self.threshold_spin.setValue(round(100 * threshold))

    def _on_threshold_change(self, percent: int) -> None:
        """Przelicz próg z procentów na ułamek i zgłoś zmianę."""
        self.threshold_changed.emit(percent / 100.0)

    def set_matches(self, matches: list[TMMatch]) -> None:
        """Wyświetl sugestie TM z etykietami i podpowiedziami."""
        self._matches = matches
        self.list_widget.clear()
        for match in matches:
            label, tooltip = display_tm_match(match)
            item = QListWidgetItem(label)
            item.setToolTip(tooltip)
            if match.is_current_segment:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.list_widget.addItem(item)

    def _use_match(self, item) -> None:
        """Zgłoś wstawienie tłumaczenia z wybranej sugestii."""
        index = self.list_widget.row(item)
        if 0 <= index < len(self._matches):
            self.target_selected.emit(self._matches[index].entry.target)
