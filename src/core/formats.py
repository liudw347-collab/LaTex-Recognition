"""
Output format transforms for recognized text.

Three formats, matching the original web app:

- typora : raw Markdown + LaTeX (no transform)
- word   : HTML with MathML inline, ready to paste into MS Word
- web    : plain text with \\(...\\) display and \\( ... \\) inline math
           (for web textareas that don't understand $...$)

LaTeX → MathML conversion uses the `latex2mathml` package (pure Python,
no JS runtime needed). If a formula fails to convert, the raw LaTeX is
kept as a fallback so the user can see something.
"""

from __future__ import annotations

import html
import re

try:
    import latex2mathml.converter as _l2m
except ImportError:  # pragma: no cover
    _l2m = None


def _latex_to_mathml(formula: str, display: bool) -> str | None:
    """Convert a LaTeX formula to MathML. Returns None on failure."""
    if _l2m is None:
        return None
    try:
        mathml = _l2m.convert(formula.strip())
        return mathml
    except Exception:
        return None


# ----- Format: Typora (raw markdown) -------------------------------------

def to_typora(raw: str) -> str:
    """No transform — pass through."""
    return raw


# ----- Format: Word (HTML + MathML) --------------------------------------

def to_word_html(raw: str) -> str:
    """
    Convert Markdown + LaTeX into HTML with MathML inline.
    Suitable for pasting into Microsoft Word, which renders MathML natively.
    """
    s = raw

    # Display math $$...$$
    s = re.sub(
        r"\$\$([\s\S]*?)\$\$",
        lambda m: _wrap_display_math(m.group(1).strip()),
        s,
    )

    # Inline math $...$  (avoid matching across lines or greedy $$)
    s = re.sub(
        r"\$([^\$\n]+?)\$",
        lambda m: _wrap_inline_math(m.group(1).strip()),
        s,
    )

    # Markdown headings
    s = re.sub(r"^### (.+)$", r"<h3>\1</h3>", s, flags=re.MULTILINE)
    s = re.sub(r"^## (.+)$", r"<h2>\1</h2>", s, flags=re.MULTILINE)
    s = re.sub(r"^# (.+)$", r"<h1>\1</h1>", s, flags=re.MULTILINE)

    # Bold / italic
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)

    # Unordered lists
    s = re.sub(r"^[-*] (.+)$", r"<li>\1</li>", s, flags=re.MULTILINE)
    s = re.sub(r"(<li>.*</li>\n?)+", lambda m: f"<ul>{m.group(0)}</ul>", s)

    # Ordered lists
    s = re.sub(r"^\d+\. (.+)$", r"<li>\1</li>", s, flags=re.MULTILINE)

    # Wrap loose paragraphs in <p>
    out_blocks: list[str] = []
    for block in s.split("\n\n"):
        trimmed = block.strip()
        if not trimmed:
            continue
        if trimmed.startswith(("<h", "<ul", "<ol", "<p>")):
            out_blocks.append(trimmed)
        else:
            out_blocks.append(f"<p>{trimmed.replace(chr(10), '<br>')}</p>")

    return "\n".join(out_blocks)


def _wrap_display_math(formula: str) -> str:
    mathml = _latex_to_mathml(formula, display=True)
    if mathml:
        return f"<p>{mathml}</p>"
    return f"<p>$${formula}$$</p>"


def _wrap_inline_math(formula: str) -> str:
    mathml = _latex_to_mathml(formula, display=False)
    if mathml:
        return mathml
    return f"${formula}$"


# ----- Format: Web (\\(...\\) syntax) ------------------------------------

def to_web_text(raw: str) -> str:
    """
    Convert $...$ / $$...$$ LaTeX delimiters into \\(...\\) / \\[...\\],
    which many web textareas (e.g. ChatGPT, Notion) recognize.
    """
    s = raw
    s = re.sub(
        r"\$\$([\s\S]*?)\$\$",
        lambda m: f"\\[{m.group(1).strip()}\\]",
        s,
    )
    s = re.sub(
        r"\$([^\$\n]+?)\$",
        lambda m: f"\\({m.group(1).strip()}\\)",
        s,
    )
    return s


# ----- Dispatcher --------------------------------------------------------

FORMAT_IDS = ("typora", "word", "web")

FORMAT_LABELS = {
    "typora": "Typora (Markdown + LaTeX)",
    "word": "Word (HTML + MathML)",
    "web": "网页输入框 (\\(...\\))",
}

FORMAT_DESCRIPTIONS = {
    "typora": "Markdown + LaTeX，适用于 Typora 等 Markdown 编辑器",
    "word": "带 MathML 的 HTML 格式，可直接粘贴到 Word 中渲染公式",
    "web": "纯文本 + LaTeX 标记，适用于网页表单和文本输入",
}


def transform(raw: str, fmt: str) -> str:
    if fmt == "typora":
        return to_typora(raw)
    if fmt == "word":
        return to_word_html(raw)
    if fmt == "web":
        return to_web_text(raw)
    return raw
