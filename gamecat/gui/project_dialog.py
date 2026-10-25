from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit
from gamecat.models.project import Project


class ProjectDialog(QDialog):
    """Collect metadata for a new translation project."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Nowy projekt')
        self.name_edit = QLineEdit()
        self.source_edit = QLineEdit('en')
        self.target_edit = QLineEdit('pl')
        self.format_combo = QComboBox(); self.format_combo.addItems(['txt','csv','json'])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout = QFormLayout(self)
        layout.addRow('Nazwa:', self.name_edit)
        layout.addRow('Język źródłowy:', self.source_edit)
        layout.addRow('Język docelowy:', self.target_edit)
        layout.addRow('Format:', self.format_combo)
        layout.addRow(buttons)

    def project(self) -> Project:
        return Project(self.name_edit.text().strip(), self.source_edit.text().strip(), self.target_edit.text().strip(), self.format_combo.currentText())
