"""Record/replay cassette: memoized model responses, itself a backend.

Design: docs/design/llm.md. Replay is fail-closed: a request that was never
recorded raises instead of silently hitting the network — determinism is a
correctness property here, not a convenience.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Literal

from harness.core.canonical import canonical_json, digest
from harness.llm.base import LLMBackend, LLMResponse

__all__ = ["Cassette", "CassetteMiss"]


class CassetteMiss(Exception):
    """Replay mode was asked for a request that was never recorded."""


class Cassette:
    """Wraps a backend in ``record`` mode; stands alone in ``replay`` mode.

    Identical requests recorded multiple times replay in recording order
    (per-key FIFO), so runs with repeated prompts stay faithful.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        mode: Literal["record", "replay"],
        backend: LLMBackend | None = None,
    ) -> None:
        if mode not in ("record", "replay"):
            raise ValueError(f"unknown cassette mode: {mode}")
        if mode == "record" and backend is None:
            raise ValueError("record mode requires a backend to record from")
        self.path = Path(path)
        self.mode = mode
        self.backend = backend

        self._replay: dict[str, deque[LLMResponse]] = defaultdict(deque)
        if mode == "replay" and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                self._replay[entry["key"]].append(LLMResponse.from_dict(entry["response"]))

    @staticmethod
    def request_key(
        messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> str:
        return digest({"messages": messages, "tools": tools or []})

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        key = self.request_key(messages, tools)
        if self.mode == "replay":
            queue = self._replay.get(key)
            if not queue:
                raise CassetteMiss(f"no recorded response for request {key[:12]}")
            return queue.popleft()

        assert self.backend is not None
        response = self.backend.complete(messages, tools=tools)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="") as fh:
            fh.write(canonical_json({"key": key, "response": response.to_dict()}) + "\n")
        return response
