"""LLM backend protocol and implementations (docs/design/llm.md)."""

from harness.llm.backends.mock import MockBackend
from harness.llm.base import LLMBackend, LLMResponse, ScriptExhausted
from harness.llm.cassette import Cassette, CassetteMiss

__all__ = [
    "LLMBackend",
    "LLMResponse",
    "ScriptExhausted",
    "MockBackend",
    "Cassette",
    "CassetteMiss",
]
