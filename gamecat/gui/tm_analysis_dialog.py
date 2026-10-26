"""Okno analizy projektu względem TM (z wyborem trybu wykonania)."""
from __future__ import annotations

from concurrent.futures import Future

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from gamecat.models.project import Project
from gamecat.services.project_service import ProjectService
from gamecat.tm.analysis import MATCH_BANDS, ExecutionMode, TMAnalysisReport, default_workers

_MODE_LABELS = {
    ExecutionMode.PROCESSES: 'Procesy (ProcessPoolExecutor)',
    ExecutionMode.THREADS: 'Wątki (ThreadPoolExecutor)',
    ExecutionMode.SEQUENTIAL: 'Sekwencyjnie',
}


class TMAnalysisDialog(QDialog):
    """Uruchamia analizę w tle, pokazuje statystykę progów i pozwala wstawić 100%."""

    segments_changed = Signal()

    def __init__(self, service: ProjectService, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Analiza projektu względem TM')
        self.resize(520, 420)
        self._service = service
        self._project = project
        self._report: TMAnalysisReport | None = None

        self.mode_combo = QComboBox()
        for mode, label in _MODE_LABELS.items():
            self.mode_combo.addItem(label, mode)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 64)
        self.workers_spin.setValue(default_workers())
        self.run_button = QPushButton('Analizuj')
        self.run_button.clicked.connect(self.start_analysis)

        form = QFormLayout()
        form.addRow('Tryb wykonania:', self.mode_combo)
        form.addRow('Liczba wątków/procesów:', self.workers_spin)

        self.table = QTableWidget(len(MATCH_BANDS), 3)
        self.table.setHorizontalHeaderLabels(['Próg', 'Segmenty', 'Słowa'])
        self.table.verticalHeader().setVisible(False)
        self.summary_label = QLabel('Wybierz tryb i kliknij „Analizuj”.')
        self.summary_label.setWordWrap(True)

        self.pretranslate_spin = QSpinBox()
        self.pretranslate_spin.setRange(50, 100)
        self.pretranslate_spin.setSuffix('%')
        self.pretranslate_spin.setValue(100)
        self.pretranslate_spin.setToolTip(
            '100% to najbezpieczniejszy wybór. Niższe progi wstawiają propozycje '
            'wymagające ręcznej kontroli tłumacza.'
        )
        self.pretranslate_spin.valueChanged.connect(self._refresh_apply_button)
        self.apply_button = QPushButton('Wstaw dopasowania 100%')
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_exact_matches)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        actions = QHBoxLayout()
        actions.addWidget(self.run_button)
        actions.addWidget(QLabel('Pretranslacja od:'))
        actions.addWidget(self.pretranslate_spin)
        actions.addWidget(self.apply_button)
        actions.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(self.table)
        layout.addWidget(self.summary_label)
        layout.addWidget(buttons)

    def start_analysis(self) -> None:
        mode = self.mode_combo.currentData()
        self.run_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.summary_label.setText('Analiza w toku…')
        future = self._service.analyze_project_tm_async(
            self._project, mode=mode, workers=self.workers_spin.value(),
        )
        self._poll(future)

    def _poll(self, future: Future[TMAnalysisReport]) -> None:
        if not future.done():
            QTimer.singleShot(50, lambda: self._poll(future))
            return
        self.run_button.setEnabled(True)
        try:
            report = future.result()
        except Exception as exc:
            self.summary_label.setText('Analiza nie powiodła się.')
            QMessageBox.critical(self, 'GameCAT', f'Analiza TM nie powiodła się:\n{exc}')
            return
        self.show_report(report)

    def show_report(self, report: TMAnalysisReport) -> None:
        self._report = report
        for row, (label, _) in enumerate(MATCH_BANDS):
            self.table.setItem(row, 0, QTableWidgetItem(label))
            self.table.setItem(row, 1, QTableWidgetItem(str(report.band_segments[label])))
            self.table.setItem(row, 2, QTableWidgetItem(str(report.band_words[label])))
        self.summary_label.setText(
            f'{report.segment_count} segmentów ({report.total_words} słów) porównano z '
            f'{report.tm_size} wpisami TM. Tryb: {_MODE_LABELS[report.mode]}, '
            f'workerów: {report.workers}, czas: {report.elapsed:.2f} s.'
        )
        self._refresh_apply_button()

    def _refresh_apply_button(self) -> None:
        if self._report is None:
            self.apply_button.setEnabled(False)
            return
        threshold = self.pretranslate_spin.value() / 100
        eligible = sum(1 for item in self._report.matches
                       if item.score >= threshold and item.tm_target and item.tm_source)
        self.apply_button.setText(
            f'Wstaw dopasowania ≥{self.pretranslate_spin.value()}% ({eligible})'
        )
        self.apply_button.setEnabled(eligible > 0)

    def apply_exact_matches(self) -> None:
        """Apply selected TM suggestions only to empty targets."""
        if self._report is None or not self.apply_button.isEnabled():
            return
        threshold = self.pretranslate_spin.value() / 100
        if threshold < 1.0:
            answer = QMessageBox.question(
                self, 'GameCAT — fuzzy pretranslacja',
                'Dopasowania poniżej 100% mogą być niepoprawne lub zawierać '
                'niezgodne placeholdery. Każdy wstawiony tekst wymaga weryfikacji '
                'i kontroli QA. Kontynuować?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            count = self._service.apply_tm_matches(
                self._project, self._report, minimum_score=threshold
            )
        except Exception as exc:
            QMessageBox.critical(self, 'GameCAT', f'Pretranslacja nie powiodła się:\n{exc}')
            return
        self.apply_button.setEnabled(False)
        QMessageBox.information(
            self, 'GameCAT',
            f'Wstawiono {count} tłumaczeń do pustych segmentów. '
            'Zalecane: uruchom QA całego projektu.'
        )
        self.segments_changed.emit()
