import multiprocessing
import sys

from PySide6.QtWidgets import QApplication

from gamecat.gui.main_window import MainWindow
from gamecat.logging_config import configure_logging


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    window = MainWindow(); window.show()
    return app.exec()


if __name__ == '__main__':
    # Wymagane przy budowie .exe (PyInstaller) – procesy potomne analizy TM
    # uruchamiają ponownie ten plik i nie mogą otworzyć kolejnego okna.
    multiprocessing.freeze_support()
    raise SystemExit(main())
