"""Tests for declarative fault injection (docs/design/faults.md)."""

import pytest

from crashbench.faults import ApiThrottleError, FaultPlan, InjectedBackend, InjectedToolRegistry
from harness.core.loop import AgentLoop
from harness.core.types import (
    EventType,
    Fault,
    FaultFamily,
    Task,
    TaskStatus,
    ToolCall,
    ToolStatus,
)
from harness.llm import LLMResponse, MockBackend
from harness.tools import ToolRegistry
from harness.trace import TraceWriter, read_events


def _registry(calls_log=None):
    r = ToolRegistry()

    def add(a, b):
        if calls_log is not None:
            calls_log.append((a, b))
        return a + b

    r.register("add", add)
    return r


def _call(cid="c1"):
    return ToolCall(id=cid, name="add", args={"a": 1, "b": 1})


def test_plan_matches_exact_occurrence_once():
    plan = FaultPlan([Fault(family=FaultFamily.TOOL_ERROR, target="add", step=2)])
    assert plan.match_tool("add", 1) is None
    assert plan.match_tool("add", 2) is not None
    assert plan.match_tool("add", 2) is None  # consumed
    assert plan.unconsumed() == []


def test_injected_error_substitutes_without_executing():
    calls_log = []
    plan = FaultPlan([Fault(family=FaultFamily.TOOL_ERROR, target="add", step=1, seed=7)])
    gate = InjectedToolRegistry(_registry(calls_log), plan)

    result = gate.invoke(_call())
    assert result.status is ToolStatus.ERROR
    assert "seed=7" in result.error
    assert calls_log == []  # the real tool never ran

    result2 = gate.invoke(_call("c2"))  # second occurrence passes through
    assert result2.status is ToolStatus.OK
    assert calls_log == [(1, 1)]


def test_injected_timeout_family_maps_to_timeout_status():
    plan = FaultPlan([Fault(family=FaultFamily.TOOL_TIMEOUT, target="add", step=1)])
    gate = InjectedToolRegistry(_registry(), plan)
    assert gate.invoke(_call()).status is ToolStatus.TIMEOUT


def test_specs_passthrough():
    gate = InjectedToolRegistry(_registry(), FaultPlan([]))
    assert gate.specs()[0]["function"]["name"] == "add"


def test_backend_throttle_raises_at_nth_call():
    plan = FaultPlan([Fault(family=FaultFamily.API_THROTTLE, target="llm", step=2)])
    backend = InjectedBackend(MockBackend([LLMResponse(), LLMResponse()]), plan)
    backend.complete([])  # first call fine
    with pytest.raises(ApiThrottleError) as exc:
        backend.complete([])
    assert exc.value.status_code == 429


def test_loop_recovers_from_injected_tool_error(tmp_path):
    """Injected transport failure is fed back; run completes; injection is
    visible in the trace between tool_start and tool_end."""
    script = [
        LLMResponse(tool_calls=(ToolCall(id="c1", name="add", args={"a": 1, "b": 2}),)),
        LLMResponse(tool_calls=(ToolCall(id="c2", name="add", args={"a": 1, "b": 2}),)),
        LLMResponse(content="3 after retrying"),
    ]
    calls_log = []
    plan = FaultPlan([Fault(family=FaultFamily.TOOL_ERROR, target="add", step=1)])
    trace = TraceWriter(tmp_path, "run1")
    gate = InjectedToolRegistry(_registry(calls_log), plan, trace=trace)
    loop = AgentLoop(MockBackend(script), gate, trace)

    result = loop.run(Task(id="t1", goal="add 1+2"))
    trace.close()

    assert result.status is TaskStatus.COMPLETED
    assert calls_log == [(1, 2)]  # only the retry actually executed
    types = [e.type for e in read_events(trace.path).events]
    i = types.index(EventType.FAULT_INJECTED)
    assert types[i - 1] is EventType.TOOL_START
    assert types[i + 1] is EventType.TOOL_END
    assert plan.unconsumed() == []
