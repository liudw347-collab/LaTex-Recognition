"""
Qt worker thread that runs the recognition request off the UI thread.

Emits progress, success, and failure signals that the main window connects to.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from .config import Settings
from .recognizer import recognize_image


class RecognizeWorkerSignals(QObject):
    progress = Signal(str)
    success = Signal(str, int, int)   # text, elapsed_ms, attempts
    failed = Signal(str)              # error message


class RecognizeWorker(QRunnable):
    """Run recognize_image() in a thread pool worker."""

    def __init__(self, image_data_url: str, settings: Settings) -> None:
        super().__init__()
        self.image_data_url = image_data_url
        self.settings = settings
        self.signals = RecognizeWorkerSignals()

    def run(self) -> None:
        result = recognize_image(
            self.image_data_url,
            self.settings,
            progress_cb=self.signals.progress.emit,
        )
        if result.success:
            self.signals.success.emit(result.text, result.elapsed_ms, result.attempts)
        else:
            self.signals.failed.emit(result.error)
