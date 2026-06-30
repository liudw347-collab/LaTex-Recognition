"""
Main window for TextLens desktop app.

Layout (single window, 3-pane vertically):
  - Top:    Toolbar with file/upload/screenshot/settings/history buttons
  - Middle: Image preview (left) + recognition result / editor (right)
  - Bottom: Status bar with progress + copy-format selector + copy button
"""

from __future__ import annotations

import io
import time
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QThreadPool, QTimer, QSize
from PySide6.QtGui import (
    QAction,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..core.config import Settings, load_settings, save_settings
from ..core.formats import FORMAT_LABELS, transform
from ..core.history import (
    HistoryItem,
    add_history_item,
    load_history,
    make_thumbnail,
    save_history,
)
from ..core.image_utils import (
    compress_image,
    bytes_to_data_url,
    load_image_file,
)
from ..core.worker import RecognizeWorker
from .preview_widget import LatexPreviewWidget
from .settings_dialog import SettingsDialog
from .history_dialog import HistoryDialog


STYLE_QSS = """
QMainWindow, QDialog { background: #fafaf9; }
QToolBar { background: #ffffff; border: 0; border-bottom: 1px solid #e5e7eb; spacing: 4px; padding: 4px; }
QToolButton { padding: 6px 12px; border-radius: 6px; color: #374151; }
QToolButton:hover { background: #f3f4f6; }
QToolButton:pressed { background: #e5e7eb; }
QPushButton {
    background: #10b981; color: white; border: 0;
    padding: 6px 16px; border-radius: 6px; font-weight: 500;
}
QPushButton:hover { background: #059669; }
QPushButton:pressed { background: #047857; }
QPushButton:disabled { background: #d1d5db; color: #9ca3af; }
QPushButton[secondary="true"] { background: #ffffff; color: #374151; border: 1px solid #d1d5db; }
QPushButton[secondary="true"]:hover { background: #f3f4f6; }
QFrame#dropZone {
    background: #ffffff;
    border: 2px dashed #d6d3d1;
    border-radius: 12px;
}
QFrame#dropZone[dragging="true"] {
    border-color: #10b981;
    background: #ecfdf5;
}
QLabel#heroTitle { font-size: 22pt; font-weight: 700; color: #059669; }
QLabel#heroSub   { font-size: 11pt; color: #6b7280; }
QStatusBar { background: #ffffff; border-top: 1px solid #e5e7eb; }
QStatusBar QLabel { color: #4b5563; }
QComboBox, QSpinBox { padding: 4px 8px; border: 1px solid #d1d5db; border-radius: 6px; background: white; }
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TextLens - 图文识别")
        self.resize(1200, 800)

        self.settings: Settings = load_settings()
        self.history: list[HistoryItem] = load_history()
        self.thread_pool = QThreadPool.globalInstance()
        self._current_worker = None

        # Current image state
        self._pil_image: Image.Image | None = None
        self._image_data_url: str | None = None
        self._recognized_text: str = ""
        self._is_recognizing: bool = False

        self._build_ui()
        self._apply_style()
        self._restore_window_state()

        # Global paste handler
        self._install_paste_filter()

        # Screenshot hotkey
        self._setup_screenshot_hotkey()

        # If first run and no API key, prompt user
        if not self.settings.api_key:
            QTimer.singleShot(200, self._prompt_first_run_setup)

    # ------------------------------------------------------------ UI build

    def _build_ui(self) -> None:
        # --- Toolbar ---
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        self.action_open = QAction("📂 打开图片", self)
        self.action_open.setShortcut(QKeySequence("Ctrl+O"))
        self.action_open.triggered.connect(self._on_open_file)
        toolbar.addAction(self.action_open)

        self.action_paste = QAction("📋 粘贴图片", self)
        self.action_paste.setShortcut(QKeySequence("Ctrl+V"))
        self.action_paste.triggered.connect(self._on_paste)
        toolbar.addAction(self.action_paste)

        self.action_screenshot = QAction("📷 屏幕截图", self)
        self.action_screenshot.setShortcut(
            QKeySequence(self.settings.screenshot_hotkey)
        )
        self.action_screenshot.triggered.connect(self._on_screenshot)
        toolbar.addAction(self.action_screenshot)

        toolbar.addSeparator()

        self.action_recognize = QAction("✨ 开始识别", self)
        self.action_recognize.setShortcut(QKeySequence("Ctrl+R"))
        self.action_recognize.triggered.connect(self._on_recognize)
        toolbar.addAction(self.action_recognize)

        toolbar.addSeparator()

        self.action_history = QAction("🕓 历史记录", self)
        self.action_history.triggered.connect(self._on_open_history)
        toolbar.addAction(self.action_history)

        self.action_settings = QAction("⚙️ 设置", self)
        self.action_settings.triggered.connect(self._on_open_settings)
        toolbar.addAction(self.action_settings)

        toolbar.addSeparator()
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().Policy.Expanding,
                              spacer.sizePolicy().Policy.Preferred)
        toolbar.addWidget(spacer)

        # Title in toolbar right
        title_label = QLabel("  TextLens  ")
        title_label.setStyleSheet(
            "font-size: 13pt; font-weight: 700;"
            " color: #059669; padding-right: 12px;"
        )
        toolbar.addWidget(title_label)

        # --- Central area: 3-pane ---
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Hero (shown when no image)
        self.hero_frame = QFrame()
        hero_layout = QVBoxLayout(self.hero_frame)
        hero_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_title = QLabel("图片文字与公式识别")
        hero_title.setObjectName("heroTitle")
        hero_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_sub = QLabel(
            "粘贴 / 拖拽 / 上传图片，AI 自动识别文字与数学公式\n"
            "支持 Ctrl+V 粘贴截图 · 拖拽上传 · 点击下方区域选择文件"
        )
        hero_sub.setObjectName("heroSub")
        hero_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_sub)

        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("dropZone")
        drop_layout = QVBoxLayout(self.drop_zone)
        drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_hint = QLabel("点击此处选择图片，或拖拽图片到此区域\n\n支持 PNG / JPG / WebP / GIF / BMP")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_hint.setStyleSheet("color: #6b7280; font-size: 11pt;")
        drop_layout.addWidget(drop_hint)
        # Click on drop zone opens file dialog
        self.drop_zone.mousePressEvent = lambda _e: self._on_open_file()

        # Image preview pane
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet(
            "background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px;"
        )
        self.image_label.setMinimumSize(400, 300)
        self.image_label.hide()

        # Result editor + LaTeX preview (tabbed: 编辑 / 预览)
        self.result_edit = LatexPreviewWidget()
        self.result_edit.setStyleSheet(
            "QTabWidget::pane { background: #ffffff; border: 1px solid #e5e7eb;"
            " border-radius: 8px; }"
            "QTabBar::tab { background: #f9fafb; padding: 6px 14px;"
            " border: 1px solid #e5e7eb; border-bottom: none;"
            " border-top-left-radius: 6px; border-top-right-radius: 6px;"
            " margin-right: 2px; font-size: 10pt; }"
            "QTabBar::tab:selected { background: #ffffff;"
            " border-color: #10b981 #10b981 #ffffff #10b981;"
            " color: #059669; font-weight: 600; }"
            "QTabBar::tab:!selected { color: #6b7280; }"
        )
        # Wire text changes from the inner text_edit to our handler
        self.result_edit.text_edit.textChanged.connect(self._on_result_edited)

        # Splitter: image | result
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.image_label)
        self.splitter.addWidget(self.result_edit)
        self.splitter.setSizes([500, 700])
        self.splitter.hide()

        # Stacked: hero or (drop_zone when no image yet), then splitter
        self.stack = QFrame()
        stack_layout = QVBoxLayout(self.stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.addWidget(self.hero_frame)
        stack_layout.addWidget(self.drop_zone)
        stack_layout.addWidget(self.splitter)
        # Initially show hero + drop zone
        self.splitter.hide()

        root.addWidget(self.stack, 1)

        # --- Bottom action bar ---
        bottom = QHBoxLayout()

        self.format_combo = QComboBox()
        for fid, label in FORMAT_LABELS.items():
            self.format_combo.addItem(label, fid)
        idx = self.format_combo.findData(self.settings.default_copy_format)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)
        bottom.addWidget(QLabel("复制格式："))
        bottom.addWidget(self.format_combo)

        bottom.addStretch()

        self.clear_btn = QPushButton("清空", self)
        self.clear_btn.setProperty("secondary", True)
        self.clear_btn.clicked.connect(self._on_clear)
        bottom.addWidget(self.clear_btn)

        self.re_recognize_btn = QPushButton("重新识别", self)
        self.re_recognize_btn.setProperty("secondary", True)
        self.re_recognize_btn.clicked.connect(self._on_recognize)
        bottom.addWidget(self.re_recognize_btn)

        self.copy_btn = QPushButton("复制结果", self)
        self.copy_btn.clicked.connect(self._on_copy)
        bottom.addWidget(self.copy_btn)

        root.addLayout(bottom)

        self.setCentralWidget(central)

        # --- Status bar ---
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_progress = QLabel("就绪")
        sb.addWidget(self.status_progress, 1)
        self.status_model = QLabel(f"模型：{self.settings.model or '未配置'}")
        sb.addPermanentWidget(self.status_model)

        # Enable drag/drop on the whole window
        self.setAcceptDrops(True)

    def _apply_style(self) -> None:
        self.setStyleSheet(STYLE_QSS)

    def _restore_window_state(self) -> None:
        if self.settings.window_geometry:
            self.restoreGeometry(bytes.fromhex(self.settings.window_geometry))
        if self.settings.window_state:
            self.restoreState(bytes.fromhex(self.settings.window_state))

    # ------------------------------------------------------- paste handler

    def _install_paste_filter(self) -> None:
        # Use a global shortcut to catch Ctrl+V even when focus is in result_edit
        paste_shortcut = QShortcut(QKeySequence("Ctrl+V"), self)
        paste_shortcut.activated.connect(self._on_paste)
        # Also let the result_edit handle Ctrl+V natively when it has focus:
        # by connecting only at window level and checking focus, we can avoid
        # hijacking text editing. We delegate to native paste if a text field
        # has focus.
        # Reconnect with custom handler:
        paste_shortcut.activated.disconnect()
        paste_shortcut.activated.connect(self._on_paste_smart)

    def _on_paste_smart(self) -> None:
        # If a text widget has focus and clipboard has no image, let it paste text.
        focus = QApplication.focusWidget()
        clipboard = QGuiApplication.clipboard()
        mime = clipboard.mimeData()
        inner_edit = getattr(self.result_edit, "text_edit", None)
        if focus is inner_edit and not (mime and mime.hasImage()):
            # Allow native text paste into the inner QPlainTextEdit
            inner_edit.paste()
            return
        self._on_paste()

    # ----------------------------------------------------- screenshot hotkey

    def _setup_screenshot_hotkey(self) -> None:
        try:
            sc = QShortcut(QKeySequence(self.settings.screenshot_hotkey), self)
            sc.activated.connect(self._on_screenshot)
        except Exception:
            pass  # invalid sequence — skip silently

    # ------------------------------------------------------- first-run UX

    def _prompt_first_run_setup(self) -> None:
        ret = QMessageBox.question(
            self,
            "欢迎使用 TextLens",
            "检测到尚未配置 API Key。\n\n是否现在打开设置对话框，绑定你自己的模型和 API Key？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            self._on_open_settings()

    # ------------------------------------------------------- file handlers

    def _on_open_file(self) -> None:
        last_dir = self.settings.last_open_dir or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            last_dir,
            "图片文件 (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.tiff);;所有文件 (*)",
        )
        if not path:
            return
        self.settings.last_open_dir = str(Path(path).parent)
        save_settings(self.settings)
        try:
            self._load_image_from_path(path)
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法加载图片：\n{e}")

    def _load_image_from_path(self, path: str) -> None:
        _, _, img = load_image_file(path)
        self._set_image(img)

    def _on_paste(self) -> None:
        clipboard = QGuiApplication.clipboard()
        mime = clipboard.mimeData()
        if mime is None or not mime.hasImage():
            self.status_progress.setText("剪贴板没有图片")
            return
        qimg = clipboard.image()
        if qimg.isNull():
            return
        # Convert QImage → PIL Image
        from PySide6.QtGui import QImage
        # Get raw bytes in RGBA8888 format
        rgba = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
        ptr = rgba.constBits()
        ptr.setsize(rgba.sizeInBytes())
        data = bytes(ptr)
        img = Image.frombytes("RGBA", (rgba.width(), rgba.height()), data)
        self._set_image(img)

    def _on_screenshot(self) -> None:
        """Use mss (cross-platform) if available; otherwise pick the screen
        and let the user select a region via a simple fullscreen overlay."""
        try:
            import mss
            import mss.tools
        except ImportError:
            QMessageBox.information(
                self,
                "缺少依赖",
                "屏幕截图功能需要 mss 库。\n请运行：pip install mss",
            )
            return

        # Minimize self so we don't appear in the shot
        was_visible = self.isVisible()
        self.hide()
        QApplication.processEvents()
        time.sleep(0.15)

        try:
            from .screenshot_overlay import ScreenshotOverlay
            overlay = ScreenshotOverlay()
            overlay.exec()
            rect = overlay.selected_rect
        finally:
            if was_visible:
                self.show()

        if rect is None:
            return

        with mss.mss() as sct:
            monitor = {
                "top": int(rect.y()),
                "left": int(rect.x()),
                "width": int(rect.width()),
                "height": int(rect.height()),
            }
            shot = sct.grab(monitor)
            from PIL import Image as PILImage
            img = PILImage.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        self._set_image(img)

    # ----------------------------------------------------- set image / run

    def _set_image(self, img: Image.Image) -> None:
        self._pil_image = img
        # Compress and prepare data URL
        png_bytes, _ = compress_image(
            img,
            max_width=self.settings.image_max_width,
            quality=self.settings.image_quality,
        )
        self._image_data_url = bytes_to_data_url(png_bytes, "image/png")

        # Show preview
        qpm = self._pil_to_qpixmap(img)
        self.image_label.setPixmap(
            qpm.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        # Switch UI: hide hero + drop zone, show splitter
        self.hero_frame.hide()
        self.drop_zone.hide()
        self.splitter.show()

        self.result_edit.clear()
        self._recognized_text = ""

        if self.settings.auto_recognize:
            QTimer.singleShot(50, self._on_recognize)

    @staticmethod
    def _pil_to_qpixmap(img: Image.Image) -> QPixmap:
        from PySide6.QtGui import QImage
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height,
                       QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimg)

    # ------------------------------------------------------- recognition

    def _on_recognize(self) -> None:
        if self._is_recognizing:
            return
        if not self._image_data_url:
            QMessageBox.information(self, "无图片", "请先选择或粘贴一张图片。")
            return
        if not self.settings.api_key or not self.settings.base_url:
            ret = QMessageBox.question(
                self,
                "未配置 API",
                "尚未配置 API Key / Base URL。是否现在打开设置？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret == QMessageBox.StandardButton.Yes:
                self._on_open_settings()
            return

        self._is_recognizing = True
        self.status_progress.setText("识别中...")
        self.result_edit.clear()
        self.copy_btn.setEnabled(False)
        self.re_recognize_btn.setEnabled(False)
        self.action_recognize.setEnabled(False)
        # Switch to the edit tab during recognition so user sees progress
        self.result_edit.setCurrentIndex(0)

        worker = RecognizeWorker(self._image_data_url, self.settings)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.success.connect(self._on_success)
        worker.signals.failed.connect(self._on_failed)
        self._current_worker = worker
        self.thread_pool.start(worker)

    def _on_progress(self, msg: str) -> None:
        self.status_progress.setText(msg)

    def _on_success(self, text: str, elapsed_ms: int, attempts: int) -> None:
        self._is_recognizing = False
        self._recognized_text = text
        self.result_edit.set_text(text)
        self.copy_btn.setEnabled(True)
        self.re_recognize_btn.setEnabled(True)
        self.action_recognize.setEnabled(True)
        self.status_progress.setText(
            f"识别完成（{elapsed_ms} ms，{attempts} 次尝试）"
        )

        # Add to history
        if self.settings.history_enabled and self._pil_image is not None:
            thumb = make_thumbnail(self._pil_image)
            self.history = add_history_item(
                self.history,
                text=text,
                model=self.settings.model,
                thumbnail=thumb,
                elapsed_ms=elapsed_ms,
                attempts=attempts,
                max_items=self.settings.history_max_items,
            )
            save_history(self.history, max_items=self.settings.history_max_items)

    def _on_failed(self, error: str) -> None:
        self._is_recognizing = False
        self.copy_btn.setEnabled(False)
        self.re_recognize_btn.setEnabled(True)
        self.action_recognize.setEnabled(True)
        self.status_progress.setText("识别失败")
        QMessageBox.critical(self, "识别失败", error)

    def _on_result_edited(self) -> None:
        self._recognized_text = self.result_edit.get_text()

    # ------------------------------------------------------- copy

    def _on_copy(self) -> None:
        text = self.result_edit.get_text()
        if not text:
            return
        fmt = self.format_combo.currentData()
        out = transform(text, fmt)
        clipboard = QGuiApplication.clipboard()
        if fmt == "word":
            # Provide both HTML and plain text so Word can pick the rich version
            from PySide6.QtCore import QMimeData
            mime = QMimeData()
            mime.setHtml(out)
            mime.setText(text)
            clipboard.setMimeData(mime)
        else:
            clipboard.setText(out)
        self.status_progress.setText(f"已复制（{FORMAT_LABELS[fmt]}）")

    # ------------------------------------------------------- misc handlers

    def _on_clear(self) -> None:
        self._pil_image = None
        self._image_data_url = None
        self._recognized_text = ""
        self.image_label.clear()
        self.result_edit.clear()
        self.splitter.hide()
        self.hero_frame.show()
        self.drop_zone.show()
        self.copy_btn.setEnabled(False)
        self.status_progress.setText("就绪")

    def _on_open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings = dlg.get_settings()
            save_settings(self.settings)
            self.status_model.setText(f"模型：{self.settings.model or '未配置'}")
            # Re-register screenshot hotkey in case it changed
            self._setup_screenshot_hotkey()

    def _on_open_history(self) -> None:
        dlg = HistoryDialog(self.history, self)
        dlg.exec()
        self.history = dlg.get_active_items()
        save_history(self.history, max_items=self.settings.history_max_items)

    # ------------------------------------------------------- drag & drop

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()
            self.drop_zone.setProperty("dragging", True)
            self.drop_zone.style().unpolish(self.drop_zone)
            self.drop_zone.style().polish(self.drop_zone)

    def dragLeaveEvent(self, event) -> None:
        self.drop_zone.setProperty("dragging", False)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

    def dropEvent(self, event) -> None:
        self.drop_zone.setProperty("dragging", False)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

        mime = event.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                path = url.toLocalFile()
                if path and Path(path).suffix.lower() in (
                    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"
                ):
                    try:
                        self._load_image_from_path(path)
                    except Exception as e:
                        QMessageBox.critical(self, "打开失败", f"无法加载图片：\n{e}")
                    return
        elif mime.hasImage():
            qimg = mime.imageData()
            from PySide6.QtGui import QImage
            rgba = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
            ptr = rgba.constBits()
            ptr.setsize(rgba.sizeInBytes())
            data = bytes(ptr)
            img = Image.frombytes("RGBA", (rgba.width(), rgba.height()), data)
            self._set_image(img)

    # ------------------------------------------------------- close

    def closeEvent(self, event) -> None:
        # Persist window state
        self.settings.window_geometry = self.saveGeometry().data().hex()
        self.settings.window_state = self.saveState().data().hex()
        save_settings(self.settings)
        super().closeEvent(event)
