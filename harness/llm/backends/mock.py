"""Deterministic scripted backend — a first-class citizen, not a test hack.

Bench scenarios run on this to make tool sequences, error paths, and crash
points reproducible bit-for-bit in CI.
"""

from __future__ import annotations

from typing import Any

from harness.llm.base import LLMResponse, ScriptExhausted

__all__ = ["MockBackend"]


class MockBackend:
    """Returns scripted responses in order; fails closed when over-called."""

    def __init__(self, script: list[LLMResponse]) -> None:
        self._script = list(script)
        self._cursor = 0
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools})
        if self._cursor >= len(self._script):
            raise ScriptExhausted(
                f"mock script has {len(self._script)} responses, call #{self._cursor + 1} requested"
            )
        response = self._script[self._cursor]
        self._cursor += 1
        return response

    @property
    def remaining(self) -> int:
        return len(self._script) - self._cursor
