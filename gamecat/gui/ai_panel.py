"""Project-scoped OpenAI API settings, previews, and batch progress UI."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from gamecat.ai.core import AIResult, AISettings, BatchReport


class AIPanel(QWidget):
    save_requested = Signal()
    test_requested = Signal()
    translate_requested = Signal()
    batch_requested = Signal()
    cancel_requested = Signal()
    apply_requested = Signal()
    batch_item_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        content = QWidget(self)
        layout = QVBoxLayout(content)

        settings = QGroupBox('Oficjalne OpenAI API')
        form = QFormLayout(settings)
        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText('Opcjonalnie: OPENAI_API_KEY lub systemowy magazyn')
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.remember_key = QCheckBox('Zapisz klucz w magazynie poświadczeń systemu')
        self.remember_key.setChecked(False)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(['gpt-5-mini', 'gpt-5.1', 'gpt-4.1-mini'])
        self.instructions = QPlainTextEdit()
        self.instructions.setPlaceholderText('Instrukcje stylu i kontekstu dla tego projektu…')
        self.instructions.setMaximumHeight(110)
        self.input_price = QDoubleSpinBox()
        self.output_price = QDoubleSpinBox()
        for field in (self.input_price, self.output_price):
            field.setRange(0, 10000)
            field.setDecimals(5)
            field.setSingleStep(0.01)
            field.setSuffix(' USD / 1 mln tokenów')
            field.setToolTip('Wpisz cenę ręcznie na podstawie cennika OpenAI; 0 oznacza nieznaną cenę')
        self.max_output = QSpinBox()
        self.max_output.setRange(64, 16384)
        self.max_output.setValue(1024)
        form.addRow('Klucz API (sesyjny):', self.api_key)
        form.addRow('', self.remember_key)
        form.addRow('Model:', self.model)
        form.addRow('Instrukcje projektu:', self.instructions)
        form.addRow('Cena wejścia:', self.input_price)
        form.addRow('Cena wyjścia:', self.output_price)
        form.addRow('Max output tokens:', self.max_output)
        layout.addWidget(settings)
        disclosure = QLabel('Uwaga: Source, dopasowane wpisy TM i glosariusz są wysyłane do OpenAI API. ' 'Użycie API jest płatne niezależnie od ChatGPT. Ceny wpisz ręcznie.')
        disclosure.setWordWrap(True)
        layout.addWidget(disclosure)

        controls = QHBoxLayout()
        self.save_button = QPushButton('Zapisz ustawienia')
        self.test_button = QPushButton('Test połączenia')
        self.single_button = QPushButton('Tłumacz bieżący')
        for button, signal in ((self.save_button, self.save_requested),
                               (self.test_button, self.test_requested),
                               (self.single_button, self.translate_requested)):
            button.clicked.connect(lambda checked=False, emit=signal.emit: emit())
            controls.addWidget(button)
        layout.addLayout(controls)

        batch_box = QGroupBox('Tłumaczenie wsadowe (tylko puste Target)')
        batch_layout = QVBoxLayout(batch_box)
        row = QHBoxLayout()
        self.batch_scope = QComboBox()
        self.batch_scope.addItem('Pierwsze N nieprzetłumaczonych', 'untranslated')
        self.batch_scope.addItem('Zaznaczone segmenty', 'selected')
        self.batch_count = QSpinBox()
        self.batch_count.setRange(1, 1000)
        self.batch_count.setValue(20)
        self.batch_budget = QDoubleSpinBox()
        self.batch_budget.setDecimals(3)
        self.batch_budget.setRange(0.001, 10000)
        self.batch_budget.setValue(1.0)
        self.batch_budget.setSuffix(' USD')
        row.addWidget(self.batch_scope)
        row.addWidget(QLabel('Maks.:'))
        row.addWidget(self.batch_count)
        row.addWidget(QLabel('Limit szacowany:'))
        row.addWidget(self.batch_budget)
        batch_layout.addLayout(row)
        batch_buttons = QHBoxLayout()
        self.batch_button = QPushButton('Uruchom wsad')
        self.cancel_button = QPushButton('Anuluj wsad')
        self.cancel_button.setEnabled(False)
        self.batch_button.clicked.connect(lambda checked=False: self.batch_requested.emit())
        self.cancel_button.clicked.connect(lambda checked=False: self.cancel_requested.emit())
        batch_buttons.addWidget(self.batch_button)
        batch_buttons.addWidget(self.cancel_button)
        batch_layout.addLayout(batch_buttons)
        layout.addWidget(batch_box)

        self.progress_label = QLabel('Gotowe. Koszty są szacunkowe; API nalicza opłaty.')
        self.progress_label.setWordWrap(True)
        layout.addWidget(self.progress_label)
        self.suggestions = QListWidget()
        self.suggestions.setMaximumHeight(120)
        self.suggestions.itemDoubleClicked.connect(
            lambda item: self.batch_item_requested.emit(self.suggestions.row(item))
        )
        layout.addWidget(QLabel('Wyniki wsadu (dwuklik otwiera podgląd):'))
        layout.addWidget(self.suggestions)
        self.preview_caption = QLabel('Nie wygenerowano propozycji.')
        self.preview_caption.setWordWrap(True)
        layout.addWidget(self.preview_caption)
        self.preview = QPlainTextEdit()
        self.preview.setPlaceholderText('Propozycja tłumaczenia AI do ręcznego zatwierdzenia…')
        self.preview.setMinimumHeight(100)
        layout.addWidget(self.preview)
        self.apply_button = QPushButton('Zastosuj propozycję do Target')
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(lambda checked=False: self.apply_requested.emit())
        layout.addWidget(self.apply_button)
        layout.addStretch(1)

        scroller = QScrollArea(self)
        scroller.setWidgetResizable(True)
        scroller.setWidget(content)
        parent_layout = QVBoxLayout(self)
        parent_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout.addWidget(scroller)

    def get_settings(self) -> AISettings:
        return AISettings(
            model=self.model.currentText().strip(), instructions=self.instructions.toPlainText(),
            input_price_per_million=self.input_price.value(),
            output_price_per_million=self.output_price.value(),
            max_output_tokens=self.max_output.value(),
        )

    def set_settings(self, settings: AISettings) -> None:
        self.model.setCurrentText(settings.model)
        self.instructions.setPlainText(settings.instructions)
        self.input_price.setValue(settings.input_price_per_million)
        self.output_price.setValue(settings.output_price_per_million)
        self.max_output.setValue(settings.max_output_tokens)
        self.clear_preview()

    def clear_preview(self) -> None:
        self.preview.clear()
        self.preview_caption.setText('Nie wygenerowano propozycji.')
        self.apply_button.setEnabled(False)
        self.suggestions.clear()

    def display_result(self, segment_id: int, result: AIResult) -> None:
        self.preview_caption.setText(
            f'Segment ID {segment_id} · {result.model} · '
            f'{result.usage.input_tokens}/{result.usage.output_tokens} tokenów · '
            f'koszt szacowany: {result.estimated_cost_usd:.6f} USD'
            if result.estimated_cost_usd is not None else
            f'Segment ID {segment_id} · {result.model} · '
            f'{result.usage.input_tokens}/{result.usage.output_tokens} tokenów · koszt nieznany'
        )
        if result.qa_warnings:
            self.preview_caption.setText(
                self.preview_caption.text() + '\nQA: ' + '; '.join(result.qa_warnings)
            )
        self.preview.setPlainText(result.translation)
        self.apply_button.setEnabled(True)

    def show_batch(self, report: BatchReport) -> None:
        self.suggestions.clear()
        for item in report.results:
            kind = 'QA!' if item.result.qa_warnings else 'OK'
            self.suggestions.addItem(f'[{kind}] #{item.segment_id}: {item.original_source[:75]}')
        reasons = []
        if report.cancelled:
            reasons.append('anulowano')
        if report.budget_exhausted:
            reasons.append('osiągnięto limit szacowanego kosztu')
        self.progress_label.setText(
            f'Wyniki: {len(report.results)} · istniejące Target: {report.skipped_existing} · '
            f'błędy: {len(report.errors)} · wejście/wyjście: '
            f'{report.input_tokens}/{report.output_tokens} tokenów · '
            f'szacowany koszt {report.spent_usd:.6f} USD. ' + ', '.join(reasons)
        )

    def set_running(self, running: bool) -> None:
        self.batch_button.setEnabled(not running)
        self.single_button.setEnabled(not running)
        self.test_button.setEnabled(not running)
        self.save_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
