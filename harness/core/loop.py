"""Minimal event-transparent agent loop (docs/design/loop.md).

``step()`` is the atomic unit: one model call plus its tool calls. Every
boundary emits an Event, so the trace alone reconstructs the run and the
bench can enumerate crash points between any two events.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from harness.core.canonical import canonical_json, digest
from harness.core.types import (
    EventType,
    Role,
    Task,
    TaskStatus,
    Turn,
)
from harness.llm.base import LLMBackend
from harness.tools.registry import ToolRegistry
from harness.trace.jsonl import TraceWriter

__all__ = ["AgentLoop", "RunResult", "SYSTEM_PROMPT"]

SYSTEM_PROMPT = (
    "You are a tool-using agent. Work toward the task goal step by step. "
    "Call tools when you need them; when the task is complete, reply with "
    "your final answer and no tool calls."
)


@dataclass(frozen=True)
class RunResult:
    run_id: str
    task_id: str
    status: TaskStatus
    final_answer: str
    steps: int


class AgentLoop:
    def __init__(
        self,
        backend: LLMBackend,
        tools: ToolRegistry,
        trace: TraceWriter,
        max_steps: int = 20,
    ) -> None:
        self.backend = backend
        self.tools = tools
        self.trace = trace
        self.max_steps = max_steps

        self.task: Task | None = None
        self.turns: list[Turn] = []
        self.step_count = 0
        self.status = TaskStatus.PENDING
        self.final_answer = ""

    # -- lifecycle ---------------------------------------------------------

    def start(self, task: Task) -> None:
        if self.task is not None:
            raise ValueError("loop already started; use a fresh loop per run")
        self.task = task
        self.status = TaskStatus.RUNNING
        task.status = TaskStatus.RUNNING
        self.trace.emit(EventType.RUN_START, {"task": task.to_dict()})

    def run(self, task: Task) -> RunResult:
        self.start(task)
        while self.step():
            pass
        return self.result()

    def result(self) -> RunResult:
        assert self.task is not None
        return RunResult(
            run_id=self.trace.run_id,
            task_id=self.task.id,
            status=self.status,
            final_answer=self.final_answer,
            steps=self.step_count,
        )

    # -- the atomic unit ---------------------------------------------------

    def step(self) -> bool:
        """Execute one turn. Returns False when the run is finished."""
        if self.task is None:
            raise ValueError("loop not started")
        if self.status is not TaskStatus.RUNNING:
            return False
        if self.step_count >= self.max_steps:
            self._finish(TaskStatus.FAILED, reason="max_steps")
            return False

        messages = self.build_messages()
        response = self.backend.complete(messages, tools=self.tools.specs())
        self.step_count += 1
        self.trace.emit(
            EventType.LLM_CALL,
            {
                "step": self.step_count,
                "request_sha256": digest(messages),
                "model": response.model,
                "content_chars": len(response.content),
                "tool_call_count": len(response.tool_calls),
            },
        )
        self.turns.append(
            Turn(
                idx=len(self.turns),
                role=Role.ASSISTANT,
                content=response.content,
                tool_calls=list(response.tool_calls),
                usage=dict(response.usage),
            )
        )

        if not response.tool_calls:
            self.final_answer = response.content
            self._finish(TaskStatus.COMPLETED)
            return False

        for call in response.tool_calls:
            self.trace.emit(EventType.TOOL_START, {"call": call.to_dict()})
            result = self.tools.invoke(call)
            self.trace.emit(EventType.TOOL_END, {"result": result.to_dict()})
            self.turns.append(
                Turn(
                    idx=len(self.turns),
                    role=Role.TOOL,
                    content=canonical_json(result.to_dict()),
                )
            )
        return True

    # -- message assembly (moves to the context module later in P1) --------

    def build_messages(self) -> list[dict[str, Any]]:
        assert self.task is not None
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        user = self.task.goal
        if self.task.inputs:
            user += "\n\nInputs:\n" + canonical_json(self.task.inputs)
        messages.append({"role": "user", "content": user})

        for turn in self.turns:
            if turn.role is Role.ASSISTANT:
                msg: dict[str, Any] = {"role": "assistant", "content": turn.content}
                if turn.tool_calls:
                    msg["tool_calls"] = [c.to_dict() for c in turn.tool_calls]
                messages.append(msg)
            elif turn.role is Role.TOOL:
                result = json.loads(turn.content)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result["call_id"],
                        "content": turn.content,
                    }
                )
        return messages

    # -- internals ---------------------------------------------------------

    def _finish(self, status: TaskStatus, reason: str | None = None) -> None:
        assert self.task is not None
        self.status = status
        self.task.status = status
        payload: dict[str, Any] = {"status": str(status), "steps": self.step_count}
        if reason:
            payload["reason"] = reason
        self.trace.emit(EventType.RUN_END, payload)
