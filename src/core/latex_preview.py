"""
LaTeX preview renderer.

Renders Markdown-with-LaTeX text into a single PNG image for preview,
using matplotlib mathtext (pure-Python, no LaTeX install needed).

Limitations of mathtext (vs. full LaTeX):
- Does NOT support \\begin{align}, \\begin{cases}, \\text{}, some macros.
- We fall back to rendering the raw text in a monospace font for any
  formula that fails to parse, so the user always sees *something*.

Public API:
    render_preview(markdown_text: str, width: int = 800, font_size: int = 13)
        -> bytes  # PNG bytes

    render_formula_to_png(formula: str, display: bool, font_size: int = 13)
        -> bytes | None  # PNG bytes, or None on failure
"""

from __future__ import annotations

import io
import re
from typing import Optional

# matplotlib uses Agg backend automatically when no display is set, but
# be explicit to avoid ever pulling in a GUI toolkit.
import matplotlib
matplotlib.use("Agg")
# IMPORTANT: we use the OO API (Figure / FigureCanvasAgg) instead of
# pyplot (plt.figure / plt.close) because pyplot manages global state
# and is NOT thread-safe. This module is called from background worker
# threads; using pyplot would cause intermittent crashes and corrupted
# output when two workers run concurrently.
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
import matplotlib.font_manager as fm  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402

# CJK font discovery: try a list of font files that commonly exist on
# Linux / Windows / macOS, and register the first one found with matplotlib.
# This makes Chinese characters render correctly when mixed with LaTeX math.
import os as _os

_CJK_FONT_CANDIDATES = [
    # Linux
    "/usr/share/fonts/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf",
    "/usr/share/fonts/truetype/chinese/SarasaMonoSC-Regular.ttf",
    "/usr/share/fonts/truetype/lxgw-wenkai/LXGWWenKai-Regular.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    # Windows
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

_cjk_font_path: str | None = None
for _p in _CJK_FONT_CANDIDATES:
    if _os.path.exists(_p):
        try:
            fm.fontManager.addfont(_p)
            _cjk_font_path = _p
            break
        except Exception:
            continue

# Also register DejaVu Sans for Latin/symbol fallback (it's usually already
# installed alongside matplotlib, but be explicit).
for _p in (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
):
    if _os.path.exists(_p):
        try:
            fm.fontManager.addfont(_p)
        except Exception:
            pass

# Determine the CJK font family name for rcParams
_cjk_family_name = "Noto Serif SC"  # sensible default; overridden below
if _cjk_font_path:
    try:
        _fp = fm.FontProperties(fname=_cjk_font_path)
        _cjk_family_name = _fp.get_name()
    except Exception:
        pass

# Set rcParams via matplotlib's global config (thread-safe for reads,
# set once at import time). These are read by the Figure/Text objects
# when they render.
matplotlib.rcParams["font.sans-serif"] = [_cjk_family_name, "DejaVu Sans"]
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["axes.unicode_minus"] = False
# Use 'cm' math fontset (Computer Modern) for clean math look. Mathtext
# uses its own internal fonts for math, so CJK family only affects the
# non-math (rm) text segments.
matplotlib.rcParams["mathtext.fontset"] = "cm"
matplotlib.rcParams["mathtext.default"] = "regular"


def _get_text_font() -> "FontProperties | None":
    """Return a FontProperties pointing to the CJK font file, or None if
    no CJK font is available (in which case we fall back to default fonts
    and Chinese characters will show as boxes)."""
    if _cjk_font_path:
        try:
            return fm.FontProperties(fname=_cjk_font_path)
        except Exception:
            return None
    return None


# Regex matching $...$ and $$...$$ (same as formats.py)
_INLINE_RE = re.compile(r"\$([^\$\n]+?)\$")
_DISPLAY_RE = re.compile(r"\$\$([\s\S]*?)\$\$")

# Markdown heading markers (stripped from preview since mathtext doesn't
# understand them; we render headings as larger bold text).
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def render_formula_to_png(
    formula: str,
    display: bool = True,
    font_size: int = 13,
    color: str = "#1f2937",
) -> Optional[bytes]:
    """
    Render a single LaTeX formula to PNG bytes via matplotlib mathtext.

    Returns None if the formula fails to parse.
    """
    formula = formula.strip()
    if not formula:
        return None

    try:
        # Use the OO API: create a Figure directly (no pyplot global state).
        # Wide figure so the formula isn't wrapped; bbox_inches='tight'
        # crops down to the actual rendered bounds on save.
        fig = Figure(figsize=(10, 0.5), dpi=150)
        FigureCanvasAgg(fig)  # attach a canvas so savefig works
        # mathtext must be wrapped in $...$ for matplotlib to parse it as math.
        # Note: mathtext does NOT support \displaystyle; for "display mode"
        # we just bump the font size up a bit.
        math_str = f"${formula}$"

        # For display mode, use a slightly larger font size.
        actual_size = font_size + (2 if display else 0)

        fig.text(
            0.5,
            0.5,
            math_str,
            ha="center",
            va="center",
            fontsize=actual_size,
            color=color,
        )
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.08,
                    transparent=False, facecolor="white")
        # No plt.close needed — Figure is GC'd when it goes out of scope.
        return buf.getvalue()
    except Exception:
        return None


