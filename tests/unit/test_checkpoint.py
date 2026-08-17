"""Checkpoint store tests + the crash-resume integration test
(docs/design/checkpoint.md)."""

import pytest

from harness.core.loop import AgentLoop
from harness.core.types import EventType, Task, TaskStatus, ToolCall
from harness.llm import LLMResponse, MockBackend
from harness.persist import CheckpointIntegrityError, CheckpointNotFound, FileCheckpointStore
from harness.tools import ToolRegistry
from harness.trace import TraceWriter, read_events

# -- store unit tests -------------------------------------------------------


def test_save_load_roundtrip(tmp_path):
    store = FileCheckpointStore(tmp_path)
    saved = store.save("r1", step=1, payload={"cursor": 1}, meta={"ext": True})
    loaded = store.load("r1", saved.ckpt_id)
    assert loaded == saved
    assert loaded.meta == {"ext": True}
    assert loaded.verify()


def test_atomic_write_leaves_no_tmp(tmp_path):
    store = FileCheckpointStore(tmp_path)
    store.save("r1", step=1, payload={"a": 1})
    files = [p.name for p in (tmp_path / "r1").iterdir()]
    assert files == ["000001.json"]


def test_tamper_detected(tmp_path):
    store = FileCheckpointStore(tmp_path)
    store.save("r1", step=1, payload={"a": 1})
    path = tmp_path / "r1" / "000001.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"a":1', '"a":2'), encoding="utf-8")
    with pytest.raises(CheckpointIntegrityError):
        store.select("r1")


def test_select_latest_and_by_id(tmp_path):
    store = FileCheckpointStore(tmp_path)
    first = store.save("r1", step=1, payload={"cursor": 1})
    store.save("r1", step=2, payload={"cursor": 2})
    assert store.select("r1").payload == {"cursor": 2}
    assert store.select("r1", ckpt_id=first.ckpt_id).payload == {"cursor": 1}
    assert store.steps("r1") == [1, 2]


def test_select_empty_returns_none(tmp_path):
    assert FileCheckpointStore(tmp_path).select("ghost") is None


def test_load_unknown_id_raises(tmp_path):
    store = FileCheckpointStore(tmp_path)
    store.save("r1", step=1, payload={})
    with pytest.raises(CheckpointNotFound):
        store.load("r1", "ckpt-r1-999999")


# -- crash-resume integration ----------------------------------------------


def _registry(calls_log):
    r = ToolRegistry()

    def add(a, b):
        calls_log.append((a, b))
        return a + b

    r.register("add", add)
    return r


def test_abandoned_run_resumes_without_duplicating_tool_calls(tmp_path):
    """The seed of the project's core claim: stop mid-run, restore, finish —
    the already-executed tool call must not run again."""
    calls_log = []
    store = FileCheckpointStore(tmp_path / "ckpts")

    # First life: executes step 1 (tool call add(1,2)), then "crashes".
    trace_a = TraceWriter(tmp_path / "runs", "run1")
    loop_a = AgentLoop(
        MockBackend(
            [
                LLMResponse(
                    tool_calls=(ToolCall(id="c1", name="add", args={"a": 1, "b": 2}),)
                )
            ]
        ),
        _registry(calls_log),
        trace_a,
        checkpoints=store,
    )
    loop_a.start(Task(id="t1", goal="add 1+2 then 3+4"))
    assert loop_a.step() is True
    trace_a.close()  # process gone; loop_a is never touched again

    # Second life: fresh process — restore from the checkpoint and finish.
    trace_b = TraceWriter(tmp_path / "runs", "run1")  # reopen continues seq
    loop_b = AgentLoop.restore(
        MockBackend(
            [
                LLMResponse(
                    tool_calls=(ToolCall(id="c2", name="add", args={"a": 3, "b": 4}),)
                ),
                LLMResponse(content="3 and 7"),
            ]
        ),
        _registry(calls_log),
        trace_b,
        store,
    )
    result = loop_b.continue_run()
    trace_b.close()

    assert result.status is TaskStatus.COMPLETED
    assert result.final_answer == "3 and 7"
    assert result.steps == 3
    # No duplicate side effect: add(1,2) ran exactly once, in the first life.
    assert calls_log == [(1, 2), (3, 4)]

    # One contiguous trace across both lives, with the resume recorded.
    events = read_events(trace_b.path).events
    assert [e.seq for e in events] == list(range(len(events)))
    resume_events = [
        e for e in events if e.type is EventType.RUN_START and e.payload.get("resumed")
    ]
    assert len(resume_events) == 1
    assert resume_events[0].payload["step"] == 1
    assert events[-1].type is EventType.RUN_END


def test_checkpoint_event_emitted_with_content_address(tmp_path):
    store = FileCheckpointStore(tmp_path / "ckpts")
    trace = TraceWriter(tmp_path / "runs", "run2")
    loop = AgentLoop(
        MockBackend(
            [
                LLMResponse(tool_calls=(ToolCall(id="c1", name="add", args={"a": 1, "b": 1}),)),
                LLMResponse(content="2"),
            ]
        ),
        _registry([]),
        trace,
        checkpoints=store,
    )
    loop.run(Task(id="t1", goal="g"))
    trace.close()

    ck_events = [e for e in read_events(trace.path).events if e.type is EventType.CHECKPOINT]
    assert len(ck_events) == 1
    stored = store.select("run2")
    assert ck_events[0].payload["payload_sha256"] == stored.payload_sha256


def test_restore_without_checkpoints_raises(tmp_path):
    with pytest.raises(CheckpointNotFound):
        AgentLoop.restore(
            MockBackend([]),
            _registry([]),
            TraceWriter(tmp_path / "runs", "ghost"),
            FileCheckpointStore(tmp_path / "ckpts"),
        )
