"""Deterministic fault injection at the harness chokepoints.

Design: docs/design/faults.md. ``step`` on a Fault means the Nth occurrence
(1-based) of its target; every fault fires exactly once and is always
visible in the trace.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from harness.core.types import (
    ErrorKind,
    EventType,
    Fault,
    FaultFamily,
    ToolCall,
    ToolResult,
    ToolStatus,
)
from harness.llm.base import LLMBackend, LLMResponse
from harness.tools.registry import ToolRegistry
from harness.trace.jsonl import TraceWriter

__all__ = ["FaultPlan", "InjectedToolRegistry", "InjectedBackend", "ApiThrottleError"]

_TOOL_FAMILIES = (FaultFamily.TOOL_ERROR, FaultFamily.TOOL_TIMEOUT)


class ApiThrottleError(Exception):
    """Synthetic backend throttling (HTTP 429 shaped)."""

    status_code = 429


class FaultPlan:
    def __init__(self, faults: Iterable[Fault]) -> None:
        self._faults: list[Fault] = list(faults)
        self._consumed: set[int] = set()

    def _match(self, wanted_families: tuple[FaultFamily, ...], target: str, occurrence: int):
        for i, fault in enumerate(self._faults):
            if (
                i not in self._consumed
                and fault.family in wanted_families
                and fault.target == target
                and fault.step == occurrence
            ):
                self._consumed.add(i)
                return fault
        return None

    def match_tool(self, name: str, occurrence: int) -> Fault | None:
        return self._match(_TOOL_FAMILIES, name, occurrence)

    def match_llm(self, occurrence: int) -> Fault | None:
        return self._match((FaultFamily.API_THROTTLE,), "llm", occurrence)

    def unconsumed(self) -> list[Fault]:
        return [f for i, f in enumerate(self._faults) if i not in self._consumed]


class InjectedToolRegistry:
    """Drop-in for ToolRegistry that substitutes declared failures."""

    def __init__(
        self,
        inner: ToolRegistry,
        plan: FaultPlan,
        trace: TraceWriter | None = None,
    ) -> None:
        self.inner = inner
        self.plan = plan
        self.trace = trace
        self._occurrences: Counter[str] = Counter()

    def specs(self) -> list[dict[str, Any]]:
        return self.inner.specs()

    def invoke(self, call: ToolCall) -> ToolResult:
        self._occurrences[call.name] += 1
        fault = self.plan.match_tool(call.name, self._occurrences[call.name])
        if fault is None:
            return self.inner.invoke(call)

        if self.trace is not None:
            self.trace.emit(EventType.FAULT_INJECTED, {"fault": fault.to_dict()})
        if fault.family is FaultFamily.TOOL_TIMEOUT:
            return ToolResult(
                call_id=call.id,
                status=ToolStatus.TIMEOUT,
                error_kind=ErrorKind.RETRYABLE,
                error=f"injected timeout (seed={fault.seed})",
            )
        return ToolResult(
            call_id=call.id,
            status=ToolStatus.ERROR,
            error_kind=ErrorKind.RETRYABLE,
            error=f"injected transport failure (seed={fault.seed})",
        )


class InjectedBackend:
    """Drop-in for any LLMBackend that throttles declared model calls."""

    def __init__(
        self,
        inner: LLMBackend,
        plan: FaultPlan,
        trace: TraceWriter | None = None,
    ) -> None:
        self.inner = inner
        self.plan = plan
        self.trace = trace
        self._occurrence = 0

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self._occurrence += 1
        fault = self.plan.match_llm(self._occurrence)
        if fault is not None:
            if self.trace is not None:
                self.trace.emit(EventType.FAULT_INJECTED, {"fault": fault.to_dict()})
            raise ApiThrottleError(f"injected throttle (seed={fault.seed})")
        return self.inner.complete(messages, tools=tools)
