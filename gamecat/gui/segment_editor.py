"""Edytor segmentów: lista, wyszukiwanie w tle, szkice Target i akcje workflow."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, Future
from threading import Event
import re

from PySide6.QtCore import Signal, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gamecat.gui.glossary_source_edit import GlossarySourceEdit
from gamecat.gui.segment_list import SegmentListView
from gamecat.models.segment import Segment, SegmentStatus
from gamecat.workflow.status import ProjectProgress
from gamecat.search.operations import SearchQuery
from gamecat.search.index import SegmentSearchIndex


_STATUS_BADGES = {
    SegmentStatus.NEW: 'N',
    SegmentStatus.TRANSLATED: 'T',
    SegmentStatus.REVIEWED: 'R',
    SegmentStatus.APPROVED: 'A',
}


class SegmentEditor(QWidget):
    """Edytor Source/Target z nawigacją, wyszukiwaniem i statusami workflow.

    Zmiany Target i komentarza są szkicami w pamięci; trwały zapis następuje
    dopiero po akcji użytkownika (Zapisz, Zatwierdź, LQA). Filtrowanie dużych
    projektów działa w wątku tła na migawce indeksu.
    """

    segment_changed = Signal(object)
    segment_modified = Signal(object)  # Legacy signal for explicit external operations.
    draft_changed = Signal(object, str)
    action_requested = Signal(object, object, str, str)
    segments_status_modified = Signal(object)
    search_context_requested = Signal()

    def __init__(self, parent=None):
        """Zbuduj listę segmentów, filtry, pola Source/Target/komentarza i przyciski akcji."""
        super().__init__(parent)
        self._segments: list[Segment] = []
        self._visible: list[Segment] = []
        self._loading = False
        self._qa_error_ids: set[int] = set()
        self._tm_match_ids: set[int] = set()
        self._search_valid = True
        self._drafts: dict[int, tuple[str, str]] = {}
        self._search_index = SegmentSearchIndex([])
        self._search_executor: ThreadPoolExecutor | None = None
        self._search_future: Future | None = None
        self._search_cancel: Event | None = None
        self._search_generation = 0
        self._search_busy = False
        self._search_closed = False
        self._applying_results = False
        self._selection_hint: int | None = None
        self._pending_selection_id: int | None = None
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._submit_background_search)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('Szukaj w Source/Target (Ctrl+F)…')
        self.search_scope = QComboBox()
        for title, mode in [('Source + Target', 'both'), ('Source', 'source'), ('Target', 'target')]:
            self.search_scope.addItem(title, mode)
        self.regex_check = QCheckBox('Regex')
        self.case_check = QCheckBox('Aa')
        self.case_check.setToolTip('Rozróżniaj wielkość liter')
        self.search_error = QLabel('')
        self.search_progress = QLabel('')
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
        self.segment_list = SegmentListView()
        self.segment_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.source_edit = GlossarySourceEdit()
        self.target_edit = QPlainTextEdit()
        self.comment_edit = QPlainTextEdit()
        self.comment_edit.setPlaceholderText('Komentarz, nazwa postaci, kontekst dialogu…')
        self.comment_edit.setMaximumHeight(100)
        self.status_combo = QComboBox()
        self.status_combo.addItems([s.value for s in SegmentStatus])
        self.status_combo.setToolTip('Sam wybór statusu nie zapisuje segmentu. Użyj Zapisz, Zatwierdź albo LQA.')
        self.save_translation_button = QPushButton('Zapisz')
        self.review_button = QPushButton('Zatwierdź')
        self.lqa_button = QPushButton('LQA')
        self.draft_label = QLabel('')
        self.draft_label.setStyleSheet('color: #a05a00')

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
        filters.addWidget(self.search_progress)
        filters.addWidget(self.search_error)

        texts = QWidget()
        texts_layout = QVBoxLayout(texts)
        texts_layout.addWidget(QLabel('Source'))
        texts_layout.addWidget(self.source_edit)
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel('Status (zmiana wymaga przycisku):'))
        status_row.addWidget(self.status_combo)
        status_row.addStretch(1)
        texts_layout.addLayout(status_row)
        texts_layout.addWidget(QLabel('Target'))
        texts_layout.addWidget(self.target_edit)
        texts_layout.addWidget(QLabel('Kontekst / komentarz segmentu'))
        texts_layout.addWidget(self.comment_edit)
        action_buttons = QHBoxLayout()
        for button in (self.save_translation_button, self.review_button, self.lqa_button):
            action_buttons.addWidget(button)
        action_buttons.addWidget(self.draft_label)
        texts_layout.addLayout(action_buttons)

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
        self.comment_edit.textChanged.connect(self._on_comment_changed)
        self.status_combo.currentTextChanged.connect(self._on_status_combo_changed)
        self.save_translation_button.clicked.connect(
            lambda checked=False: self.request_action(SegmentStatus.TRANSLATED))
        self.review_button.clicked.connect(
            lambda checked=False: self.request_action(SegmentStatus.REVIEWED))
        self.lqa_button.clicked.connect(
            lambda checked=False: self.request_action(SegmentStatus.APPROVED))
        QShortcut(QKeySequence('Ctrl+Enter'), self, activated=self.confirm_current)
        QShortcut(QKeySequence('Alt+Down'), self, activated=self.next_segment)
        QShortcut(QKeySequence('Alt+Up'), self, activated=self.previous_segment)
        QShortcut(QKeySequence('Ctrl+F'), self, activated=self.search_edit.setFocus)

    def set_segments(self, segments: list[Segment], *, preserve_drafts: bool = False) -> None:
        """Załaduj segmenty projektu; opcjonalnie zachowaj szkice istniejących segmentów."""
        self._invalidate_search()
        if preserve_drafts:
            valid_ids = {segment.id for segment in segments}
            self._drafts = {sid: draft for sid, draft in self._drafts.items() if sid in valid_ids}
        else:
            self._drafts.clear()
        self._selection_hint = self.current_segment().id if self.current_segment() else None
        self._segments = segments
        # Never leave rows from the previously opened project actionable while
        # the new project's initial asynchronous search is pending.
        self._applying_results = True
        try:
            self._visible = []
            self.segment_list.set_rows([])
        finally:
            self._applying_results = False
        self._search_index = SegmentSearchIndex(segments)
        self._refilter()

    def project_progress(self) -> ProjectProgress:
        """Policz postęp na podstawie segmentów załadowanych w edytorze."""
        counts = Counter(segment.status for segment in self._segments)
        return ProjectProgress.from_counts(counts)

    @staticmethod
    def _item_text(segment: Segment) -> str:
        """Zwróć etykietę segmentu na liście (status, pozycja, początek Source)."""
        badge = _STATUS_BADGES[segment.status]
        return f'[AI] [{badge}] {segment.position}: {segment.source[:70]}' if segment.ai_generated else f'[{badge}] {segment.position}: {segment.source[:70]}'

    def _on_quality_filter_changed(self, *_args) -> None:
        """Poproś o indeks QA/TM, gdy wybrany filtr jakości go wymaga."""
        if self.quality_filter.currentData() in {'qa_errors', 'tm_match'}:
            self.search_context_requested.emit()
        else:
            self._refilter()

    def set_search_context(self, *, qa_error_ids=None, tm_match_ids=None) -> None:
        """Zaktualizuj zbiory ID segmentów z błędami QA i dopasowaniami TM."""
        if qa_error_ids is not None:
            self._qa_error_ids = set(qa_error_ids)
        if tm_match_ids is not None:
            self._tm_match_ids = set(tm_match_ids)
        self._refilter()

    @property
    def search_valid(self) -> bool:
        """Czy bieżący wzorzec wyszukiwania jest poprawny."""
        return self._search_valid

    def all_segments(self) -> list[Segment]:
        """Zwróć kopię listy wszystkich segmentów projektu."""
        return list(self._segments)

    def clear_filters(self) -> None:
        """Przywróć domyślne filtry i pustą frazę wyszukiwania."""
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
        """Zwróć kopię listy segmentów widocznych po filtrowaniu."""
        return list(self._visible)

    @property
    def search_busy(self) -> bool:
        """Czy widoczne wyniki nie odpowiadają jeszcze wprowadzonym filtrom."""
        return self._search_busy

    def _invalidate_search(self) -> int:
        """Unieważnij trwające wyszukiwanie i zwróć nowy numer generacji."""
        self._search_generation += 1
        self._search_timer.stop()
        if self._search_cancel is not None:
            self._search_cancel.set()
        if self._search_future is not None:
            self._search_future.cancel()
        self._search_cancel = None
        self._search_future = None
        return self._search_generation

    def _query(self) -> SearchQuery:
        """Zbuduj zapytanie wyszukiwania z bieżących ustawień filtrów."""
        return SearchQuery(
            self.search_edit.text(),
            scope=self.search_scope.currentData() or 'both',
            regex=self.regex_check.isChecked(),
            case_sensitive=self.case_check.isChecked(),
            status=self.status_filter.currentText() or 'ALL',
            quality=self.quality_filter.currentData() or 'all',
            sort=self.sort_combo.currentData() or 'position',
            descending=self.sort_descending.isChecked(),
        )

    def _refilter(self, *_args) -> None:
        """Odśwież listę po zmianie filtrów.

        Małe projekty są filtrowane od razu, duże – z opóźnieniem w wątku tła;
        błędny regex jest zgłaszany natychmiast.
        """
        if self._search_closed:
            return
        token = self._invalidate_search()
        query = self._query()
        # Invalid patterns are reported immediately even for huge projects.
        try:
            if query.regex and query.phrase:
                re.compile(query.phrase, 0 if query.case_sensitive else re.IGNORECASE)
        except re.error as exc:
            self._search_valid = False
            self._search_busy = False
            self.search_progress.clear()
            self.search_error.setText(f'Błąd wzorca: Invalid search regex: {exc}')
            self.search_error.setVisible(True)
            self.search_edit.setStyleSheet('border: 1px solid #b03a2e;')
            self._apply_results([], token)
            return
        self._search_valid = True
        self.search_error.setVisible(False)
        self.search_edit.setStyleSheet('')
        if len(self._segments) <= 1500:
            # Small projects retain the immediate search behaviour.
            try:
                indexes = self._search_index.search(query,
                    qa_error_ids=self._qa_error_ids, tm_match_ids=self._tm_match_ids)
            except ValueError as exc:
                self._search_valid = False
                self.search_error.setText(str(exc))
                self.search_error.setVisible(True)
                indexes = []
            self._apply_results(indexes or [], token)
        else:
            self._search_busy = True
            self.search_progress.setText('Wyszukiwanie…')
            self._search_timer.start()

    def _submit_background_search(self) -> None:
        """Uruchom filtrowanie migawki indeksu w wątku tła i odbierz wynik przez ``QTimer``."""
        if self._search_closed:
            return
        token = self._search_generation
        if self._search_executor is None:
            self._search_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='gamecat-search')
        cancel = Event()
        self._search_cancel = cancel
        query = self._query()
        # Index and quality filters are immutable snapshots used only by the worker.
        index = self._search_index
        future = self._search_executor.submit(index.search, query,
            qa_error_ids=frozenset(self._qa_error_ids),
            tm_match_ids=frozenset(self._tm_match_ids), cancel=cancel)
        self._search_future = future

        def poll() -> None:
            if self._search_closed or token != self._search_generation:
                return
            if not future.done():
                QTimer.singleShot(30, poll)
                return
            try:
                indexes = future.result()
            except ValueError as exc:
                self._search_valid = False
                self.search_error.setText(str(exc))
                self.search_error.setVisible(True)
                indexes = []
            except Exception as exc:
                self._search_valid = False
                self.search_error.setText(f'Błąd wyszukiwania: {exc}')
                self.search_error.setVisible(True)
                indexes = []
            if indexes is not None:
                self._apply_results(indexes, token)

        QTimer.singleShot(0, poll)

    def _apply_results(self, indexes: list[int], token: int) -> None:
        """Pokaż wyniki filtrowania, jeśli są aktualne, zachowując zaznaczenie segmentu."""
        if token != self._search_generation or self._search_closed:
            return
        current = self.current_segment()
        current_id = (self._pending_selection_id if self._pending_selection_id is not None
                      else current.id if current else self._selection_hint)
        # Creating thousands of QListWidgetItem objects was the primary UI freeze.
        self._visible = [self._segments[i] for i in indexes]
        self._search_busy = False
        self.search_progress.clear()
        self._applying_results = True
        try:
            self.segment_list.set_rows(self._visible)
            if self._visible:
                row = next((i for i, segment in enumerate(self._visible)
                            if current_id is not None and segment.id == current_id), 0)
                self.segment_list.setCurrentRow(row)
            else:
                self.segment_list.setCurrentRow(-1)
        finally:
            self._applying_results = False
        self._selection_hint = None
        if self._pending_selection_id is not None and any(
            segment.id == self._pending_selection_id for segment in self._visible
        ):
            self._pending_selection_id = None
        self._load_current(self.segment_list.currentRow())

    def stop_search(self) -> None:
        """Anuluj oczekujące wyszukiwania przy zamykaniu okna lub aplikacji."""
        if self._search_closed:
            return
        self._search_closed = True
        self._invalidate_search()
        if self._search_executor is not None:
            self._search_executor.shutdown(wait=False, cancel_futures=True)

    def closeEvent(self, event) -> None:
        """Zatrzymaj wyszukiwanie w tle przed zamknięciem widżetu."""
        self.stop_search()
        super().closeEvent(event)

    def current_segment(self) -> Segment | None:
        """Zwróć bieżący segment z listy widocznych albo ``None``."""
        row = self.segment_list.currentRow()
        return self._visible[row] if 0 <= row < len(self._visible) else None

    def selected_segments(self) -> list[Segment]:
        """Zwróć zaznaczone segmenty (lub bieżący, gdy nic nie zaznaczono)."""
        selected_ids = {item.data(256) for item in self.segment_list.selectedItems()}
        if selected_ids:
            return [segment for segment in self._visible if segment.id in selected_ids]
        current = self.current_segment()
        return [current] if current is not None else []

    def _load_current(self, row: int) -> None:
        """Wczytaj bieżący segment (lub jego szkic) do pól edytora."""
        if self._applying_results:
            return
        segment = self.current_segment()
        self._loading = True
        try:
            self.source_edit.setPlainText(segment.source if segment else '')
            draft = self._drafts.get(segment.id) if segment and segment.id is not None else None
            self.target_edit.setPlainText(draft[0] if draft else (segment.target if segment else ''))
            self.comment_edit.setPlainText(draft[1] if draft else (segment.comment if segment else ''))
            self.draft_label.setText('Niezapisane' if draft else '')
            self.status_combo.setCurrentText(
                segment.status.value if segment else SegmentStatus.NEW.value
            )
        finally:
            self._loading = False
        if segment:
            self.segment_changed.emit(segment)

    @property
    def has_unsaved_drafts(self) -> bool:
        """Czy istnieją niezapisane szkice tłumaczeń."""
        return bool(self._drafts)

    def _draft_changed(self) -> None:
        """Zapamiętaj szkic Target i komentarza tylko w RAM – bez zmian w ``Segment`` i SQLite."""
        if self._loading:
            return
        segment = self.current_segment()
        if segment is None or segment.id is None:
            return
        target = self.target_edit.toPlainText()
        comment = self.comment_edit.toPlainText()
        if (target, comment) == (segment.target, segment.comment):
            self._drafts.pop(segment.id, None)
        else:
            self._drafts[segment.id] = (target, comment)
        self.draft_label.setText('Niezapisane' if segment.id in self._drafts else '')
        self.draft_changed.emit(segment, target)

    def _on_comment_changed(self) -> None:
        """Obsłuż zmianę komentarza jako zmianę szkicu."""
        self._draft_changed()

    def _on_target_changed(self) -> None:
        """Obsłuż zmianę Target jako zmianę szkicu."""
        self._draft_changed()

    def _on_status_combo_changed(self, value: str) -> None:
        """Lista statusów jest tylko podglądem – zatwierdza dopiero przycisk akcji."""
        if self._loading or self.current_segment() is None:
            return
        self.draft_label.setText('Wybierz przycisk zapisu statusu')

    def request_action(self, status: SegmentStatus | str) -> None:
        """Zgłoś akcję workflow (zapis z wybranym statusem) dla bieżącego szkicu."""
        segment = self.current_segment()
        if segment is None or segment.id is None:
            return
        status = SegmentStatus(status)
        target = self.target_edit.toPlainText()
        comment = self.comment_edit.toPlainText()
        self.action_requested.emit(segment, status, target, comment)

    def accept_saved_segment(self, persisted: Segment) -> None:
        """Zaktualizuj segment na liście dopiero po udanym zapisie w bazie i usuń jego szkic."""
        existing = next((s for s in self._segments if s.id == persisted.id), None)
        if existing is None:
            return
        existing.target = persisted.target
        existing.status = persisted.status
        existing.comment = persisted.comment
        existing.updated_at = persisted.updated_at
        existing.ai_generated = persisted.ai_generated
        self._drafts.pop(persisted.id, None)
        self._search_index = self._search_index.updated(existing)
        self._refilter()

    def set_selected_status(self, status: SegmentStatus | str) -> int:
        """Zmień status zaznaczonych segmentów jako jawną akcję (polecenia z menu)."""
        resolved = SegmentStatus(status)
        segments = self.selected_segments()
        if resolved is SegmentStatus.NEW:
            # This legacy reset stays explicit; NEW has no translation-history entry.
            for segment in segments:
                segment.status = SegmentStatus.NEW
            self.segments_status_modified.emit(segments)
            self._search_index = SegmentSearchIndex(self._segments)
            self._refilter()
            return len(segments)
        for segment in segments:
            if segment.id is None:
                continue
            draft = self._drafts.get(segment.id, (segment.target, segment.comment))
            self.action_requested.emit(segment, resolved, *draft)
        return len(segments)

    def confirm_current(self) -> None:
        """Ctrl+Enter działa jak przycisk Zapisz (status ``TRANSLATED``)."""
        self.request_action(SegmentStatus.TRANSLATED)

    def select_segment_by_id(self, segment_id: int, reveal: bool = True) -> bool:
        """Zaznacz segment po ID bazy; z ``reveal`` wyczyść filtry, które go ukrywają."""
        def visible_row() -> int | None:
            return next((i for i, segment in enumerate(self._visible) if segment.id == segment_id), None)

        row = visible_row()
        if row is not None:
            self.segment_list.setCurrentRow(row)
            self.target_edit.setFocus()
            return True
        if not reveal or not any(s.id == segment_id for s in self._segments):
            return False
        self._pending_selection_id = segment_id
        self.search_edit.clear()
        self.status_filter.setCurrentText('ALL')
        self.quality_filter.setCurrentIndex(0)
        row = visible_row()
        if row is not None and not self.search_busy:
            self.segment_list.setCurrentRow(row)
            self._pending_selection_id = None
            self.target_edit.setFocus()
        # For large projects the selection will be applied when the async
        # result arrives; do not claim that the segment is absent meanwhile.
        return True


    def insert_target_text(self, text: str) -> None:
        """Wstaw tekst (np. termin glosariusza) w miejscu kursora w Target."""
        cursor = self.target_edit.textCursor()
        cursor.insertText(text)
        self.target_edit.setTextCursor(cursor)
        self.target_edit.setFocus()

    def jump_to_next(self, kind: str, *, backwards: bool = False, anchor_id: int | None = None) -> bool:
        """Przejdź do następnego (lub poprzedniego) segmentu bez tłumaczenia albo z błędem QA.

        Wyszukiwanie zawija się na końcu listy. Zwraca ``False``, gdy brak kandydatów.

        :raises ValueError: nieznany rodzaj nawigacji.
        """
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
        """Przejdź do następnego segmentu na liście."""
        row = self.segment_list.currentRow()
        if row + 1 < self.segment_list.count():
            self.segment_list.setCurrentRow(row + 1)

    def previous_segment(self) -> None:
        """Przejdź do poprzedniego segmentu na liście."""
        row = self.segment_list.currentRow()
        if row > 0:
            self.segment_list.setCurrentRow(row - 1)
