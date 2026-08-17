"""End-to-end loop tests on the mock backend (docs/design/loop.md)."""

import pytest

from harness.core.loop import AgentLoop, RunResult
from harness.core.types import EventType, Task, TaskStatus, ToolCall
from harness.llm import LLMResponse, MockBackend
from harness.tools import ToolRegistry
from harness.trace import TraceWriter, read_events


def make_registry(calls_log=None):
    r = ToolRegistry()

    def add(a, b):
        if calls_log is not None:
            calls_log.append(("add", a, b))
        return a + b

    r.register("add", add, description="add two numbers")
    return r


def scripted_two_tool_run():
    return [
        LLMResponse(
            content="adding first pair",
            tool_calls=(ToolCall(id="c1", name="add", args={"a": 1, "b": 2}),),
        ),
        LLMResponse(
            content="adding second pair",
            tool_calls=(ToolCall(id="c2", name="add", args={"a": 3, "b": 4}),),
        ),
        LLMResponse(content="results are 3 and 7"),
    ]


def test_completes_two_tool_task(tmp_path):
    calls_log = []
    trace = TraceWriter(tmp_path, "run1")
    loop = AgentLoop(MockBackend(scripted_two_tool_run()), make_registry(calls_log), trace)
    result = loop.run(Task(id="t1", goal="add 1+2 then 3+4"))

    assert isinstance(result, RunResult)
    assert result.status is TaskStatus.COMPLETED
    assert result.final_answer == "results are 3 and 7"
    assert result.steps == 3
    assert calls_log == [("add", 1, 2), ("add", 3, 4)]


def test_event_sequence_reconstructs_run(tmp_path):
    trace = TraceWriter(tmp_path, "run2")
    loop = AgentLoop(MockBackend(scripted_two_tool_run()), make_registry(), trace)
    loop.run(Task(id="t1", goal="g"))
    trace.close()

    events = read_events(trace.path).events
    types = [e.type for e in events]
    assert types == [
        EventType.RUN_START,
        EventType.LLM_CALL,
        EventType.TOOL_START,
        EventType.TOOL_END,
        EventType.LLM_CALL,
        EventType.TOOL_START,
        EventType.TOOL_END,
        EventType.LLM_CALL,
        EventType.RUN_END,
    ]
    assert [e.seq for e in events] == list(range(9))
    assert events[2].payload["call"]["name"] == "add"
    assert events[3].payload["result"]["status"] == "ok"
    assert events[-1].payload["status"] == "completed"


def test_max_steps_fails_closed(tmp_path):
    endless = [
        LLMResponse(tool_calls=(ToolCall(id=f"c{i}", name="add", args={"a": 1, "b": 1}),))
        for i in range(10)
    ]
    trace = TraceWriter(tmp_path, "run3")
    loop = AgentLoop(MockBackend(endless), make_registry(), trace, max_steps=3)
    result = loop.run(Task(id="t1", goal="never ends"))

    assert result.status is TaskStatus.FAILED
    assert result.steps == 3
    trace.close()
    end = read_events(trace.path).events[-1]
    assert end.type is EventType.RUN_END
    assert end.payload["reason"] == "max_steps"


def test_tool_error_is_fed_back_and_run_continues(tmp_path):
    script = [
        LLMResponse(tool_calls=(ToolCall(id="c1", name="missing_tool", args={}),)),
        LLMResponse(content="recovered gracefully"),
    ]
    trace = TraceWriter(tmp_path, "run4")
    loop = AgentLoop(MockBackend(script), make_registry(), trace)
    backend_messages_seen = loop.backend.calls  # MockBackend records calls

    result = loop.run(Task(id="t1", goal="g"))
    assert result.status is TaskStatus.COMPLETED

    # The second model call must have seen the tool error as a tool message.
    second_call_messages = backend_messages_seen[1]["messages"]
    tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "c1"
    assert "unknown tool" in tool_msgs[0]["content"]


def test_messages_include_system_goal_and_inputs(tmp_path):
    trace = TraceWriter(tmp_path, "run5")
    loop = AgentLoop(MockBackend([LLMResponse(content="done")]), make_registry(), trace)
    loop.run(Task(id="t1", goal="the goal", inputs={"k": "v"}))

    first_messages = loop.backend.calls[0]["messages"]
    assert first_messages[0]["role"] == "system"
    assert first_messages[1]["role"] == "user"
    assert "the goal" in first_messages[1]["content"]
    assert '"k":"v"' in first_messages[1]["content"]


def test_manual_stepping(tmp_path):
    trace = TraceWriter(tmp_path, "run6")
    loop = AgentLoop(MockBackend(scripted_two_tool_run()), make_registry(), trace)
    loop.start(Task(id="t1", goal="g"))
    assert loop.step() is True
    assert loop.step() is True
    assert loop.step() is False  # final answer
    assert loop.step() is False  # idempotent after finish
    assert loop.status is TaskStatus.COMPLETED


def test_step_before_start_raises(tmp_path):
    loop = AgentLoop(MockBackend([]), make_registry(), TraceWriter(tmp_path, "run7"))
    with pytest.raises(ValueError, match="not started"):
        loop.step()


def test_double_start_raises(tmp_path):
    trace = TraceWriter(tmp_path, "run8")
    loop = AgentLoop(MockBackend([LLMResponse(content="x")]), make_registry(), trace)
    loop.run(Task(id="t1", goal="g"))
    with pytest.raises(ValueError, match="already started"):
        loop.start(Task(id="t2", goal="g2"))
