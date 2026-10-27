"""Panel glosariusza tylko do odczytu, zawężony do terminów z bieżącego Source."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QListWidget, QPushButton, QMenu

from gamecat.gui.wrapping import enable_list_word_wrap
from gamecat.glossary.spans import term_spans
from gamecat.models.glossary import GlossaryTerm


class ContextGlossaryPanel(QGroupBox):
    """Lista terminów występujących w bieżącym segmencie z możliwością wstawienia wariantu."""
    open_full_requested = Signal()
    target_insert_requested = Signal(str)

    def __init__(self, parent=None):
        """Zbuduj listę terminów i przycisk otwarcia pełnego glosariusza."""
        super().__init__('Glosariusz segmentu', parent)
        self._all_terms: list[GlossaryTerm] = []
        self._visible: list[GlossaryTerm] = []
        self._source = ''
        self.list_widget = QListWidget(self)
        enable_list_word_wrap(self.list_widget)
        self.full_button = QPushButton('Otwórz cały słownik', self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.full_button)
        self.full_button.clicked.connect(lambda checked=False: self.open_full_requested.emit())
        self.list_widget.itemDoubleClicked.connect(self._offer_target)

    def set_terms(self, terms: list[GlossaryTerm]) -> None:
        """Ustaw pełny glosariusz projektu i odśwież listę kontekstową."""
        self._all_terms = list(terms)
        self._refresh()

    def set_source_context(self, source: str) -> None:
        """Ustaw tekst bieżącego Source i odśwież listę kontekstową."""
        self._source = source
        self._refresh()

    def _refresh(self) -> None:
        """Pokaż tylko terminy występujące w Source (bez powtórzeń)."""
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
        """Wstaw jedyny wariant terminu albo pokaż menu wyboru wariantu."""
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
