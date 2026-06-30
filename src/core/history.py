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
import os
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from PIL import Image

from .config import history_file_path


@dataclass
class HistoryItem:
    id: str                  # unique id (timestamp + counter)
    timestamp: float         # unix epoch seconds
    text: str                # recognized text
    model: str               # model name used
    thumbnail: str           # data URL of small thumbnail PNG
    elapsed_ms: int          # recognition time
    attempts: int            # number of attempts

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HistoryItem":
        """Build a HistoryItem from a dict, using field defaults for any
        missing keys (forward-compatible with older history files)."""
        from dataclasses import MISSING
        kwargs = {}
        for f in fields(cls):
            if f.name in d and d[f.name] is not None:
                kwargs[f.name] = d[f.name]
            elif f.default is not MISSING:
                kwargs[f.name] = f.default
            else:
                # No default — use a sensible empty value based on the
                # type annotation string ('str' → '', 'int' → 0, etc.)
                t = f.type if isinstance(f.type, type) else str(f.type)
                if 'str' in str(t):
                    kwargs[f.name] = ""
                elif 'int' in str(t) or 'float' in str(t):
                    kwargs[f.name] = 0
                else:
                    kwargs[f.name] = None
        return cls(**kwargs)


def make_thumbnail(img: Image.Image, max_size: int = 200) -> str:
    """Return a small data-URL PNG thumbnail for the history view."""
    thumb = img.copy()
    thumb.thumbnail((max_size, max_size), Image.LANCZOS)
    # Convert to RGBA to preserve transparency, or RGB for opaque images.
    if thumb.mode not in ("RGB", "RGBA"):
        thumb = thumb.convert("RGBA")
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
    # Include milliseconds in the id to avoid collisions when two
    # recognitions complete in the same second.
    id_str = "{}-{:03d}".format(
        time.strftime("%Y%m%d-%H%M%S", time.localtime(now)),
        int((now * 1000)) % 1000,
    )
    item = HistoryItem(
        id=id_str,
        timestamp=now,
        text=text,
        model=model,
        thumbnail=thumbnail,
        elapsed_ms=elapsed_ms,
        attempts=attempts,
    )
    items.insert(0, item)
    return items[:max_items]