def _render_text_block_to_png(
    text: str,
    font_size: int = 13,
    color: str = "#1f2937",
    is_heading: bool = False,
    is_list_item: bool = False,
) -> Optional[bytes]:
    """Render a plain-text block (with inline math) to PNG.

    Uses a CJK-capable font (Noto Sans SC on Linux, Microsoft YaHei on
    Windows, PingFang on macOS) so Chinese characters render correctly.
    Inline $...$ math is rendered with matplotlib's mathtext.
    """
    text = text.rstrip()
    if not text:
        return None

    actual_size = font_size + (4 if is_heading else 0)

    prefix = "• " if is_list_item else ""
    display_text = prefix + text

    fontprops = _get_text_font()
    if fontprops is not None:
        fontprops = fontprops.copy()
        fontprops.set_size(actual_size)
        if is_heading:
            fontprops.set_weight("bold")
        text_kwargs = dict(fontproperties=fontprops)
    else:
        text_kwargs = dict(
            fontsize=actual_size,
            fontweight="bold" if is_heading else "normal",
        )

    try:
        # OO API: no pyplot global state, safe for background threads.
        fig = Figure(figsize=(10, 0.5), dpi=150)
        FigureCanvasAgg(fig)
        fig.text(
            0.5,
            0.5,
            display_text,
            ha="center",
            va="center",
            color=color,
            **text_kwargs,
        )
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1,
                    transparent=False, facecolor="white")
        return buf.getvalue()
    except Exception:
        return None


def render_preview(
    markdown_text: str,
    width: int = 800,
    font_size: int = 13,
) -> bytes:
    """
    Render a Markdown+LaTeX string to a single preview PNG.

    Strategy:
    1. Split the text into blocks (paragraphs separated by blank lines).
    2. For each block, classify it as:
       - heading    (starts with #)
       - display $$ (contains $$...$$)
       - list item  (starts with - or *)
       - paragraph  (anything else, may contain inline $...$)
    3. Render each block as a separate PNG via matplotlib.
    4. Stack all block PNGs vertically into a single tall PNG.

    Returns PNG bytes (always non-None; if rendering fails entirely,
    a placeholder image is returned).
    """
    from PIL import Image

    if not markdown_text.strip():
        # Render an empty placeholder so the preview widget has something to show.
        return _render_placeholder("（无内容）", width=width)

    # Pre-strip display math blocks out of the text and render separately.
    # We split the text into ordered segments.
    segments: list[tuple[str, str]] = []  # (kind, content)
    pos = 0
    for m in _DISPLAY_RE.finditer(markdown_text):
        if m.start() > pos:
            segments.append(("text", markdown_text[pos:m.start()]))
        segments.append(("display", m.group(1)))
        pos = m.end()
    if pos < len(markdown_text):
        segments.append(("text", markdown_text[pos:]))

    block_images: list[Image.Image] = []

    for kind, content in segments:
        if kind == "display":
            png = render_formula_to_png(content, display=True, font_size=font_size + 1)
            if png:
                try:
                    img = Image.open(io.BytesIO(png)).convert("RGBA")
                    block_images.append(img)
                    continue
                except Exception:
                    pass
            # Fallback: render the raw formula text in red, indicating parse failure
            fallback_text = f"$${content}$$  [公式解析失败，显示原文]"
            fb_png = _render_text_block_to_png(
                fallback_text, font_size=font_size, color="#b91c1c"
            )
            if fb_png:
                try:
                    img = Image.open(io.BytesIO(fb_png)).convert("RGBA")
                    block_images.append(img)
                    continue
                except Exception:
                    pass
            # Last-resort: tiny placeholder
            block_images.append(Image.new("RGBA", (200, 24), (254, 226, 226, 255)))
        else:
            # text block: split by lines, classify headings and list items
            for raw_line in content.split("\n"):
                line = raw_line.rstrip()
                if not line.strip():
                    # blank line → small vertical spacer
                    spacer = Image.new("RGBA", (1, 8), (0, 0, 0, 0))
                    block_images.append(spacer)
                    continue

                heading_m = _HEADING_RE.match(line)
                is_list = bool(re.match(r"^\s*[-*]\s+", line))
                if is_list:
                    # strip the bullet
                    line = re.sub(r"^\s*[-*]\s+", "", line)

                if heading_m:
                    line = heading_m.group(2)
                    png = _render_text_block_to_png(
                        line, font_size=font_size, is_heading=True
                    )
                else:
                    png = _render_text_block_to_png(
                        line, font_size=font_size, is_list_item=is_list
                    )
                if png:
                    try:
                        img = Image.open(io.BytesIO(png)).convert("RGBA")
                        block_images.append(img)
                    except Exception:
                        # Skip blocks that fail to open as images
                        pass

    if not block_images:
        return _render_placeholder("（无可渲染内容）", width=width)

    # Stack vertically
    total_h = sum(img.height for img in block_images) + 8 * (len(block_images) - 1)
    max_w = max(img.width for img in block_images)
    canvas_w = max(max_w, width)
    canvas = Image.new("RGBA", (canvas_w, total_h), (255, 255, 255, 255))

    y = 0
    for img in block_images:
        # Center horizontally
        x = (canvas_w - img.width) // 2
        canvas.paste(img, (x, y), img if img.mode == "RGBA" else None)
        y += img.height + 8

    # Convert RGBA → RGB (white bg) for the final PNG
    out = Image.new("RGB", canvas.size, (255, 255, 255))
    out.paste(canvas, mask=canvas.split()[3] if canvas.mode == "RGBA" else None)

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _render_placeholder(text: str, width: int = 800) -> bytes:
    """Render a small placeholder image with the given text."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (width, 80), (245, 247, 250))
    draw = ImageDraw.Draw(img)
    # Use the CJK font discovered at module load (cross-platform).
    font = None
    if _cjk_font_path:
        try:
            font = ImageFont.truetype(_cjk_font_path, 14)
        except Exception:
            pass
    if font is None:
        font = ImageFont.load_default()
    draw.text((width // 2, 40), text, fill="#9ca3af", font=font, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
