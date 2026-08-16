"""Frozen core contracts shared by the harness (runtime) and crashbench (rig).

Design rules:

- Every type serializes to plain JSON-compatible dicts via ``to_dict`` and
  rebuilds via ``from_dict``. The JSONL trace, the checkpoint store, and the
  bench all speak these dicts — no pickling, ever.
- Timestamps are integer microseconds UTC (``ts_us``), see
  :mod:`harness.core.canonical`.
- ``Checkpoint`` carries a content address of its payload and an opaque
  ``meta`` extension slot; the harness itself only reads documented fields.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from harness.core.canonical import digest, now_us

__all__ = [
    "Role",
    "ToolStatus",
    "ErrorKind",
    "TaskStatus",
    "EventType",
    "FaultFamily",
    "MemoryScope",
    "MemoryKind",
    "ToolCall",
    "ToolResult",
    "Turn",
    "Task",
    "Event",
    "Checkpoint",
    "MemoryEntry",
    "Skill",
    "Fault",
    "Scenario",
    "LedgerEntry",
]


# --------------------------------------------------------------------------
# Enums (StrEnum: JSON-serializable as plain strings)
# --------------------------------------------------------------------------


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


class ErrorKind(StrEnum):
    """Classification a tool failure gets from the executor."""

    RETRYABLE = "retryable"  # transient: network hiccup, throttling
    FATAL = "fatal"  # will not succeed on retry
    SCHEMA = "schema"  # arguments failed validation; caller must change them


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(StrEnum):
    RUN_START = "run_start"
    LLM_CALL = "llm_call"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    MEMORY_WRITE = "memory_write"
    CHECKPOINT = "checkpoint"
    FAULT_INJECTED = "fault_injected"
    RUN_END = "run_end"


class FaultFamily(StrEnum):
    PROC_KILL = "proc_kill"  # the agent process dies mid-task
    TOOL_ERROR = "tool_error"  # a tool raises / returns garbage
    TOOL_TIMEOUT = "tool_timeout"  # a tool hangs past its budget
    API_THROTTLE = "api_throttle"  # LLM backend returns 429/500 bursts


class MemoryScope(StrEnum):
    SHORT = "short"
    LONG = "long"


class MemoryKind(StrEnum):
    FACT = "fact"
    SUMMARY = "summary"
    PREFERENCE = "preference"


# --------------------------------------------------------------------------
# Dataclasses
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 30.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ToolCall:
        return cls(
            id=d["id"],
            name=d["name"],
            args=dict(d.get("args", {})),
            timeout_s=float(d.get("timeout_s", 30.0)),
        )


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    status: ToolStatus
    content: Any = None
    error_kind: ErrorKind | None = None
    error: str | None = None
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = str(self.status)
        d["error_kind"] = str(self.error_kind) if self.error_kind is not None else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ToolResult:
        ek = d.get("error_kind")
        return cls(
            call_id=d["call_id"],
            status=ToolStatus(d["status"]),
            content=d.get("content"),
            error_kind=ErrorKind(ek) if ek else None,
            error=d.get("error"),
            elapsed_ms=int(d.get("elapsed_ms", 0)),
        )


@dataclass
class Turn:
    idx: int
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    ts_us: int = field(default_factory=now_us)

    def to_dict(self) -> dict[str, Any]:
        return {
            "idx": self.idx,
            "role": str(self.role),
            "content": self.content,
            "tool_calls": [c.to_dict() for c in self.tool_calls],
            "usage": dict(self.usage),
            "ts_us": self.ts_us,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Turn:
        return cls(
            idx=int(d["idx"]),
            role=Role(d["role"]),
            content=d.get("content", ""),
            tool_calls=[ToolCall.from_dict(c) for c in d.get("tool_calls", [])],
            usage=dict(d.get("usage", {})),
            ts_us=int(d.get("ts_us", 0)),
        )


@dataclass
class Task:
    id: str
    goal: str
    inputs: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = str(self.status)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Task:
        return cls(
            id=d["id"],
            goal=d["goal"],
            inputs=dict(d.get("inputs", {})),
            constraints=dict(d.get("constraints", {})),
            status=TaskStatus(d.get("status", "pending")),
        )


@dataclass(frozen=True)
class Event:
    """Atomic unit of the trace. The trace is the ground truth for the bench."""

    run_id: str
    seq: int
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    ts_us: int = field(default_factory=now_us)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "seq": self.seq,
            "type": str(self.type),
            "payload": dict(self.payload),
            "ts_us": self.ts_us,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        return cls(
            run_id=d["run_id"],
            seq=int(d["seq"]),
            type=EventType(d["type"]),
            payload=dict(d.get("payload", {})),
            ts_us=int(d.get("ts_us", 0)),
        )


@dataclass(frozen=True)
class Checkpoint:
    """A persisted snapshot of loop state.

    ``payload_sha256`` is the content address of ``payload`` (canonical JSON).
    ``meta`` is an opaque extension slot: the harness only writes documented
    keys and never interprets unknown ones.
    """

    ckpt_id: str
    run_id: str
    step: int
    payload: dict[str, Any]
    payload_sha256: str
    meta: dict[str, Any] = field(default_factory=dict)
    ts_us: int = field(default_factory=now_us)

    @classmethod
    def create(
        cls,
        run_id: str,
        step: int,
        payload: dict[str, Any],
        meta: dict[str, Any] | None = None,
        ckpt_id: str | None = None,
    ) -> Checkpoint:
        return cls(
            ckpt_id=ckpt_id or f"ckpt-{run_id}-{step:06d}",
            run_id=run_id,
            step=step,
            payload=payload,
            payload_sha256=digest(payload),
            meta=meta or {},
        )

    def verify(self) -> bool:
        """True iff the stored payload still matches its content address."""
        return digest(self.payload) == self.payload_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "ckpt_id": self.ckpt_id,
            "run_id": self.run_id,
            "step": self.step,
            "payload": dict(self.payload),
            "payload_sha256": self.payload_sha256,
            "meta": dict(self.meta),
            "ts_us": self.ts_us,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Checkpoint:
        return cls(
            ckpt_id=d["ckpt_id"],
            run_id=d["run_id"],
            step=int(d["step"]),
            payload=dict(d["payload"]),
            payload_sha256=d["payload_sha256"],
            meta=dict(d.get("meta", {})),
            ts_us=int(d.get("ts_us", 0)),
        )


@dataclass
class MemoryEntry:
    id: str
    scope: MemoryScope
    kind: MemoryKind
    content: str
    source_turn: int | None = None
    tags: list[str] = field(default_factory=list)
    ts_us: int = field(default_factory=now_us)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["scope"] = str(self.scope)
        d["kind"] = str(self.kind)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MemoryEntry:
        return cls(
            id=d["id"],
            scope=MemoryScope(d["scope"]),
            kind=MemoryKind(d["kind"]),
            content=d["content"],
            source_turn=d.get("source_turn"),
            tags=list(d.get("tags", [])),
            ts_us=int(d.get("ts_us", 0)),
        )


@dataclass(frozen=True)
class Skill:
    """Declarative capability package (SKILL.md + frontmatter)."""

    name: str
    version: str
    description: str
    tools_allowed: tuple[str, ...] = ()
    triggers: tuple[str, ...] = ()
    body_path: str = ""
    resources: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tools_allowed": list(self.tools_allowed),
            "triggers": list(self.triggers),
            "body_path": self.body_path,
            "resources": list(self.resources),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Skill:
        return cls(
            name=d["name"],
            version=d.get("version", "0"),
            description=d.get("description", ""),
            tools_allowed=tuple(d.get("tools_allowed", ())),
            triggers=tuple(d.get("triggers", ())),
            body_path=d.get("body_path", ""),
            resources=tuple(d.get("resources", ())),
        )


@dataclass(frozen=True)
class Fault:
    """A declaratively registered fault to inject into a run."""

    family: FaultFamily
    target: str  # tool name, "process", or backend name
    step: int  # inject when the run reaches this step
    seed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": str(self.family),
            "target": self.target,
            "step": self.step,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Fault:
        return cls(
            family=FaultFamily(d["family"]),
            target=d["target"],
            step=int(d["step"]),
            seed=int(d.get("seed", 0)),
        )


@dataclass(frozen=True)
class Scenario:
    """A bench scenario: a skill-defined mini-application plus its oracle data."""

    id: str
    skill: str
    description: str = ""
    gold_trace: tuple[dict[str, Any], ...] = ()
    invariants: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "skill": self.skill,
            "description": self.description,
            "gold_trace": [dict(g) for g in self.gold_trace],
            "invariants": dict(self.invariants),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Scenario:
        return cls(
            id=d["id"],
            skill=d["skill"],
            description=d.get("description", ""),
            gold_trace=tuple(dict(g) for g in d.get("gold_trace", ())),
            invariants=dict(d.get("invariants", {})),
        )


@dataclass(frozen=True)
class LedgerEntry:
    """One externally observable side effect, recorded outside the agent."""

    effect_id: str
    effect_kind: str  # e.g. "file_write", "email_send", "payment"
    payload_digest: str
    ts_us: int = field(default_factory=now_us)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LedgerEntry:
        return cls(
            effect_id=d["effect_id"],
            effect_kind=d["effect_kind"],
            payload_digest=d["payload_digest"],
            ts_us=int(d.get("ts_us", 0)),
        )
