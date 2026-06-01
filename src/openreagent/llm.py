"""LLM client interface for the *extract* path only.

This module is never imported by ``openreagent.scan`` or by any recipe module
at import time. Recipe extractors import it lazily, inside ``extract``, so that
loading recipes for a scan pulls in no LLM client (a test guard asserts this).

The interface is intentionally tiny and pluggable. The default implementation
wraps the ``anthropic`` SDK (installed via the ``extract`` extra). A
``ReplayClient`` reads pre-recorded responses from a JSONL file, so an
extraction can be reproduced deterministically with no network access.
"""
from __future__ import annotations

import json
import os
from typing import Protocol


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    uses_llm: bool

    def complete_json(self, prompt: str, key: str) -> dict:
        """Return a parsed JSON object for ``prompt``. ``key`` identifies the
        call for replay/caching."""
        ...


class AnthropicClient:
    """Default client. Requires ``pip install 'openreagent[extract]'`` and an
    ``ANTHROPIC_API_KEY`` in the environment."""

    uses_llm = True

    def __init__(self, model: str = "claude-sonnet-4-5", temperature: float = 0.0):
        self.model = model
        self.temperature = temperature

    def complete_json(self, prompt: str, key: str) -> dict:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY not set. Set it, supply pre-filled slots in the "
                "finding, or use a ReplayClient."
            )
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise LLMError(
                "anthropic SDK not installed. Run: pip install 'openreagent[extract]'."
            ) from exc
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=self.model,
            max_tokens=2048,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:-1])
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM did not return JSON for {key}: {exc}") from exc


class ReplayClient:
    """Deterministic, offline client backed by a JSONL file of records:
    ``{"key": "<key>", "output": {...}}``."""

    uses_llm = False

    def __init__(self, path: str):
        self.responses: dict[str, dict] = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    self.responses[rec["key"]] = rec["output"]

    def complete_json(self, prompt: str, key: str) -> dict:
        if key not in self.responses:
            raise LLMError(f"no replay response recorded for key {key!r}")
        return self.responses[key]


def default_client() -> LLMClient | None:
    """Return an LLM client if one can be configured, else None.

    Honors ``OPENREAGENT_REPLAY_FILE`` for offline replay; otherwise returns an
    ``AnthropicClient`` when ``ANTHROPIC_API_KEY`` is present; otherwise None.
    """
    replay = os.environ.get("OPENREAGENT_REPLAY_FILE")
    if replay and os.path.exists(replay):
        return ReplayClient(replay)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClient()
    return None
