"""Konfiguracja zawijania tekstu dla list Qt z długimi wpisami.

Samo ``QListWidget.setWordWrap(True)`` nie przelicza wysokości wierszy po
zmianie szerokości panelu; delegat poniżej liczy rozmiar dla aktualnej
szerokości widoku.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QListView, QListWidget, QStyledItemDelegate, QStyleOptionViewItem


class WrappingItemDelegate(QStyledItemDelegate):
    """Delegat ustalający wysokość wiersza na podstawie *zawiniętego* tekstu."""

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        """Zwróć rozmiar wiersza dla tekstu zawiniętego do bieżącej szerokości widoku."""
        configured = QStyleOptionViewItem(option)
        self.initStyleOption(configured, index)
        result = super().sizeHint(option, index)
        view = self.parent()
        width = view.viewport().width() if isinstance(view, QListView) else configured.rect.width()
        # Preserve room for the selection border, item padding and any icon.
        text_width = max(32, width - 20)
        if configured.decorationSize.width() and index.data(Qt.ItemDataRole.DecorationRole) is not None:
            text_width = max(32, text_width - configured.decorationSize.width() - 4)
        metrics = QFontMetrics(configured.font)
        bounds = metrics.boundingRect(
            QRect(0, 0, text_width, 1_000_000),
            Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextExpandTabs,
            configured.text,
        )
        return QSize(min(result.width(), max(32, width)), max(result.height(), bounds.height() + 10))


def enable_list_word_wrap(widget: QListWidget) -> None:
    """Włącz pełne zawijanie tekstu i przeliczanie wierszy po zmianie rozmiaru panelu."""
    widget.setWordWrap(True)
    widget.setTextElideMode(Qt.TextElideMode.ElideNone)
    widget.setUniformItemSizes(False)
    widget.setResizeMode(QListView.ResizeMode.Adjust)
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    widget.setItemDelegate(WrappingItemDelegate(widget))
