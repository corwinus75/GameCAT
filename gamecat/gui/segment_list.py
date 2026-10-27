"""Wirtualna lista segmentów: Qt tworzy tylko widoczne wiersze, a nie obiekt na każdy segment."""
from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QItemSelectionModel, Qt, Signal
from PySide6.QtWidgets import QListView
from gamecat.models.segment import Segment, SegmentStatus

_BADGES = {
    SegmentStatus.NEW: 'N',
    SegmentStatus.TRANSLATED: 'T',
    SegmentStatus.REVIEWED: 'R',
    SegmentStatus.APPROVED: 'A',
}


class SegmentListModel(QAbstractListModel):
    """Model listy segmentów (``QAbstractListModel``) dostarczający dane tylko dla widocznych wierszy."""
    def __init__(self, parent=None):
        """Utwórz pusty model."""
        super().__init__(parent)
        self._rows: list[Segment] = []

    def set_rows(self, rows: list[Segment]) -> None:
        """Podmień wiersze modelu jednym resetem (bez tworzenia elementów Qt)."""
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        """Zwróć liczbę wierszy listy."""
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        """Zwróć etykietę, ID lub podpowiedź dla wiersza w zależności od roli Qt."""
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        segment = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            label = f'[{_BADGES[segment.status]}] {segment.position}: {segment.source[:70]}'
            return f'[AI] {label}' if segment.ai_generated else label
        if role == Qt.ItemDataRole.UserRole:
            return segment.id
        if role == Qt.ItemDataRole.ToolTipRole:
            return f'{segment.status.value} — segment {segment.position}'
        return None


class _ItemProxy:
    """Mały, zgodny wstecz odpowiednik ``QListWidgetItem`` używany przez istniejący kod i testy."""

    def __init__(self, view: 'SegmentListView', row: int):
        """Zapamiętaj widok i numer wiersza."""
        self._view = view
        self._row = row

    def text(self) -> str:
        """Zwróć etykietę wiersza."""
        return self._view._rows_model.data(self._view._rows_model.index(self._row),
                                          Qt.ItemDataRole.DisplayRole)

    def data(self, role: int) -> object:
        """Zwróć dane wiersza dla podanej roli Qt."""
        return self._view._rows_model.data(self._view._rows_model.index(self._row), role)

    def setSelected(self, selected: bool) -> None:
        """Zaznacz lub odznacz wiersz."""
        index = self._view._rows_model.index(self._row)
        flag = QItemSelectionModel.SelectionFlag.Select if selected else QItemSelectionModel.SelectionFlag.Deselect
        self._view.selectionModel().select(index, flag | QItemSelectionModel.SelectionFlag.Rows)


class SegmentListView(QListView):
    """Widok listy segmentów z interfejsem zgodnym z dawnym ``QListWidget``."""
    currentRowChanged = Signal(int)

    def __init__(self, parent=None):
        """Utwórz widok z modelem i przekazuj zmianę bieżącego wiersza sygnałem."""
        super().__init__(parent)
        self._rows_model = SegmentListModel(self)
        self.setModel(self._rows_model)
        self.setUniformItemSizes(True)
        self.selectionModel().currentRowChanged.connect(
            lambda current, previous: self.currentRowChanged.emit(current.row()))

    def set_rows(self, rows: list[Segment]) -> None:
        """Ustaw segmenty wyświetlane na liście."""
        self._rows_model.set_rows(rows)

    def count(self) -> int:
        """Zwróć liczbę wierszy."""
        return self._rows_model.rowCount()

    def currentRow(self) -> int:
        """Zwróć numer bieżącego wiersza (-1, gdy brak)."""
        return self.currentIndex().row()

    def setCurrentRow(self, row: int) -> None:
        """Ustaw bieżący wiersz albo wyczyść zaznaczenie dla numeru spoza zakresu."""
        if 0 <= row < self.count():
            index = self._rows_model.index(row)
            self.selectionModel().setCurrentIndex(index,
                QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)
        else:
            self.selectionModel().clearCurrentIndex()
            self.selectionModel().clearSelection()

    def item(self, row: int) -> _ItemProxy | None:
        """Zwróć pośrednika elementu dla wiersza albo ``None``."""
        return _ItemProxy(self, row) if 0 <= row < self.count() else None

    def selectedItems(self) -> list[_ItemProxy]:
        """Zwróć pośredników zaznaczonych wierszy."""
        return [_ItemProxy(self, index.row()) for index in self.selectionModel().selectedRows()]
