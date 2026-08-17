"""Tests for the record/replay cassette (docs/design/llm.md)."""

import pytest

from harness.llm import LLMBackend, LLMResponse, MockBackend
from harness.llm.cassette import Cassette, CassetteMiss

MSGS_A = [{"role": "user", "content": "question A"}]
MSGS_B = [{"role": "user", "content": "question B"}]


def test_record_then_replay_roundtrip(tmp_path):
    tape = tmp_path / "tape.jsonl"
    real = MockBackend([LLMResponse(content="answer A"), LLMResponse(content="answer B")])

    recorder = Cassette(tape, "record", backend=real)
    assert recorder.complete(MSGS_A).content == "answer A"
    assert recorder.complete(MSGS_B).content == "answer B"
    assert tape.exists()

    replayer = Cassette(tape, "replay")  # no backend needed
    assert replayer.complete(MSGS_B).content == "answer B"  # order-independent lookup
    assert replayer.complete(MSGS_A).content == "answer A"


def test_replay_miss_fails_closed(tmp_path):
    tape = tmp_path / "tape.jsonl"
    Cassette(tape, "record", backend=MockBackend([LLMResponse()])).complete(MSGS_A)
    replayer = Cassette(tape, "replay")
    with pytest.raises(CassetteMiss):
        replayer.complete(MSGS_B)


def test_identical_requests_replay_in_recorded_order(tmp_path):
    tape = tmp_path / "tape.jsonl"
    real = MockBackend([LLMResponse(content="first"), LLMResponse(content="second")])
    recorder = Cassette(tape, "record", backend=real)
    recorder.complete(MSGS_A)
    recorder.complete(MSGS_A)  # same request, different (non-deterministic) answer

    replayer = Cassette(tape, "replay")
    assert replayer.complete(MSGS_A).content == "first"
    assert replayer.complete(MSGS_A).content == "second"
    with pytest.raises(CassetteMiss):  # queue exhausted
        replayer.complete(MSGS_A)


def test_record_appends_across_sessions(tmp_path):
    tape = tmp_path / "tape.jsonl"
    Cassette(tape, "record", backend=MockBackend([LLMResponse(content="one")])).complete(MSGS_A)
    Cassette(tape, "record", backend=MockBackend([LLMResponse(content="two")])).complete(MSGS_B)
    replayer = Cassette(tape, "replay")
    assert replayer.complete(MSGS_A).content == "one"
    assert replayer.complete(MSGS_B).content == "two"


def test_tools_are_part_of_the_key(tmp_path):
    tape = tmp_path / "tape.jsonl"
    real = MockBackend([LLMResponse(content="with tools")])
    Cassette(tape, "record", backend=real).complete(MSGS_A, tools=[{"name": "t"}])
    replayer = Cassette(tape, "replay")
    with pytest.raises(CassetteMiss):
        replayer.complete(MSGS_A)  # same messages, no tools -> different request
    assert replayer.complete(MSGS_A, tools=[{"name": "t"}]).content == "with tools"


def test_mode_validation(tmp_path):
    with pytest.raises(ValueError, match="unknown cassette mode"):
        Cassette(tmp_path / "t.jsonl", "playback")
    with pytest.raises(ValueError, match="requires a backend"):
        Cassette(tmp_path / "t.jsonl", "record")


def test_cassette_satisfies_backend_protocol(tmp_path):
    assert isinstance(Cassette(tmp_path / "t.jsonl", "replay"), LLMBackend)
