"""
Shared Claude API client wrapper.

Provides:
- A singleton Anthropic client
- A call() helper that handles retries, JSON extraction, and error logging
- A stream_call() helper for streaming completions
"""

from __future__ import annotations

import json
import re
import time
import os
from typing import Any, Optional

import anthropic

from utils.logger import log_info, log_warn, log_error

# ── singleton client ──────────────────────────────────────────────────────────
_client: Optional[anthropic.Anthropic] = None

MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4096


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Add it to your .env file or export it in your shell."
            )
        _client = anthropic.Anthropic(api_key=api_key)
        log_info("Claude client initialised", model=MODEL)
    return _client


# ── core call helper ──────────────────────────────────────────────────────────
def call(
    prompt: str,
    system: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    temperature: float = 0.3,
) -> str:
    """
    Send a single-turn message to Claude and return the text response.

    Retries on transient API errors with exponential back-off.
    """
    client = get_client()
    messages = [{"role": "user", "content": prompt}]
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    for attempt in range(1, max_retries + 1):
        try:
            response = client.messages.create(**kwargs)
            text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            return text.strip()
        except anthropic.RateLimitError:
            wait = retry_delay * (2 ** (attempt - 1))
            log_warn(f"Rate limited — waiting {wait:.0f}s (attempt {attempt}/{max_retries})")
            time.sleep(wait)
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500 and attempt < max_retries:
                wait = retry_delay * attempt
                log_warn(f"Server error {exc.status_code} — retrying in {wait:.0f}s")
                time.sleep(wait)
            else:
                log_error(f"API error {exc.status_code}: {exc.message}")
                raise
        except Exception as exc:
            log_error(f"Unexpected error calling Claude: {exc}")
            raise

    raise RuntimeError(f"Claude call failed after {max_retries} attempts")


# ── JSON extraction helper ────────────────────────────────────────────────────
def call_json(
    prompt: str,
    system: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_retries: int = 3,
) -> Any:
    """
    Call Claude and parse the response as JSON.

    The system prompt is automatically augmented to request pure JSON output.
    Strips markdown fences before parsing.
    """
    json_system = (
        (system + "\n\n" if system else "")
        + "You MUST respond with valid JSON only. "
        "Do NOT include markdown code fences, preamble, or commentary. "
        "Return only the raw JSON object or array."
    )

    raw = call(prompt, system=json_system, max_tokens=max_tokens, max_retries=max_retries)

    # Strip ```json ... ``` fences if Claude added them anyway
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log_error(f"JSON parse error: {exc}\nRaw response:\n{raw[:500]}")
        raise ValueError(f"Claude returned invalid JSON: {exc}") from exc
