"""Backend protocol and response type (docs/design/llm.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from harness.core.types import ToolCall

__all__ = ["LLMResponse", "LLMBackend", "ScriptExhausted"]


class ScriptExhausted(Exception):
    """A scripted backend was called more times than its script allows."""


@dataclass(frozen=True)
class LLMResponse:
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: dict[str, int] = field(default_factory=dict)
    model: str = "mock"

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": [c.to_dict() for c in self.tool_calls],
            "usage": dict(self.usage),
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LLMResponse:
        return cls(
            content=d.get("content", ""),
            tool_calls=tuple(ToolCall.from_dict(c) for c in d.get("tool_calls", ())),
            usage=dict(d.get("usage", {})),
            model=d.get("model", "mock"),
        )


@runtime_checkable
class LLMBackend(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse: ...
