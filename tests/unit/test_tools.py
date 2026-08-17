"""Tests for the tool registry gate (docs/design/tools.md)."""

import pytest

from harness.core.types import ErrorKind, ToolCall, ToolStatus
from harness.tools import ToolError, ToolRegistry


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register("add", lambda a, b: a + b, description="add two numbers")
    return r


def test_invoke_ok(registry):
    result = registry.invoke(ToolCall(id="c1", name="add", args={"a": 2, "b": 3}))
    assert result.status is ToolStatus.OK
    assert result.content == 5
    assert result.call_id == "c1"
    assert result.error_kind is None


def test_unknown_tool_is_schema_error(registry):
    result = registry.invoke(ToolCall(id="c2", name="nope", args={}))
    assert result.status is ToolStatus.ERROR
    assert result.error_kind is ErrorKind.SCHEMA
    assert "unknown tool" in result.error


def test_tool_error_classification_honored(registry):
    def flaky():
        raise ToolError("try again later", kind=ErrorKind.RETRYABLE)

    registry.register("flaky", flaky)
    result = registry.invoke(ToolCall(id="c3", name="flaky", args={}))
    assert result.status is ToolStatus.ERROR
    assert result.error_kind is ErrorKind.RETRYABLE
    assert "try again later" in result.error


def test_plain_exception_is_fatal(registry):
    def boom():
        raise RuntimeError("kaput")

    registry.register("boom", boom)
    result = registry.invoke(ToolCall(id="c4", name="boom", args={}))
    assert result.status is ToolStatus.ERROR
    assert result.error_kind is ErrorKind.FATAL
    assert "RuntimeError: kaput" in result.error


def test_bad_args_are_fatal_not_raised(registry):
    result = registry.invoke(ToolCall(id="c5", name="add", args={"a": 1}))
    assert result.status is ToolStatus.ERROR
    assert result.error_kind is ErrorKind.FATAL


def test_duplicate_registration_raises(registry):
    with pytest.raises(ValueError, match="already registered"):
        registry.register("add", lambda: None)


def test_specs_shape(registry):
    specs = registry.specs()
    assert len(specs) == 1
    fn = specs[0]["function"]
    assert fn["name"] == "add"
    assert fn["description"] == "add two numbers"
    assert fn["parameters"]["type"] == "object"


def test_elapsed_ms_recorded(registry):
    import time

    registry.register("slow", lambda: time.sleep(0.02))
    result = registry.invoke(ToolCall(id="c6", name="slow", args={}))
    assert result.elapsed_ms >= 10
