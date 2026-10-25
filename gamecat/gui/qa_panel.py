from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGroupBox, QListWidget, QListWidgetItem, QTabWidget, QVBoxLayout, QWidget

from gamecat.qa.project_scan import ProjectQAReport
from gamecat.qa.rules import QAIssue


class QAPanel(QGroupBox):
    """Shows live QA for the current segment and persistent full-project scan results."""

    segment_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__('QA', parent)
        self.tabs = QTabWidget(self)
        self.current_list = QListWidget()
        self.project_list = QListWidget()
        self.project_list.itemDoubleClicked.connect(self._request_segment)

        current_page = QWidget()
        current_layout = QVBoxLayout(current_page)
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.addWidget(self.current_list)

        project_page = QWidget()
        project_layout = QVBoxLayout(project_page)
        project_layout.setContentsMargins(0, 0, 0, 0)
        project_layout.addWidget(self.project_list)

        self.tabs.addTab(current_page, 'Bieżący (0)')
        self.tabs.addTab(project_page, 'Projekt (0)')
        QVBoxLayout(self).addWidget(self.tabs)

        # Compatibility alias used by the original smoke test.
        self.list_widget = self.current_list

    def set_issues(self, issues: list[QAIssue]) -> None:
        self.current_list.clear()
        for issue in issues:
            self.current_list.addItem(f'{issue.code}: {issue.message}')
        self.tabs.setTabText(0, f'Bieżący ({len(issues)})')
        self.setTitle(f'QA ({len(issues)})')

    def set_project_report(self, report: ProjectQAReport) -> None:
        self.project_list.clear()
        for result in report.results:
            for issue in result.issues:
                key = f' [{result.segment.key}]' if result.segment.key else ''
                item = QListWidgetItem(
                    f'#{result.segment.position}{key} — {issue.code}: {issue.message}'
                )
                if result.segment.id is not None:
                    item.setData(Qt.ItemDataRole.UserRole, result.segment.id)
                self.project_list.addItem(item)
        self.tabs.setTabText(1, f'Projekt ({report.issue_count})')
        self.tabs.setCurrentIndex(1)

    def clear_project_report(self) -> None:
        self.project_list.clear()
        self.tabs.setTabText(1, 'Projekt (0)')

    def _request_segment(self, item: QListWidgetItem) -> None:
        segment_id = item.data(Qt.ItemDataRole.UserRole)
        if segment_id is not None:
            self.segment_requested.emit(int(segment_id))
