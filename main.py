"""
TextLens desktop app entry point.

Run with:
    python main.py

Or, after PyInstaller packaging, double-click TextLens.exe.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def main() -> int:
    # High-DPI support (PySide6 enables this by default on Qt 6, but explicit
    # is better than implicit).
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.HighDpiScaleFactorRoundingPolicy
        .PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("TextLens")
    app.setApplicationDisplayName("TextLens - 图文识别")
    app.setOrganizationName("TextLens")

    # Dark mode palette adjustments: keep default light theme for clarity
    # but ensure toolbar text shows up correctly on Windows.

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
