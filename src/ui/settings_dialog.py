"""
Settings dialog: lets the user bind their own AI model + API key, and
configure timeout / retries / image preprocessing / UI behavior.

Layout:
  - API 预设 (dropdown: 智谱/OpenAI/.../自定义)
  - API Base URL
  - API Key (password-style with show/hide toggle)
  - 模型名称
  - 超时时间 (秒)
  - 最大重试次数
  - 限流退避基数 (毫秒)
  - 默认复制格式
  - 自动识别
  - 图片最大宽度
  - 截图快捷键
  - 历史记录开关
  - 历史上限
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..core.config import API_PRESETS, Settings, PRESET_BY_ID
from ..core.formats import FORMAT_LABELS


class SettingsDialog(QDialog):
    """Modal dialog for editing user settings."""

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(560)
        self._settings = settings
        self._build_ui()
        self._load_from_settings()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        title = QLabel("API 与软件设置")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        root.addWidget(title)

        hint = QLabel(
            "在这里绑定你自己的模型和 API Key。配置仅保存在本机，不会被上传。"
            "你可以随时回到此对话框修改。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6b7280; font-size: 11pt;")
        root.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        root.addLayout(form)

        # --- API section ---
        self.preset_combo = QComboBox()
        for preset in API_PRESETS:
            label = preset.name if preset.id != "custom" else "自定义 (手动填写)"
            self.preset_combo.addItem(label, preset.id)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow("API 服务商：", self.preset_combo)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("https://api.example.com/v1")
        form.addRow("API Base URL：", self.base_url_edit)

        # API key row with show/hide button
        key_row = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        self.show_key_btn = QPushButton("显示")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setFixedWidth(64)
        self.show_key_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self.api_key_edit)
        key_row.addWidget(self.show_key_btn)
        form.addRow("API Key：", key_row)

        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("glm-4.6v-flash / gpt-4o / ...")
        form.addRow("模型名称：", self.model_edit)

        self.doc_link = QLabel("")
        self.doc_link.setOpenExternalLinks(True)
        self.doc_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.doc_link.setStyleSheet("color: #2563eb; font-size: 10pt;")
        form.addRow("获取 Key：", self.doc_link)

        # --- Request behavior ---
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 600)
        self.timeout_spin.setSuffix(" 秒")
        form.addRow("单次请求超时：", self.timeout_spin)

        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 30)
        form.addRow("最大重试次数：", self.retries_spin)

        self.backoff_spin = QSpinBox()
        self.backoff_spin.setRange(500, 30000)
        self.backoff_spin.setSingleStep(500)
        self.backoff_spin.setSuffix(" ms")
        form.addRow("限流退避基数：", self.backoff_spin)

        # --- Image preprocessing ---
        self.img_width_spin = QSpinBox()
        self.img_width_spin.setRange(512, 8192)
        self.img_width_spin.setSingleStep(256)
        self.img_width_spin.setSuffix(" px")
        form.addRow("图片最大宽度：", self.img_width_spin)

        # --- UI behavior ---
        self.format_combo = QComboBox()
        for fid, label in FORMAT_LABELS.items():
            self.format_combo.addItem(label, fid)
        form.addRow("默认复制格式：", self.format_combo)

        self.auto_recognize_check = QCheckBox("加载图片后自动开始识别")
        form.addRow("", self.auto_recognize_check)

        self.history_check = QCheckBox("保存识别历史到本地")
        form.addRow("", self.history_check)

        self.history_max_spin = QSpinBox()
        self.history_max_spin.setRange(10, 1000)
        self.history_max_spin.setSingleStep(10)
        form.addRow("历史记录上限：", self.history_max_spin)

        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText("Ctrl+Alt+S")
        form.addRow("截图快捷键：", self.hotkey_edit)

        # --- Buttons ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ------------------------------------------------------------- handlers

    def _on_preset_changed(self, _index: int) -> None:
        preset_id = self.preset_combo.currentData()
        preset = PRESET_BY_ID.get(preset_id)
        if not preset:
            return
        # Update base URL and model fields, but DON'T clobber the key.
        if preset.base_url:
            self.base_url_edit.setText(preset.base_url)
        if preset.default_model:
            self.model_edit.setText(preset.default_model)
        if preset.doc_url:
            self.doc_link.setText(
                f'<a href="{preset.doc_url}">{preset.doc_url}</a>'
            )
        else:
            self.doc_link.setText("")

    def _toggle_key_visibility(self, checked: bool) -> None:
        if checked:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_btn.setText("隐藏")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_btn.setText("显示")

    # ------------------------------------------------------------ load/save

    def _load_from_settings(self) -> None:
        s = self._settings
        # Find combo index for current preset
        idx = self.preset_combo.findData(s.preset_id)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        self.base_url_edit.setText(s.base_url)
        self.api_key_edit.setText(s.api_key)
        self.model_edit.setText(s.model)
        self.timeout_spin.setValue(s.timeout_seconds)
        self.retries_spin.setValue(s.max_retries)
        self.backoff_spin.setValue(s.retry_backoff_base_ms)
        self.img_width_spin.setValue(s.image_max_width)
        fmt_idx = self.format_combo.findData(s.default_copy_format)
        if fmt_idx >= 0:
            self.format_combo.setCurrentIndex(fmt_idx)
        self.auto_recognize_check.setChecked(s.auto_recognize)
        self.history_check.setChecked(s.history_enabled)
        self.history_max_spin.setValue(s.history_max_items)
        self.hotkey_edit.setText(s.screenshot_hotkey)

        # Trigger doc link update
        self._on_preset_changed(self.preset_combo.currentIndex())

    def get_settings(self) -> Settings:
        """Return a new Settings object populated from the dialog fields."""
        s = Settings()  # fresh copy
        s.preset_id = self.preset_combo.currentData()
        s.base_url = self.base_url_edit.text().strip()
        s.api_key = self.api_key_edit.text().strip()
        s.model = self.model_edit.text().strip()
        s.timeout_seconds = self.timeout_spin.value()
        s.max_retries = self.retries_spin.value()
        s.retry_backoff_base_ms = self.backoff_spin.value()
        s.image_max_width = self.img_width_spin.value()
        s.default_copy_format = self.format_combo.currentData()
        s.auto_recognize = self.auto_recognize_check.isChecked()
        s.history_enabled = self.history_check.isChecked()
        s.history_max_items = self.history_max_spin.value()
        s.screenshot_hotkey = self.hotkey_edit.text().strip()
        # Preserve preserved fields
        s.window_geometry = self._settings.window_geometry
        s.window_state = self._settings.window_state
        s.last_open_dir = self._settings.last_open_dir
        return s

    def accept(self) -> None:
        # Basic validation before closing.
        if not self.api_key_edit.text().strip():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "缺少 API Key", "请填写 API Key 后再保存。")
            return
        if not self.base_url_edit.text().strip():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "缺少 Base URL", "请填写 API Base URL 后再保存。")
            return
        if not self.model_edit.text().strip():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "缺少模型名称", "请填写模型名称后再保存。")
            return
        super().accept()
