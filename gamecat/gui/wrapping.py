"""Reusable wrapping configuration for text-heavy Qt list views.

Qt's QListWidget.setWordWrap(True) affects painting, but alone it does not
reliably enlarge the height of a row. The size-hint delegate ensures long
suggestions, QA messages and history entries remain readable in narrow docks.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QListView, QListWidget, QStyledItemDelegate, QStyleOptionViewItem


class WrappingItemDelegate(QStyledItemDelegate):
    """Size list rows to their *wrapped* text at the current viewport width."""

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
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
    """Enable full-text wrapping and reflow when a dock/panel is resized."""
    widget.setWordWrap(True)
    widget.setTextElideMode(Qt.TextElideMode.ElideNone)
    widget.setUniformItemSizes(False)
    widget.setResizeMode(QListView.ResizeMode.Adjust)
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    widget.setItemDelegate(WrappingItemDelegate(widget))
