"""Single-entry tool execution gate (docs/design/tools.md).

All tool calls flow through :meth:`ToolRegistry.invoke`; failures come back
as classified :class:`ToolResult` data, never as exceptions. This chokepoint
is where events, timeouts, idempotency keys, and the intent journal attach
in later phases.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from harness.core.types import ErrorKind, ToolCall, ToolResult, ToolStatus

__all__ = ["ToolRegistry", "ToolError"]


class ToolError(Exception):
    """Raised by tools to self-classify their failure."""

    def __init__(self, message: str, kind: ErrorKind = ErrorKind.FATAL) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class _Spec:
    fn: Callable[..., Any]
    description: str
    parameters: dict[str, Any]
    timeout_s: float


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, _Spec] = {}

    def register(
        self,
        name: str,
        fn: Callable[..., Any],
        description: str = "",
        parameters: dict[str, Any] | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        self._tools[name] = _Spec(
            fn=fn,
            description=description,
            parameters=parameters or {"type": "object", "properties": {}},
            timeout_s=timeout_s,
        )

    def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for name, spec in self._tools.items()
        ]

    def invoke(self, call: ToolCall) -> ToolResult:
        started = time.perf_counter()

        def elapsed_ms() -> int:
            return int((time.perf_counter() - started) * 1000)

        spec = self._tools.get(call.name)
        if spec is None:
            return ToolResult(
                call_id=call.id,
                status=ToolStatus.ERROR,
                error_kind=ErrorKind.SCHEMA,
                error=f"unknown tool: {call.name}",
                elapsed_ms=elapsed_ms(),
            )

        # Both the registered budget and the caller's are upper bounds.
        effective_timeout = min(spec.timeout_s, call.timeout_s)
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(spec.fn, **call.args)
            try:
                content = future.result(timeout=effective_timeout)
            except TimeoutError:
                if future.done():
                    # The tool itself raised TimeoutError; classify like any
                    # other exception rather than as a budget overrun.
                    raise
                # CPython cannot kill the worker thread; the call may keep
                # running in the background. Real isolation is the bench's
                # process-level job — the gate only reports honestly.
                return ToolResult(
                    call_id=call.id,
                    status=ToolStatus.TIMEOUT,
                    error_kind=ErrorKind.RETRYABLE,
                    error=f"timed out after {effective_timeout}s",
                    elapsed_ms=elapsed_ms(),
                )
        except ToolError as exc:
            return ToolResult(
                call_id=call.id,
                status=ToolStatus.ERROR,
                error_kind=exc.kind,
                error=str(exc),
                elapsed_ms=elapsed_ms(),
            )
        except Exception as exc:  # noqa: BLE001 - the gate converts, never leaks
            return ToolResult(
                call_id=call.id,
                status=ToolStatus.ERROR,
                error_kind=ErrorKind.FATAL,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=elapsed_ms(),
            )
        finally:
            executor.shutdown(wait=False)
        return ToolResult(
            call_id=call.id,
            status=ToolStatus.OK,
            content=content,
            elapsed_ms=elapsed_ms(),
        )
