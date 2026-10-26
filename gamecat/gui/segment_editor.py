from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gamecat.models.segment import Segment, SegmentStatus
from gamecat.workflow.status import ProjectProgress, confirmed_translation_status


_STATUS_BADGES = {
    SegmentStatus.NEW: 'N',
    SegmentStatus.TRANSLATED: 'T',
    SegmentStatus.REVIEWED: 'R',
    SegmentStatus.APPROVED: 'A',
}


class SegmentEditor(QWidget):
    """Source/target editor with navigation, searching and workflow statuses."""

    segment_changed = Signal(object)
    segment_modified = Signal(object)
    segments_status_modified = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[Segment] = []
        self._visible: list[Segment] = []
        self._loading = False

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('Szukaj Source/Target...')
        self.status_filter = QComboBox()
        self.status_filter.addItems(['ALL', *[s.value for s in SegmentStatus]])
        self.segment_list = QListWidget()
        self.segment_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.source_edit = QPlainTextEdit()
        self.source_edit.setReadOnly(True)
        self.target_edit = QPlainTextEdit()
        self.status_combo = QComboBox()
        self.status_combo.addItems([s.value for s in SegmentStatus])

        controls = QHBoxLayout()
        controls.addWidget(QLabel('Szukaj:'))
        controls.addWidget(self.search_edit)
        controls.addWidget(QLabel('Filtr statusu:'))
        controls.addWidget(self.status_filter)

        texts = QWidget()
        texts_layout = QVBoxLayout(texts)
        texts_layout.addWidget(QLabel('Source'))
        texts_layout.addWidget(self.source_edit)
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel('Status segmentu:'))
        status_row.addWidget(self.status_combo)
        status_row.addStretch(1)
        texts_layout.addLayout(status_row)
        texts_layout.addWidget(QLabel('Target'))
        texts_layout.addWidget(self.target_edit)

        splitter = QSplitter()
        splitter.addWidget(self.segment_list)
        splitter.addWidget(texts)
        splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(splitter)

        self.segment_list.currentRowChanged.connect(self._load_current)
        self.search_edit.textChanged.connect(self._refilter)
        self.status_filter.currentTextChanged.connect(self._refilter)
        self.target_edit.textChanged.connect(self._on_target_changed)
        self.status_combo.currentTextChanged.connect(self._on_status_combo_changed)
        QShortcut(QKeySequence('Ctrl+Enter'), self, activated=self.confirm_current)
        QShortcut(QKeySequence('Alt+Down'), self, activated=self.next_segment)
        QShortcut(QKeySequence('Alt+Up'), self, activated=self.previous_segment)
        QShortcut(QKeySequence('Ctrl+F'), self, activated=self.search_edit.setFocus)

    def set_segments(self, segments: list[Segment]) -> None:
        self._segments = segments
        self._refilter()

    def project_progress(self) -> ProjectProgress:
        counts = Counter(segment.status for segment in self._segments)
        return ProjectProgress.from_counts(counts)

    @staticmethod
    def _item_text(segment: Segment) -> str:
        badge = _STATUS_BADGES[segment.status]
        return f'[{badge}] {segment.position}: {segment.source[:70]}'

    def _refilter(self) -> None:
        query = self.search_edit.text().casefold()
        status = self.status_filter.currentText()
        current = self.current_segment()
        current_id = current.id if current else None
        self._visible = [
            segment
            for segment in self._segments
            if (
                not query
                or query in segment.source.casefold()
                or query in segment.target.casefold()
            )
            and (status in ('', 'ALL') or segment.status.value == status)
        ]
        self.segment_list.clear()
        for segment in self._visible:
            item = QListWidgetItem(self._item_text(segment))
            item.setData(256, segment.id)
            item.setToolTip(f'{segment.status.value} — segment {segment.position}')
            self.segment_list.addItem(item)
        if self._visible:
            row = next(
                (
                    i
                    for i, segment in enumerate(self._visible)
                    if current_id is not None and segment.id == current_id
                ),
                0,
            )
            self.segment_list.setCurrentRow(row)
        else:
            self._loading = True
            try:
                self.source_edit.clear()
                self.target_edit.clear()
                self.status_combo.setCurrentText(SegmentStatus.NEW.value)
            finally:
                self._loading = False

    def current_segment(self) -> Segment | None:
        row = self.segment_list.currentRow()
        return self._visible[row] if 0 <= row < len(self._visible) else None

    def selected_segments(self) -> list[Segment]:
        selected_ids = {item.data(256) for item in self.segment_list.selectedItems()}
        if selected_ids:
            return [segment for segment in self._visible if segment.id in selected_ids]
        current = self.current_segment()
        return [current] if current is not None else []

    def _load_current(self, row: int) -> None:
        segment = self.current_segment()
        self._loading = True
        try:
            self.source_edit.setPlainText(segment.source if segment else '')
            self.target_edit.setPlainText(segment.target if segment else '')
            self.status_combo.setCurrentText(
                segment.status.value if segment else SegmentStatus.NEW.value
            )
        finally:
            self._loading = False
        if segment:
            self.segment_changed.emit(segment)

    def _on_target_changed(self) -> None:
        if self._loading:
            return
        segment = self.current_segment()
        if segment is not None:
            segment.target = self.target_edit.toPlainText()
            self.segment_modified.emit(segment)

    def _on_status_combo_changed(self, value: str) -> None:
        if self._loading:
            return
        segment = self.current_segment()
        if segment is None:
            return
        status = SegmentStatus(value)
        if segment.status is status:
            return
        segment.status = status
        self.segments_status_modified.emit([segment])
        self._refilter()

    def set_selected_status(self, status: SegmentStatus | str) -> int:
        resolved = status if isinstance(status, SegmentStatus) else SegmentStatus(status)
        segments = self.selected_segments()
        changed = [segment for segment in segments if segment.status is not resolved]
        if not changed:
            return 0
        for segment in changed:
            segment.status = resolved
        self.segments_status_modified.emit(changed)
        self._refilter()
        return len(changed)

    def confirm_current(self) -> None:
        segment = self.current_segment()
        if segment is None:
            return
        segment.target = self.target_edit.toPlainText()
        old_status = segment.status
        segment.status = confirmed_translation_status(segment.status)
        self.segment_modified.emit(segment)
        if segment.status is not old_status:
            self.segments_status_modified.emit([segment])
        self.next_segment()

    def select_segment_by_id(self, segment_id: int, reveal: bool = True) -> bool:
        """Select a segment by database id; optionally clear filters that hide it."""

        def visible_row() -> int | None:
            return next(
                (i for i, segment in enumerate(self._visible) if segment.id == segment_id),
                None,
            )

        row = visible_row()
        if row is None and reveal:
            self.search_edit.clear()
            self.status_filter.setCurrentText('ALL')
            row = visible_row()
        if row is None:
            return False
        self.segment_list.setCurrentRow(row)
        self.target_edit.setFocus()
        return True

    def next_segment(self) -> None:
        row = self.segment_list.currentRow()
        if row + 1 < self.segment_list.count():
            self.segment_list.setCurrentRow(row + 1)

    def previous_segment(self) -> None:
        row = self.segment_list.currentRow()
        if row > 0:
            self.segment_list.setCurrentRow(row - 1)
