"""Round-trip and contract tests for the frozen core types."""

from harness.core.canonical import digest
from harness.core.types import (
    Checkpoint,
    ErrorKind,
    Event,
    EventType,
    Fault,
    FaultFamily,
    LedgerEntry,
    MemoryEntry,
    MemoryKind,
    MemoryScope,
    Role,
    Scenario,
    Skill,
    Task,
    TaskStatus,
    ToolCall,
    ToolResult,
    ToolStatus,
    Turn,
)


def test_tool_call_roundtrip():
    c = ToolCall(id="c1", name="write_file", args={"path": "a.txt"}, timeout_s=5.0)
    assert ToolCall.from_dict(c.to_dict()) == c


def test_tool_result_roundtrip_with_error():
    r = ToolResult(
        call_id="c1",
        status=ToolStatus.ERROR,
        error_kind=ErrorKind.RETRYABLE,
        error="boom",
        elapsed_ms=12,
    )
    r2 = ToolResult.from_dict(r.to_dict())
    assert r2 == r
    assert r2.error_kind is ErrorKind.RETRYABLE


def test_turn_roundtrip_with_nested_tool_calls():
    t = Turn(
        idx=3,
        role=Role.ASSISTANT,
        content="calling a tool",
        tool_calls=[ToolCall(id="c1", name="t", args={"k": 1})],
        usage={"in": 10, "out": 5},
    )
    t2 = Turn.from_dict(t.to_dict())
    assert t2 == t
    assert t2.tool_calls[0].args == {"k": 1}


def test_task_roundtrip_defaults():
    task = Task(id="t1", goal="do the thing")
    t2 = Task.from_dict(task.to_dict())
    assert t2 == task
    assert t2.status is TaskStatus.PENDING


def test_event_roundtrip_and_json_safe():
    e = Event(run_id="r1", seq=7, type=EventType.TOOL_END, payload={"call_id": "c1"})
    d = e.to_dict()
    assert d["type"] == "tool_end"
    assert Event.from_dict(d) == e


def test_checkpoint_content_addressing():
    payload = {"turns": [1, 2, 3], "cursor": 3}
    ck = Checkpoint.create(run_id="r1", step=3, payload=payload)
    assert ck.payload_sha256 == digest(payload)
    assert ck.verify()
    same = Checkpoint.create(run_id="r1", step=3, payload={"cursor": 3, "turns": [1, 2, 3]})
    assert same.payload_sha256 == ck.payload_sha256  # order-invariant address
    other = Checkpoint.create(run_id="r1", step=4, payload={"cursor": 4})
    assert other.payload_sha256 != ck.payload_sha256


def test_checkpoint_verify_detects_tamper():
    ck = Checkpoint.create(run_id="r1", step=1, payload={"a": 1})
    tampered = Checkpoint.from_dict({**ck.to_dict(), "payload": {"a": 2}})
    assert not tampered.verify()


def test_checkpoint_meta_slot_is_opaque_and_preserved():
    ck = Checkpoint.create(run_id="r1", step=1, payload={"a": 1}, meta={"ext": {"x": 1}})
    ck2 = Checkpoint.from_dict(ck.to_dict())
    assert ck2.meta == {"ext": {"x": 1}}


def test_memory_entry_roundtrip():
    m = MemoryEntry(
        id="m1",
        scope=MemoryScope.LONG,
        kind=MemoryKind.FACT,
        content="user prefers metric units",
        source_turn=2,
        tags=["pref"],
    )
    assert MemoryEntry.from_dict(m.to_dict()) == m


def test_skill_roundtrip():
    s = Skill(
        name="file-migration",
        version="1",
        description="migrate files with manifest checks",
        tools_allowed=("read_file", "write_file"),
        body_path="skills/file-migration/SKILL.md",
    )
    assert Skill.from_dict(s.to_dict()) == s


def test_fault_roundtrip():
    f = Fault(family=FaultFamily.PROC_KILL, target="process", step=5, seed=42)
    d = f.to_dict()
    assert d["family"] == "proc_kill"
    assert Fault.from_dict(d) == f


def test_scenario_roundtrip():
    sc = Scenario(
        id="s1",
        skill="file-migration",
        gold_trace=({"tool": "read_file"}, {"tool": "write_file"}),
        invariants={"max_steps": 20},
    )
    assert Scenario.from_dict(sc.to_dict()) == sc


def test_ledger_entry_roundtrip():
    le = LedgerEntry(effect_id="e1", effect_kind="file_write", payload_digest="abc")
    assert LedgerEntry.from_dict(le.to_dict()) == le
