from PySide6.QtWidgets import QGroupBox, QTableWidget, QTableWidgetItem, QVBoxLayout
from gamecat.models.glossary import GlossaryEntry


class GlossaryPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__('Glosariusz', parent)
        self.table=QTableWidget(0,2); self.table.setHorizontalHeaderLabels(['Source','Target']); QVBoxLayout(self).addWidget(self.table)
    def set_entries(self, entries: list[GlossaryEntry]) -> None:
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self.table.setItem(row,0,QTableWidgetItem(entry.source_term)); self.table.setItem(row,1,QTableWidgetItem(entry.target_term))
