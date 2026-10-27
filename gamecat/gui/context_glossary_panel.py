"""Read-only project glossary filtered to the current source segment."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QListWidget, QPushButton, QMenu

from gamecat.glossary.spans import term_spans
from gamecat.models.glossary import GlossaryTerm


class ContextGlossaryPanel(QGroupBox):
    open_full_requested = Signal()
    target_insert_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__('Glosariusz segmentu', parent)
        self._all_terms: list[GlossaryTerm] = []
        self._visible: list[GlossaryTerm] = []
        self._source = ''
        self.list_widget = QListWidget(self)
        self.full_button = QPushButton('Otwórz cały słownik', self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.full_button)
        self.full_button.clicked.connect(lambda checked=False: self.open_full_requested.emit())
        self.list_widget.itemDoubleClicked.connect(self._offer_target)

    def set_terms(self, terms: list[GlossaryTerm]) -> None:
        self._all_terms = list(terms)
        self._refresh()

    def set_source_context(self, source: str) -> None:
        self._source = source
        self._refresh()

    def _refresh(self) -> None:
        seen: set[int] = set()
        self._visible = []
        for _, _, term in term_spans(self._source, self._all_terms):
            marker = id(term)
            if marker not in seen:
                self._visible.append(term)
                seen.add(marker)
        self.list_widget.clear()
        for term in self._visible:
            self.list_widget.addItem(f'{term.source_term} → {" | ".join(term.targets)}')

    def _offer_target(self, item) -> None:
        index = self.list_widget.row(item)
        if not 0 <= index < len(self._visible):
            return
        targets = self._visible[index].targets
        if len(targets) == 1:
            self.target_insert_requested.emit(targets[0])
        elif targets:
            menu = QMenu(self)
            for target in targets:
                menu.addAction(target, lambda checked=False, target=target: self.target_insert_requested.emit(target))
            menu.exec(self.list_widget.mapToGlobal(self.list_widget.visualItemRect(item).bottomLeft()))
