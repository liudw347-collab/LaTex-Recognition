"""
TextLens desktop app entry point.

Run with:
    python main.py

Or, after PyInstaller packaging, double-click TextLens.exe.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def main() -> int:
    # High-DPI: Qt 6 enables scaling by default. Set the rounding policy
    # to PassThrough for sharpest rendering on fractional-DPI displays.
    # Must be called BEFORE creating QApplication.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("TextLens")
    app.setApplicationDisplayName("TextLens - 图文识别")
    app.setOrganizationName("TextLens")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
