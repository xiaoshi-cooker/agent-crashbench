"""Tests for the LLM backend protocol and mock (docs/design/llm.md)."""

import pytest

from harness.core.types import ToolCall
from harness.llm import LLMBackend, LLMResponse, MockBackend, ScriptExhausted


def test_mock_returns_script_in_order():
    r1 = LLMResponse(tool_calls=(ToolCall(id="c1", name="read_file", args={"p": "a"}),))
    r2 = LLMResponse(content="done")
    mock = MockBackend([r1, r2])
    assert mock.complete([{"role": "user", "content": "go"}]) is r1
    assert mock.complete([]) is r2
    assert mock.remaining == 0


def test_mock_exhaustion_raises():
    mock = MockBackend([LLMResponse(content="only one")])
    mock.complete([])
    with pytest.raises(ScriptExhausted, match="call #2"):
        mock.complete([])


def test_mock_records_calls():
    mock = MockBackend([LLMResponse(), LLMResponse()])
    mock.complete([{"role": "user", "content": "q1"}], tools=[{"name": "t"}])
    mock.complete([{"role": "user", "content": "q2"}])
    assert len(mock.calls) == 2
    assert mock.calls[0]["tools"] == [{"name": "t"}]
    assert mock.calls[1]["messages"][0]["content"] == "q2"


def test_mock_satisfies_backend_protocol():
    assert isinstance(MockBackend([]), LLMBackend)


def test_response_roundtrip():
    r = LLMResponse(
        content="calling",
        tool_calls=(ToolCall(id="c1", name="t", args={"k": 1}, timeout_s=5.0),),
        usage={"in": 10, "out": 2},
        model="test-model",
    )
    assert LLMResponse.from_dict(r.to_dict()) == r


def test_response_roundtrip_defaults():
    r = LLMResponse()
    d = r.to_dict()
    assert d["tool_calls"] == []
    assert LLMResponse.from_dict(d) == r
