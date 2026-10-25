from PySide6.QtWidgets import QGroupBox, QListWidget, QVBoxLayout
from gamecat.qa.rules import QAIssue


class QAPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__('QA', parent)
        self.list_widget=QListWidget(); QVBoxLayout(self).addWidget(self.list_widget)
    def set_issues(self, issues: list[QAIssue]) -> None:
        self.list_widget.clear()
        for issue in issues: self.list_widget.addItem(f'{issue.code}: {issue.message}')
