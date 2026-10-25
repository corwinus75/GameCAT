from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QListWidget, QVBoxLayout
from gamecat.tm.matcher import TMMatch


class TMPanel(QGroupBox):
    target_selected = Signal(str)
    def __init__(self, parent=None):
        super().__init__('Translation Memory', parent)
        self.list_widget=QListWidget(); QVBoxLayout(self).addWidget(self.list_widget)
        self._matches: list[TMMatch]=[]
        self.list_widget.itemDoubleClicked.connect(self._use_match)
    def set_matches(self, matches: list[TMMatch]) -> None:
        self._matches=matches; self.list_widget.clear()
        for match in matches: self.list_widget.addItem(f'{match.score:.0%}  {match.entry.source} → {match.entry.target}')
    def _use_match(self, item) -> None:
        row=self.list_widget.row(item)
        if 0 <= row < len(self._matches): self.target_selected.emit(self._matches[row].entry.target)
