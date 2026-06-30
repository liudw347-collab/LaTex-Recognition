"""
Local history storage for recognition results.

Stored as a JSON list under %APPDATA%/TextLens/history.json.
Each entry holds the recognized text, a thumbnail (small base64 PNG),
timestamp, and the model used. Image bytes themselves are NOT stored
full-size — only a small thumbnail — to keep the file small.
"""

from __future__ import annotations

import base64
import io
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from .config import history_file_path


@dataclass
class HistoryItem:
    id: str                  # ISO timestamp used as unique id
    timestamp: float         # unix epoch seconds
    text: str                # recognized text
    model: str               # model name used
    thumbnail: str           # data URL of small thumbnail PNG
    elapsed_ms: int          # recognition time
    attempts: int            # number of attempts

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HistoryItem":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})  # type: ignore[attr-defined]


def make_thumbnail(img: Image.Image, max_size: int = 200) -> str:
    """Return a small data-URL PNG thumbnail for the history view."""
    thumb = img.copy()
    thumb.thumbnail((max_size, max_size), Image.LANCZOS)
    if thumb.mode not in ("RGB", "RGBA"):
        thumb = thumb.convert("RGB")
    buf = io.BytesIO()
    thumb.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return "data:image/png;base64," + b64


def load_history() -> list[HistoryItem]:
    path = history_file_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [HistoryItem.from_dict(item) for item in raw]
    except (json.JSONDecodeError, OSError, TypeError):
        return []


def save_history(items: list[HistoryItem], max_items: int = 100) -> None:
    """Atomically save the history list, truncating to max_items."""
    path = history_file_path()
    trimmed = items[:max_items]
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps([asdict(i) for i in trimmed], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    import os
    os.replace(tmp, path)


def add_history_item(
    items: list[HistoryItem],
    text: str,
    model: str,
    thumbnail: str,
    elapsed_ms: int,
    attempts: int,
    max_items: int = 100,
) -> list[HistoryItem]:
    """Prepend a new item, return the new list (caller is responsible for saving)."""
    now = time.time()
    item = HistoryItem(
        id=time.strftime("%Y%m%d-%H%M%S", time.localtime(now)),
        timestamp=now,
        text=text,
        model=model,
        thumbnail=thumbnail,
        elapsed_ms=elapsed_ms,
        attempts=attempts,
    )
    items.insert(0, item)
    return items[:max_items]
