"""Read-only Source with underlined clickable glossary matches."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QTextEdit

from gamecat.glossary.spans import term_spans
from gamecat.models.glossary import GlossaryTerm


class GlossarySourceEdit(QPlainTextEdit):
    target_insert_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self._terms: list[GlossaryTerm] = []
        self._clickable: list[tuple[int, int, GlossaryTerm]] = []
        self.textChanged.connect(self._refresh_highlights)

    def set_glossary_terms(self, terms: list[GlossaryTerm]) -> None:
        self._terms = list(terms)
        self._refresh_highlights()

    @staticmethod
    def _qt_pos(text: str, index: int) -> int:
        # Qt QTextCursor coordinates are UTF-16 code units, not Python code points.
        return len(text[:index].encode('utf-16-le')) // 2

    def _refresh_highlights(self) -> None:
        text = self.toPlainText()
        selections = []
        self._clickable = []
        for start, end, term in term_spans(text, self._terms):
            start_pos, end_pos = self._qt_pos(text, start), self._qt_pos(text, end)
            self._clickable.append((start_pos, end_pos, term))
            cursor = QTextCursor(self.document())
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format.setFontUnderline(True)
            selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, False)
            selections.append(selection)
        self.setExtraSelections(selections)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        cursor = self.cursorForPosition(event.position().toPoint())
        position = cursor.position()
        for start, end, term in self._clickable:
            if start <= position < end:
                self._choose_translation(term, event.position().toPoint())
                return

    def _choose_translation(self, term: GlossaryTerm, position) -> None:
        if len(term.targets) == 1:
            self.target_insert_requested.emit(term.targets[0])
            return
        menu = QMenu(self)
        for target in term.targets:
            menu.addAction(target, lambda checked=False, target=target: self.target_insert_requested.emit(target))
        menu.exec(self.mapToGlobal(position))
