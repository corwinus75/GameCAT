"""Trwała historia zatwierdzeń bieżącego segmentu (tylko do odczytu)."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QGroupBox, QListWidget, QListWidgetItem, QVBoxLayout

from gamecat.gui.wrapping import enable_list_word_wrap


class HistoryPanel(QGroupBox):
    """Lista migawek z historii segmentu: status, tekst i data."""
    def __init__(self, parent=None):
        """Utwórz listę z zawijaniem długich wpisów."""
        super().__init__('Historia', parent)
        self.list_widget = QListWidget(self)
        enable_list_word_wrap(self.list_widget)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)

    def set_history(self, entries: list[dict]) -> None:
        """Wyświetl wpisy historii z datą w strefie czasowej użytkownika."""
        self.list_widget.clear()
        for entry in entries:
            date = datetime.fromisoformat(entry['created_at']).astimezone().strftime('%Y-%m-%d %H:%M:%S')
            label = f"{entry['status']}: {entry['target']} — {date}"
            item = QListWidgetItem(label)
            item.setToolTip(label)
            self.list_widget.addItem(item)
