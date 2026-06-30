"""
Background worker that renders the LaTeX preview off the UI thread.

Rendering can take 100-500ms depending on content; doing it on the UI
thread would cause visible stutter while the user types.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal


class PreviewWorkerSignals(QObject):
    # PNG bytes of the rendered preview, or empty bytes on failure.
    finished = Signal(bytes)


class PreviewWorker(QRunnable):
    """Render a markdown string to a preview PNG in a worker thread."""

    def __init__(self, markdown_text: str, width: int = 800, font_size: int = 13) -> None:
        super().__init__()
        self.markdown_text = markdown_text
        self.width = width
        self.font_size = font_size
        self.signals = PreviewWorkerSignals()

    def run(self) -> None:
        try:
            # Import here so the matplotlib Agg backend init happens in the
            # worker thread (avoids potential GUI-thread contention).
            from .latex_preview import render_preview
            png = render_preview(self.markdown_text, width=self.width,
                                 font_size=self.font_size)
            self.signals.finished.emit(png or b"")
        except Exception:
            # Log the traceback to stderr so rendering bugs are diagnosable,
            # then emit empty bytes so the UI shows "预览渲染失败".
            import traceback
            traceback.print_exc()
            self.signals.finished.emit(b"")
