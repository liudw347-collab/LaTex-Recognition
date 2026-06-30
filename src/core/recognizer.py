"""
Image-text recognition engine using OpenAI-compatible chat completions API.

This is the desktop equivalent of the original Cloudflare Pages Function
`/api/recognize`. Key differences:

- Reads API key, base URL, model from user settings (not env vars).
- Per-request timeout and max-retry count are user-configurable.
- Runs in a QThread worker so the UI stays responsive.
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from .config import Settings


# ----- Constants ----------------------------------------------------------

SYSTEM_PROMPT = """你是一个专业的图文识别助手。你的任务是识别图片中的所有文字和数学公式，并按照指定格式返回结果。

规则：
1. 必须从图片顶部到底部逐行完整识别，绝对不能遗漏图片底部的内容
2. 保持原始的阅读顺序（从上到下，从左到右）
3. 文字部分直接输出为纯文本
4. 数学公式使用 LaTeX 格式输出
5. 行内公式用 $...$ 包裹，独立行公式用 $$...$$ 包裹
6. 如果文字和公式混合在同一段落中，保持它们的相对位置关系
7. 仔细检查图片最底部的区域，确保不遗漏任何文字或公式
8. 如果识别到标题、列表等结构，用 Markdown 格式保留结构
9. 只输出识别结果，不要添加任何解释说明
10. 输出必须完整，不能中途截断"""


# ----- Result types -------------------------------------------------------

@dataclass
class RecognizeResult:
    success: bool
    text: str = ""
    error: str = ""
    attempts: int = 0
    elapsed_ms: int = 0


# ----- Public API ---------------------------------------------------------

ProgressCallback = Callable[[str], None]


def extract_base64(data_url: str) -> str:
    """If the input is a data: URL, strip the header. Otherwise return as-is."""
    if data_url.startswith("data:image/"):
        comma = data_url.find(",")
        if comma != -1:
            return data_url[comma + 1 :]
    return data_url


def clean_markdown_fences(text: str) -> str:
    """Strip leading/trailing ```latex / ```markdown / ```md fences, matching
    the post-processing in the original Cloudflare Function."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:latex|markdown|md)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _build_request_body(model: str, image_data_url: str, settings: Settings) -> dict:
    """Build the OpenAI-compatible chat-completions request body."""
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                    {
                        "type": "text",
                        "text": (
                            SYSTEM_PROMPT
                            + "\n\n请从上到下完整识别这张图片中的所有文字和数学公式，"
                            "特别注意不要遗漏图片底部的内容，按照要求格式输出。"
                        ),
                    },
                ],
            }
        ],
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
    }


def _parse_response(resp: requests.Response) -> tuple[bool, str, str]:
    """Return (success, content, error_message)."""
    try:
        data = resp.json()
    except ValueError:
        return False, "", f"无法解析响应（HTTP {resp.status_code}）：{resp.text[:200]}"

    if resp.is_success:
        content = ""
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            pass
        if not content:
            return False, "", "识别结果为空，请尝试上传更清晰的图片"
        return True, content, ""

    # Error response
    err_msg = ""
    try:
        err_msg = (
            data.get("error", {}).get("message")
            or data.get("message")
            or ""
        )
    except AttributeError:
        pass
    if not err_msg:
        err_msg = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
    return False, "", err_msg


def recognize_image(
    image_data_url: str,
    settings: Settings,
    progress_cb: Optional[ProgressCallback] = None,
) -> RecognizeResult:
    """
    Recognize text and formulas in the given image.

    Args:
        image_data_url: Image as a data: URL string (e.g. "data:image/png;base64,...")
                        or raw base64 string.
        settings:       User settings (API key, model, timeout, retries, ...).
        progress_cb:    Optional callback receiving human-readable progress strings.

    Returns:
        RecognizeResult with either .text set (success) or .error set (failure).
    """
    started = time.monotonic()

    def emit(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    # ----- Validate settings -----
    if not settings.api_key:
        return RecognizeResult(False, error="未配置 API 密钥，请先在设置中填写")
    if not settings.base_url:
        return RecognizeResult(False, error="未配置 API Base URL")
    if not settings.model:
        return RecognizeResult(False, error="未配置模型名称")

    # Ensure the image is a proper data URL; if the caller passed raw
    # base64, wrap it. We don't use extractBase64's return value here
    # because the AI API accepts data URLs directly.
    if not image_data_url.startswith("data:image/"):
        b64 = extract_base64(image_data_url)
        image_data_url = "data:image/png;base64," + b64

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.api_key}",
    }
    url = settings.base_url.rstrip("/") + "/chat/completions"

    # Single-model retry loop (matches original behavior; users pick the model).
    last_error = ""
    attempts = 0

    for attempt in range(1, settings.max_retries + 1):
        attempts = attempt
        emit(f"正在识别... 第 {attempt}/{settings.max_retries} 次尝试")

        body = _build_request_body(settings.model, image_data_url, settings)
        try:
            resp = requests.post(
                url,
                headers=headers,
                data=json.dumps(body),
                timeout=settings.timeout_seconds,
            )
        except requests.Timeout:
            last_error = (
                f"请求超时（{settings.timeout_seconds}s），"
                f"请尝试在设置中增加超时时间"
            )
            emit(last_error)
            # Retry on timeout
            if attempt < settings.max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            break
        except requests.RequestException as e:
            last_error = f"网络错误：{e}"
            emit(last_error)
            if attempt < settings.max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            break

        ok, content, err = _parse_response(resp)

        if ok:
            cleaned = clean_markdown_fences(content)
            elapsed = int((time.monotonic() - started) * 1000)
            emit("识别成功")
            return RecognizeResult(
                success=True,
                text=cleaned,
                attempts=attempts,
                elapsed_ms=elapsed,
            )

        last_error = err
        emit(f"第 {attempt} 次失败：{err}")

        # 429 rate limit → exponential backoff
        if resp.status_code == 429:
            wait_ms = settings.retry_backoff_base_ms * attempt
            emit(f"触发限流，等待 {wait_ms // 1000}s 后重试...")
            time.sleep(wait_ms / 1000)
            continue

        # 400 bad request → no point retrying the same payload
        if resp.status_code == 400:
            emit("请求格式错误（可能是模型不支持图片输入），停止重试")
            break

        # 401/403 → key/auth issue, no point retrying
        if resp.status_code in (401, 403):
            emit("API Key 无效或权限不足，停止重试")
            break

        # Other errors → short backoff and retry
        if attempt < settings.max_retries:
            time.sleep(1.0)
            continue

    elapsed = int((time.monotonic() - started) * 1000)
    return RecognizeResult(
        success=False,
        error=f"AI 服务暂时不可用{('：' + last_error) if last_error else ''}，请稍后再试",
        attempts=attempts,
        elapsed_ms=elapsed,
    )
