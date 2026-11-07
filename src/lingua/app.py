from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication


def main() -> int:
    from lingua.ui import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("Lingua")
    app.setApplicationName("Lingua")
    window = MainWindow()
    window.show()
    return app.exec()
