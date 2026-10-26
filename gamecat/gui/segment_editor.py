from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gamecat.models.segment import Segment, SegmentStatus
from gamecat.workflow.status import ProjectProgress, confirmed_translation_status
from gamecat.search.operations import SearchQuery, filter_segments


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
    search_context_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[Segment] = []
        self._visible: list[Segment] = []
        self._loading = False
        self._qa_error_ids: set[int] = set()
        self._tm_match_ids: set[int] = set()
        self._search_valid = True

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('Szukaj w Source/Target (Ctrl+F)…')
        self.search_scope = QComboBox()
        for title, mode in [('Source + Target', 'both'), ('Source', 'source'), ('Target', 'target')]:
            self.search_scope.addItem(title, mode)
        self.regex_check = QCheckBox('Regex')
        self.case_check = QCheckBox('Aa')
        self.case_check.setToolTip('Rozróżniaj wielkość liter')
        self.search_error = QLabel('')
        self.search_error.setStyleSheet('color: #b03a2e')
        self.search_error.setVisible(False)
        self.quality_filter = QComboBox()
        for title, code in [('Wszystkie', 'all'), ('Bez tłumaczenia', 'untranslated'),
                            ('Błędy QA', 'qa_errors'), ('Dopasowanie TM 100%', 'tm_match')]:
            self.quality_filter.addItem(title, code)
        self.sort_combo = QComboBox()
        for title, code in [('Pozycja', 'position'), ('Source A-Z', 'source'), ('Status', 'status')]:
            self.sort_combo.addItem(title, code)
        self.sort_descending = QCheckBox('Malejąco')
        self.refresh_filters_button = QPushButton('Odśwież filtry')
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
        controls.addWidget(self.search_scope)
        controls.addWidget(self.regex_check)
        controls.addWidget(self.case_check)
        controls.addWidget(QLabel('Status:'))
        controls.addWidget(self.status_filter)
        filters = QHBoxLayout()
        filters.addWidget(QLabel('Filtr:'))
        filters.addWidget(self.quality_filter)
        filters.addWidget(QLabel('Sortuj:'))
        filters.addWidget(self.sort_combo)
        filters.addWidget(self.sort_descending)
        filters.addWidget(self.refresh_filters_button)
        filters.addStretch(1)
        filters.addWidget(self.search_error)

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
        layout.addLayout(filters)
        layout.addWidget(splitter)

        self.segment_list.currentRowChanged.connect(self._load_current)
        self.search_edit.textChanged.connect(self._refilter)
        self.status_filter.currentTextChanged.connect(self._refilter)
        self.search_scope.currentIndexChanged.connect(self._refilter)
        self.regex_check.toggled.connect(self._refilter)
        self.case_check.toggled.connect(self._refilter)
        self.quality_filter.currentIndexChanged.connect(self._on_quality_filter_changed)
        self.sort_combo.currentIndexChanged.connect(self._refilter)
        self.sort_descending.toggled.connect(self._refilter)
        self.refresh_filters_button.clicked.connect(lambda checked=False: self.search_context_requested.emit())
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

    def _on_quality_filter_changed(self, *_args) -> None:
        if self.quality_filter.currentData() in {'qa_errors', 'tm_match'}:
            self.search_context_requested.emit()
        else:
            self._refilter()

    def set_search_context(self, *, qa_error_ids=None, tm_match_ids=None) -> None:
        """Update cached quality indexes; call when project/QA/TM changes."""
        if qa_error_ids is not None:
            self._qa_error_ids = set(qa_error_ids)
        if tm_match_ids is not None:
            self._tm_match_ids = set(tm_match_ids)
        self._refilter()

    @property
    def search_valid(self) -> bool:
        return self._search_valid

    def all_segments(self) -> list[Segment]:
        return list(self._segments)

    def clear_filters(self) -> None:
        self.search_edit.clear()
        self.status_filter.setCurrentText('ALL')
        self.quality_filter.setCurrentIndex(0)
        self.search_scope.setCurrentIndex(0)
        self.regex_check.setChecked(False)
        self.case_check.setChecked(False)
        self.sort_combo.setCurrentIndex(0)
        self.sort_descending.setChecked(False)
        self._qa_error_ids.clear()
        self._tm_match_ids.clear()
        self._refilter()

    def visible_segments(self) -> list[Segment]:
        return list(self._visible)

    def _refilter(self, *_args) -> None:
        current = self.current_segment()
        current_id = current.id if current else None
        query = SearchQuery(
            self.search_edit.text(),
            scope=self.search_scope.currentData() or 'both',
            regex=self.regex_check.isChecked(),
            case_sensitive=self.case_check.isChecked(),
            status=self.status_filter.currentText() or 'ALL',
            quality=self.quality_filter.currentData() or 'all',
            sort=self.sort_combo.currentData() or 'position',
            descending=self.sort_descending.isChecked(),
        )
        try:
            filtered = filter_segments(
                self._segments, query,
                qa_error_ids=self._qa_error_ids,
                tm_match_ids=self._tm_match_ids,
            )
        except ValueError as exc:
            self._search_valid = False
            self.search_error.setText(f'Błąd wzorca: {exc}')
            self.search_error.setVisible(True)
            self.search_edit.setStyleSheet('border: 1px solid #b03a2e;')
            self._visible = []
            self.segment_list.clear()
            self._loading = True
            try:
                self.source_edit.clear()
                self.target_edit.clear()
            finally:
                self._loading = False
            return
        self._search_valid = True
        self.search_error.setVisible(False)
        self.search_edit.setStyleSheet('')
        self._visible = filtered
        self.segment_list.clear()
        for segment in self._visible:
            item = QListWidgetItem(self._item_text(segment))
            item.setData(256, segment.id)
            item.setToolTip(f'{segment.status.value} — segment {segment.position}')
            self.segment_list.addItem(item)
        if self._visible:
            row = next((i for i, segment in enumerate(self._visible)
                        if current_id is not None and segment.id == current_id), 0)
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
            self.quality_filter.setCurrentIndex(0)
            row = visible_row()
        if row is None:
            return False
        self.segment_list.setCurrentRow(row)
        self.target_edit.setFocus()
        return True


    def insert_target_text(self, text: str) -> None:
        """Insert glossary text at the current Target cursor position."""
        cursor = self.target_edit.textCursor()
        cursor.insertText(text)
        self.target_edit.setTextCursor(cursor)
        self.target_edit.setFocus()

    def jump_to_next(self, kind: str, *, backwards: bool = False, anchor_id: int | None = None) -> bool:
        """Move to next untranslated or QA-flagged segment, with wraparound."""
        if kind not in {'untranslated', 'qa_errors'}:
            raise ValueError('Unknown navigation type')
        candidates = sorted(self._segments, key=lambda s: (s.position, s.id or 0))
        if not candidates:
            return False
        selected = self.current_segment()
        current_id = anchor_id if anchor_id is not None else (selected.id if selected else None)
        index = next((i for i, s in enumerate(candidates)
                      if current_id is not None and s.id == current_id),
                     0 if backwards else -1)
        increment = -1 if backwards else 1
        for offset in range(1, len(candidates) + 1):
            segment = candidates[(index + increment * offset) % len(candidates)]
            valid = (not segment.target.strip() if kind == 'untranslated'
                     else segment.id in self._qa_error_ids)
            if valid and segment.id is not None:
                return self.select_segment_by_id(segment.id, reveal=True)
        return False

    def next_segment(self) -> None:
        row = self.segment_list.currentRow()
        if row + 1 < self.segment_list.count():
            self.segment_list.setCurrentRow(row + 1)

    def previous_segment(self) -> None:
        row = self.segment_list.currentRow()
        if row > 0:
            self.segment_list.setCurrentRow(row - 1)
