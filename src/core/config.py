"""
Configuration management for TextLens desktop app.

Stores user settings (API key, model, base URL, timeout, retries, etc.)
in a local JSON file under %APPDATA%/TextLens/config.json on Windows
or ~/.config/textLens/config.json on Linux/macOS.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# ----- API provider presets ----------------------------------------------

@dataclass
class ApiPreset:
    """A built-in API provider preset that users can pick from a dropdown."""
    id: str
    name: str          # display name (Chinese)
    base_url: str
    default_model: str
    doc_url: str = ""

API_PRESETS: list[ApiPreset] = [
    ApiPreset(
        id="zhipu",
        name="智谱 GLM (BigModel)",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4.6v-flash",
        doc_url="https://open.bigmodel.cn/usercenter/apikeys",
    ),
    ApiPreset(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        doc_url="https://platform.openai.com/api-keys",
    ),
    ApiPreset(
        id="qwen",
        name="通义千问 (DashScope)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-vl-plus",
        doc_url="https://dashscope.console.aliyun.com/apiKey",
    ),
    ApiPreset(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        doc_url="https://platform.deepseek.com/api_keys",
    ),
    ApiPreset(
        id="moonshot",
        name="Moonshot (Kimi)",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-8k-vision-preview",
        doc_url="https://platform.moonshot.cn/console/api-keys",
    ),
    ApiPreset(
        id="custom",
        name="自定义",
        base_url="",
        default_model="",
        doc_url="",
    ),
]

PRESET_BY_ID: dict[str, ApiPreset] = {p.id: p for p in API_PRESETS}


# ----- Settings dataclass -------------------------------------------------

@dataclass
class Settings:
    """All user-editable settings. Serialized to JSON on save."""

    # API connection
    preset_id: str = "zhipu"
    base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    api_key: str = ""
    model: str = "glm-4.6v-flash"

    # Request behavior
    timeout_seconds: int = 60          # per-request timeout
    max_retries: int = 7               # max retry attempts per model
    retry_backoff_base_ms: int = 3000  # base wait time for 429 backoff

    # Model parameters
    temperature: float = 0.1
    max_tokens: int = 8192

    # Image preprocessing
    image_max_width: int = 2048
    image_quality: float = 0.9

    # UI behavior
    default_copy_format: str = "typora"  # typora | word | web
    auto_recognize: bool = True          # auto-run recognition on image load
    minimize_to_tray: bool = False
    screenshot_hotkey: str = "Ctrl+Alt+S"

    # History
    history_enabled: bool = True
    history_max_items: int = 100

    # Window state
    window_geometry: str = ""
    window_state: str = ""

    # Last used directory for file dialogs
    last_open_dir: str = ""

    # ---- Helpers ----
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        # Only pick keys that exist in the dataclass, to be forward-compatible
        # with older config files.
        valid_keys = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    def apply_preset(self, preset_id: str) -> None:
        """Apply a preset's base_url and default_model fields. Does NOT
        overwrite api_key (users want to keep their key when switching)."""
        preset = PRESET_BY_ID.get(preset_id)
        if not preset:
            return
        self.preset_id = preset.id
        if preset.base_url:
            self.base_url = preset.base_url
        if preset.default_model:
            self.model = preset.default_model


# ----- Persistence --------------------------------------------------------

def _config_dir() -> Path:
    """Return the per-user config directory, creating it if needed."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    cfg_dir = Path(base) / "TextLens"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


def config_file_path() -> Path:
    return _config_dir() / "config.json"


def history_file_path() -> Path:
    return _config_dir() / "history.json"


def load_settings() -> Settings:
    """Load settings from disk, returning defaults if missing/corrupt."""
    path = config_file_path()
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Settings.from_dict(data)
    except (json.JSONDecodeError, OSError, TypeError):
        # Corrupt config — fall back to defaults rather than crash.
        return Settings()


def save_settings(settings: Settings) -> None:
    """Persist settings to disk atomically."""
    path = config_file_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(settings.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    # os.replace is atomic on the same filesystem.
    os.replace(tmp, path)
