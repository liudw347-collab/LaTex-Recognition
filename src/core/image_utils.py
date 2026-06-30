"""
Image preprocessing utilities.

Mirrors the web version's compressImage() function: resize to a max width
and re-encode as PNG, returning a data: URL ready for the AI API.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image


SUPPORTED_FORMATS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff")


def load_image_file(path: str | Path) -> tuple[bytes, str, Image.Image]:
    """
    Load an image file from disk.

    Returns:
        (raw_bytes, mime_type, PIL.Image)
    """
    path = Path(path)
    ext = path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
    }
    mime = mime_map.get(ext, "image/png")
    raw = path.read_bytes()
    img = Image.open(io.BytesIO(raw))
    # Force load so we can close the file handle.
    img.load()
    return raw, mime, img


def compress_image(
    img: Image.Image,
    max_width: int = 2048,
    quality: float = 0.9,  # noqa: ARG001 — kept for API compatibility
) -> tuple[bytes, str]:
    """
    Resize the image if wider than max_width and re-encode as PNG.

    Args:
        img: PIL image to compress.
        max_width: Maximum width in pixels; wider images are downscaled.
        quality: Unused (PNG is lossless). Kept for API compatibility.

    Returns:
        (png_bytes, "image/png")
    """
    # If the image is already within the width limit, just re-encode as
    # PNG (which also normalizes the mode and strips metadata).
    if img.width <= max_width:
        out = _to_png_bytes(img)
        return out, "image/png"

    # Resize maintaining aspect ratio.
    scale = max_width / img.width
    new_size = (max_width, max(round(img.height * scale), 1))
    # Use LANCZOS for downscaling quality.
    resized = img.resize(new_size, Image.LANCZOS)
    out = _to_png_bytes(resized)
    return out, "image/png"


def _to_png_bytes(img: Image.Image) -> bytes:
    """Convert PIL image to PNG bytes, handling RGBA/L/P modes safely."""
    buf = io.BytesIO()
    # PIL handles RGBA for PNG natively. For modes that confuse some
    # downstream tools (P, LA), convert to RGBA for consistency.
    if img.mode in ("P", "LA", "PA"):
        img = img.convert("RGBA")
    elif img.mode == "L":
        # Grayscale — keep as-is, PNG supports it.
        pass
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def bytes_to_data_url(data: bytes, mime: str) -> str:
    """Wrap raw bytes as a data: URL."""
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def data_url_to_bytes(data_url: str) -> tuple[bytes, str]:
    """Inverse of bytes_to_data_url. Returns (raw_bytes, mime).

    Raises ValueError if the data URL is malformed.
    """
    if not data_url or "," not in data_url:
        raise ValueError(f"Malformed data URL (no comma): {data_url[:60]!r}")
    header, b64 = data_url.split(",", 1)
    # header looks like "data:image/png;base64"
    if ":" not in header:
        raise ValueError(f"Malformed data URL header: {header!r}")
    mime_part = header.split(":", 1)[1]
    mime = mime_part.split(";")[0] if ";" in mime_part else mime_part
    if not mime:
        mime = "image/png"
    try:
        raw = base64.b64decode(b64)
    except Exception as e:
        raise ValueError(f"Invalid base64 in data URL: {e}") from e
    return raw, mime
