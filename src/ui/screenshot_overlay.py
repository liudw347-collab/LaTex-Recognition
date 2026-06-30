"""
Fullscreen overlay for selecting a screen region to capture.

When opened, the user clicks and drags to draw a rectangle. Releasing the
mouse closes the dialog and stores the selected rectangle (in virtual
desktop coordinates) in `selected_rect`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QScreen
from PySide6.QtWidgets import QDialog


class ScreenshotOverlay(QDialog):
    """A transparent fullscreen overlay covering all screens for region
    selection. Click-drag to select; Esc to cancel."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Cover the entire virtual desktop
        virt = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(virt)

        self._start = QPoint()
        self._end = QPoint()
        self.selected_rect: QRect | None = None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        # Dim the whole screen
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        # If a selection exists, clear it and draw its border
        if not self._start.isNull() and not self._end.isNull():
            r = QRect(self._start, self._end).normalized()
            # Clear the selection rectangle (make it fully transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(r, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            # Draw border
            pen = QPen(QColor(16, 185, 129), 2)
            painter.setPen(pen)
            painter.setBrush(QBrush(Qt.GlobalColor.transparent))
            painter.drawRect(r)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position().toPoint()
            self._end = self._start
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._end = event.position().toPoint()
            r = QRect(self._start, self._end).normalized()
            if r.width() > 4 and r.height() > 4:
                # Map widget-local coords to global desktop coords
                self.selected_rect = QRect(
                    self.mapToGlobal(r.topLeft()),
                    self.mapToGlobal(r.bottomRight()),
                )
            self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
