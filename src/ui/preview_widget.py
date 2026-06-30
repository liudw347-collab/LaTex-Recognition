"""
LaTeX preview widget.

A QTabWidget with two tabs:
  - 编辑: a QPlainTextEdit where the user edits the recognized text
  - 预览: a scrollable QLabel showing the rendered LaTeX preview PNG

The preview is re-rendered automatically (debounced 400ms) whenever the
text changes. Rendering runs in a background QThreadPool worker so the
UI stays responsive even for large documents.

Usage:
    widget = LatexPreviewWidget(parent)
    widget.set_text("...recognized text...")
    text = widget.get_text()
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.preview_worker import PreviewWorker


class LatexPreviewWidget(QTabWidget):
    """Tab widget with editable text and live LaTeX preview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.thread_pool = QThreadPool.globalInstance()
        self._current_worker: PreviewWorker | None = None
        # Monotonic generation counter: only the most-recently-launched
        # worker's result is applied. Stale results are discarded.
        self._preview_generation: int = 0

        # --- Edit tab ---
        self.edit_tab = QWidget()
        edit_layout = QVBoxLayout(self.edit_tab)
        edit_layout.setContentsMargins(0, 0, 0, 0)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(
            "识别结果将显示在此处。你可以在此编辑后再复制。\n\n"
            "支持 Markdown 语法和 LaTeX 公式：\n"
            "  行内公式：$E=mc^2$\n"
            "  独立行公式：$$\\int_0^1 x^2 dx$$"
        )
        self.text_edit.setStyleSheet(
            "QPlainTextEdit { background: #ffffff; border: 0;"
            " padding: 8px; font-size: 11pt; font-family: 'Consolas', 'Menlo', monospace; }"
        )
        edit_layout.addWidget(self.text_edit)

        # --- Preview tab ---
        self.preview_tab = QWidget()
        preview_layout = QVBoxLayout(self.preview_tab)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area so long previews can be scrolled
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: #ffffff; border: 0; }"
        )

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.preview_label.setStyleSheet("background: #ffffff; padding: 12px;")
        self.preview_label.setText(
            '<div style="color: #9ca3af; padding: 40px; font-size: 11pt;">'
            '预览将显示在此处。在「编辑」标签页中输入或修改文本后，'
            '切换到此标签页查看 LaTeX 公式渲染效果。'
            '</div>'
        )
        self.scroll_area.setWidget(self.preview_label)
        preview_layout.addWidget(self.scroll_area)

        # Add tabs
        self.addTab(self.edit_tab, "📝 编辑")
        self.addTab(self.preview_tab, "👁 预览")

        # --- Debounce timer ---
        # Re-render preview 400ms after the last keystroke to avoid
        # rendering on every character (which would be laggy).
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(400)
        self._debounce_timer.timeout.connect(self._trigger_preview)

        # Connect text changes to debounce
        self.text_edit.textChanged.connect(self._on_text_changed)

        # Re-render preview when switching to preview tab
        self.currentChanged.connect(self._on_tab_changed)

    # ------------------------------------------------------------ public

    def set_text(self, text: str) -> None:
        """Replace the editor contents. Triggers a preview re-render."""
        # Stop any pending debounce from prior user typing so it doesn't
        # fire after we set the new text and trigger an extra render.
        self._debounce_timer.stop()
        # Block signals to avoid double-debounce while setting text
        self.text_edit.blockSignals(True)
        self.text_edit.setPlainText(text)
        self.text_edit.blockSignals(False)
        # Trigger an immediate preview render
        self._trigger_preview()

    def get_text(self) -> str:
        """Return the current editor text."""
        return self.text_edit.toPlainText()

    def clear(self) -> None:
        # Invalidate any in-flight preview worker so its result doesn't
        # appear on the just-cleared label, and stop the debounce timer
        # so a pending trigger doesn't fire after the clear.
        self.invalidate()
        self._debounce_timer.stop()
        self.text_edit.blockSignals(True)
        self.text_edit.clear()
        self.text_edit.blockSignals(False)
        self.preview_label.clear()
        self.preview_label.setText(
            '<div style="color: #9ca3af; padding: 40px; font-size: 11pt;">'
            '预览将显示在此处。'
            '</div>'
        )

    def invalidate(self) -> None:
        """Discard any in-flight preview render by bumping the generation
        counter. Called by the parent window's closeEvent to prevent
        late-arriving signals from hitting a destroyed label."""
        self._preview_generation += 1

    # ---------------------------------------------------------- handlers

    def _on_text_changed(self) -> None:
        # Restart the debounce timer on every keystroke
        self._debounce_timer.start()

    def _on_tab_changed(self, index: int) -> None:
        # When user switches to the preview tab, render immediately if stale
        if index == 1:  # preview tab
            self._trigger_preview()

    def _trigger_preview(self) -> None:
        text = self.text_edit.toPlainText()
        if not text.strip():
            self.preview_label.clear()
            self.preview_label.setText(
                '<div style="color: #9ca3af; padding: 40px; font-size: 11pt;">'
                '（无内容）'
                '</div>'
            )
            return

        # Increment the generation counter so any in-flight worker's
        # result will be discarded as stale when it arrives.
        self._preview_generation += 1
        generation = self._preview_generation

        # Use the current preview area width as the render width.
        render_width = max(self.scroll_area.width() - 24, 400)

        worker = PreviewWorker(text, width=render_width, font_size=13)
        # Capture the generation in the lambda so the slot can check
        # whether it's still the latest.
        worker.signals.finished.connect(
            lambda data, gen=generation: self._on_preview_ready(data, gen)
        )
        self._current_worker = worker
        self.thread_pool.start(worker)

    def _on_preview_ready(self, png_bytes: bytes, generation: int) -> None:
        # Discard stale results from older workers.
        if generation != self._preview_generation:
            return

        if not png_bytes:
            self.preview_label.setText(
                '<div style="color: #b91c1c; padding: 40px; font-size: 11pt;">'
                '预览渲染失败。请检查公式语法是否正确。'
                '</div>'
            )
            return

        qimg = QImage()
        if not qimg.loadFromData(png_bytes, "PNG"):
            self.preview_label.setText(
                '<div style="color: #b91c1c; padding: 40px; font-size: 11pt;">'
                '预览图像解析失败。'
                '</div>'
            )
            return

        qpm = QPixmap.fromImage(qimg)
        # Scale down if wider than the scroll area, preserving aspect ratio
        avail_w = max(self.scroll_area.width() - 24, 100)
        if qpm.width() > avail_w:
            qpm = qpm.scaledToWidth(
                avail_w,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.preview_label.setPixmap(qpm)
