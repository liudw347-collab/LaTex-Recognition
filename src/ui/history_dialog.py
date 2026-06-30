"""
History viewer dialog. Shows a list of past recognition results on the
left, with a preview of the selected item's text on the right. Users can
copy, delete, or clear the history.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QMessageBox,
)

from ..core.history import HistoryItem


class HistoryDialog(QDialog):
    """Modal dialog for browsing past recognition results."""

    def __init__(self, items: list[HistoryItem], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("识别历史")
        self.resize(900, 600)
        self._items = items
        self._deleted: set[str] = set()
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        title = QLabel(f"共 {len(self._items)} 条历史记录")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        self._title_label = title
        root.addWidget(title)

        body = QHBoxLayout()

        # --- Left: list ---
        left = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(64, 64))
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        left.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        self.copy_btn = QPushButton("复制选中")
        self.copy_btn.clicked.connect(self._copy_selected)
        self.delete_btn = QPushButton("删除选中")
        self.delete_btn.clicked.connect(self._delete_selected)
        self.clear_btn = QPushButton("清空全部")
        self.clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addWidget(self.clear_btn)
        left.addLayout(btn_row)

        body.addLayout(left, 1)

        # --- Right: preview ---
        right = QVBoxLayout()
        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFixedHeight(180)
        self.thumb_label.setStyleSheet(
            "background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px;"
        )
        right.addWidget(self.thumb_label)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        right.addWidget(self.preview, 1)

        meta_row = QHBoxLayout()
        self.meta_label = QLabel("")
        self.meta_label.setStyleSheet("color: #6b7280; font-size: 10pt;")
        meta_row.addWidget(self.meta_label)
        meta_row.addStretch()
        right.addLayout(meta_row)

        body.addLayout(right, 2)
        root.addLayout(body, 1)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _populate(self) -> None:
        self.list_widget.clear()
        for item in self._items:
            if item.id in self._deleted:
                continue
            list_item = QListWidgetItem()
            list_item.setText(f"{item.id}  [{item.model}]")
            list_item.setData(Qt.ItemDataRole.UserRole, item.id)
            # Set thumbnail icon (safely handle corrupt data)
            thumb_bytes = self._safe_data_url_to_bytes(item.thumbnail)
            pm = QPixmap()
            if thumb_bytes:
                pm.loadFromData(thumb_bytes)
            if not pm.isNull():
                list_item.setIcon(pm.scaled(
                    56, 56,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            self.list_widget.addItem(list_item)
        self._title_label.setText(
            f"共 {len(self._items) - len(self._deleted)} 条历史记录"
        )

    @staticmethod
    def _safe_data_url_to_bytes(data_url: str) -> bytes:
        """Convert a data URL to raw bytes, returning b"" on any error."""
        try:
            from ..core.image_utils import data_url_to_bytes
            _, raw = data_url_to_bytes(data_url)
            return raw
        except Exception:
            return b""

    def _on_row_changed(self, row: int) -> None:
        if row < 0 or row >= self.list_widget.count():
            return
        item = self.list_widget.item(row)
        item_id = item.data(Qt.ItemDataRole.UserRole)
        for h in self._items:
            if h.id == item_id:
                self.preview.setPlainText(h.text or "")
                self.meta_label.setText(
                    f"模型：{h.model or '?'}    用时：{h.elapsed_ms} ms    "
                    f"尝试次数：{h.attempts}"
                )
                thumb_bytes = self._safe_data_url_to_bytes(h.thumbnail)
                pm = QPixmap()
                if thumb_bytes:
                    pm.loadFromData(thumb_bytes)
                if not pm.isNull():
                    self.thumb_label.setPixmap(
                        pm.scaled(
                            self.thumb_label.size(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                break

    def _selected_item(self) -> HistoryItem | None:
        row = self.list_widget.currentRow()
        if row < 0:
            return None
        item = self.list_widget.item(row)
        item_id = item.data(Qt.ItemDataRole.UserRole)
        for h in self._items:
            if h.id == item_id:
                return h
        return None

    def _copy_selected(self) -> None:
        item = self._selected_item()
        if not item:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(item.text)

    def _delete_selected(self) -> None:
        item = self._selected_item()
        if not item:
            return
        self._deleted.add(item.id)
        self._populate()

    def _clear_all(self) -> None:
        if not self._items:
            return
        confirm = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有历史记录吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for item in self._items:
            self._deleted.add(item.id)
        self._populate()

    def get_active_items(self) -> list[HistoryItem]:
        """Return items NOT marked as deleted (caller re-saves)."""
        return [i for i in self._items if i.id not in self._deleted]
