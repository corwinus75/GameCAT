from __future__ import annotations
from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget
from gamecat.models.segment import Segment, SegmentStatus


class SegmentEditor(QWidget):
    """Source/target editor with navigation, searching and status filtering."""
    segment_changed = Signal(object)
    segment_modified = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[Segment] = []
        self._visible: list[Segment] = []
        self._loading = False
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText('Szukaj Source/Target...')
        self.status_filter = QComboBox(); self.status_filter.addItems(['ALL', *[s.value for s in SegmentStatus]])
        self.segment_list = QListWidget()
        self.source_edit = QPlainTextEdit(); self.source_edit.setReadOnly(True)
        self.target_edit = QPlainTextEdit()
        controls = QHBoxLayout(); controls.addWidget(QLabel('Szukaj:')); controls.addWidget(self.search_edit); controls.addWidget(QLabel('Status:')); controls.addWidget(self.status_filter)
        texts = QWidget(); texts_layout=QVBoxLayout(texts); texts_layout.addWidget(QLabel('Source')); texts_layout.addWidget(self.source_edit); texts_layout.addWidget(QLabel('Target')); texts_layout.addWidget(self.target_edit)
        splitter = QSplitter(); splitter.addWidget(self.segment_list); splitter.addWidget(texts); splitter.setStretchFactor(1, 1)
        layout=QVBoxLayout(self); layout.addLayout(controls); layout.addWidget(splitter)
        self.segment_list.currentRowChanged.connect(self._load_current)
        self.search_edit.textChanged.connect(self._refilter); self.status_filter.currentTextChanged.connect(self._refilter)
        self.target_edit.textChanged.connect(self._on_target_changed)
        QShortcut(QKeySequence('Ctrl+Enter'), self, activated=self.confirm_current)
        QShortcut(QKeySequence('Alt+Down'), self, activated=self.next_segment)
        QShortcut(QKeySequence('Alt+Up'), self, activated=self.previous_segment)
        QShortcut(QKeySequence('Ctrl+F'), self, activated=self.search_edit.setFocus)

    def set_segments(self, segments: list[Segment]) -> None:
        self._segments = segments
        self._refilter()

    def _refilter(self) -> None:
        query = self.search_edit.text().casefold()
        status = self.status_filter.currentText()
        self._visible = [s for s in self._segments if (not query or query in s.source.casefold() or query in s.target.casefold()) and (status in ('','ALL') or s.status.value == status)]
        current_id = self.current_segment().id if self.current_segment() else None
        self.segment_list.clear()
        for segment in self._visible:
            item=QListWidgetItem(f'{segment.position}: {segment.source[:70]}'); item.setData(256, segment.id)
            self.segment_list.addItem(item)
        if self._visible:
            row = next((i for i,s in enumerate(self._visible) if current_id is not None and s.id == current_id), 0)
            self.segment_list.setCurrentRow(row)
        else:
            self.source_edit.clear(); self.target_edit.clear()

    def current_segment(self) -> Segment | None:
        row=self.segment_list.currentRow()
        return self._visible[row] if 0 <= row < len(self._visible) else None

    def _load_current(self, row: int) -> None:
        segment = self.current_segment()
        self._loading=True
        try:
            self.source_edit.setPlainText(segment.source if segment else '')
            self.target_edit.setPlainText(segment.target if segment else '')
        finally:
            self._loading=False
        if segment: self.segment_changed.emit(segment)

    def _on_target_changed(self) -> None:
        if self._loading: return
        segment=self.current_segment()
        if segment is not None:
            segment.target=self.target_edit.toPlainText()
            self.segment_modified.emit(segment)

    def confirm_current(self) -> None:
        segment=self.current_segment()
        if segment is None: return
        segment.target=self.target_edit.toPlainText()
        segment.status = SegmentStatus.TRANSLATED
        self.segment_modified.emit(segment)
        self.next_segment()

    def next_segment(self) -> None:
        row=self.segment_list.currentRow()
        if row + 1 < self.segment_list.count(): self.segment_list.setCurrentRow(row + 1)

    def previous_segment(self) -> None:
        row=self.segment_list.currentRow()
        if row > 0: self.segment_list.setCurrentRow(row - 1)
