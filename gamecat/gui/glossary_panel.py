from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from gamecat.glossary.matching import contains_term
from gamecat.models.glossary import GlossaryEntry, GlossaryTerm


class GlossaryPanel(QGroupBox):
    """Project glossary editor. Persistence is delegated through Qt signals."""

    term_create_requested = Signal(object)
    term_save_requested = Signal(object)
    term_delete_requested = Signal(int)
    variant_add_requested = Signal(int, str)
    variant_delete_requested = Signal(int, str)
    import_requested = Signal()
    export_requested = Signal()
    target_insert_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__('Glosariusz', parent)
        self._terms: list[GlossaryTerm] = []
        self._visible: list[GlossaryTerm] = []
        self._current_id: int | None = None
        self._source_context = ''

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('Szukaj terminu lub wariantu…')
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Source', 'Warianty Target'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.source_edit = QLineEdit()
        self.description_edit = QPlainTextEdit()
        self.description_edit.setMaximumHeight(70)
        self.case_sensitive = QCheckBox('Case sensitive')
        self.variants = QListWidget()
        self.variants.itemDoubleClicked.connect(lambda _item: self._emit_selected_variant())

        new_button = QPushButton('Dodaj termin')
        delete_button = QPushButton('Usuń termin')
        add_variant = QPushButton('Dodaj wariant')
        remove_variant = QPushButton('Usuń wariant')
        save_button = QPushButton('Zapisz')
        import_button = QPushButton('Import CSV/JSON')
        export_button = QPushButton('Eksport CSV/JSON')

        top = QHBoxLayout(); top.addWidget(self.search_edit); top.addWidget(new_button); top.addWidget(delete_button)
        variant_buttons = QHBoxLayout(); variant_buttons.addWidget(add_variant); variant_buttons.addWidget(remove_variant)
        io_buttons = QHBoxLayout(); io_buttons.addWidget(import_button); io_buttons.addWidget(export_button); io_buttons.addWidget(save_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top); layout.addWidget(self.table)
        layout.addWidget(QLabel('Source')); layout.addWidget(self.source_edit)
        layout.addWidget(QLabel('Opis')); layout.addWidget(self.description_edit); layout.addWidget(self.case_sensitive)
        layout.addWidget(QLabel('Dopuszczalne warianty Target')); layout.addWidget(self.variants)
        layout.addLayout(variant_buttons); layout.addLayout(io_buttons)

        self.search_edit.textChanged.connect(self._refilter)
        self.table.itemSelectionChanged.connect(self._load_selected)
        new_button.clicked.connect(self._new_term)
        delete_button.clicked.connect(self._delete_current)
        add_variant.clicked.connect(self._add_variant_local)
        remove_variant.clicked.connect(self._remove_variant_local)
        save_button.clicked.connect(self._save_current)
        import_button.clicked.connect(self.import_requested.emit)
        export_button.clicked.connect(self.export_requested.emit)

    def set_terms(self, terms: list[GlossaryTerm]) -> None:
        self._terms = list(terms)
        self._refilter()

    def set_entries(self, entries: list[GlossaryEntry]) -> None:
        """Compatibility wrapper for 0.6 flat callers until MainWindow is migrated."""
        grouped: dict[tuple[str, bool, int | None], list[GlossaryEntry]] = defaultdict(list)
        for entry in entries:
            grouped[(entry.source_term, entry.case_sensitive, entry.id)].append(entry)
        terms = [
            GlossaryTerm(
                source,
                [entry.target_term for entry in group],
                next((entry.description for entry in group if entry.description), ''),
                case_sensitive,
                id=term_id,
                project_id=group[0].project_id,
            )
            for (source, case_sensitive, term_id), group in grouped.items()
        ]
        self.set_terms(terms)

    def set_source_context(self, source: str) -> None:
        self._source_context = source
        self._refilter()

    def _refilter(self) -> None:
        query = self.search_edit.text().strip().casefold()
        self._visible = [
            term for term in self._terms
            if not query or query in term.source_term.casefold() or any(query in t.casefold() for t in term.targets)
        ]
        self.table.setRowCount(len(self._visible))
        for row, term in enumerate(self._visible):
            source_item = QTableWidgetItem(term.source_term)
            target_item = QTableWidgetItem(' | '.join(term.targets))
            if self._source_context and contains_term(
                self._source_context, term.source_term, case_sensitive=term.case_sensitive
            ):
                font = QFont(source_item.font()); font.setBold(True)
                source_item.setFont(font); target_item.setFont(font)
                source_item.setToolTip('Termin występuje w Source bieżącego segmentu')
            self.table.setItem(row, 0, source_item); self.table.setItem(row, 1, target_item)

    def _selected_term(self) -> GlossaryTerm | None:
        row = self.table.currentRow()
        return self._visible[row] if 0 <= row < len(self._visible) else None

    def _load_selected(self) -> None:
        term = self._selected_term()
        if term is None:
            return
        self._current_id = term.id
        self.source_edit.setText(term.source_term)
        self.description_edit.setPlainText(term.description)
        self.case_sensitive.setChecked(term.case_sensitive)
        self.variants.clear(); self.variants.addItems(term.targets)

    def _new_term(self) -> None:
        self._current_id = None
        self.source_edit.clear(); self.description_edit.clear(); self.case_sensitive.setChecked(False); self.variants.clear()
        self.source_edit.setFocus()

    def _draft(self) -> GlossaryTerm | None:
        source = self.source_edit.text().strip()
        targets = [self.variants.item(i).text().strip() for i in range(self.variants.count()) if self.variants.item(i).text().strip()]
        if not source or not targets:
            QMessageBox.warning(self, 'GameCAT', 'Termin musi mieć Source i co najmniej jeden wariant Target.')
            return None
        existing = next((t for t in self._terms if t.id == self._current_id), None)
        return GlossaryTerm(
            source, targets, self.description_edit.toPlainText(), self.case_sensitive.isChecked(),
            id=self._current_id, project_id=existing.project_id if existing else None,
        )

    def _save_current(self) -> None:
        term = self._draft()
        if term is None:
            return
        if term.id is None:
            self.term_create_requested.emit(term)
        else:
            self.term_save_requested.emit(term)

    def _delete_current(self) -> None:
        if self._current_id is not None:
            self.term_delete_requested.emit(self._current_id)

    def _add_variant_local(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        value, ok = QInputDialog.getText(self, 'Dodaj wariant', 'Target:')
        value = value.strip()
        if not ok or not value:
            return
        existing = {self.variants.item(i).text() for i in range(self.variants.count())}
        if value in existing:
            return
        self.variants.addItem(value)
        if self._current_id is not None:
            self.variant_add_requested.emit(self._current_id, value)

    def _remove_variant_local(self) -> None:
        item = self.variants.currentItem()
        if item is None:
            return
        if self.variants.count() <= 1:
            QMessageBox.warning(self, 'GameCAT', 'Nie można usunąć ostatniego wariantu. Usuń cały termin.')
            return
        value = item.text()
        self.variants.takeItem(self.variants.row(item))
        if self._current_id is not None:
            self.variant_delete_requested.emit(self._current_id, value)

    def _emit_selected_variant(self) -> None:
        item = self.variants.currentItem()
        if item is not None:
            self.target_insert_requested.emit(item.text())
