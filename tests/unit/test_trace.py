"""Tests for the JSONL trace (docs/design/trace.md)."""

import pytest

from harness.core.types import EventType
from harness.trace import TraceIntegrityError, TraceWriter, read_events


def _write(tmp_path, run_id="r1", n=3, **kw):
    with TraceWriter(tmp_path, run_id, **kw) as w:
        for i in range(n):
            w.emit(EventType.LLM_CALL, {"i": i})
        return w.path


def test_roundtrip(tmp_path):
    path = _write(tmp_path, n=3)
    result = read_events(path)
    assert not result.truncated_tail
    assert [e.seq for e in result.events] == [0, 1, 2]
    assert result.events[1].payload == {"i": 1}
    assert all(e.run_id == "r1" for e in result.events)


def test_missing_file_reads_empty(tmp_path):
    result = read_events(tmp_path / "nope.jsonl")
    assert result.events == [] and not result.truncated_tail
    assert result.last_seq == -1


def test_reopen_continues_sequence(tmp_path):
    _write(tmp_path, n=2)
    with TraceWriter(tmp_path, "r1") as w:
        assert not w.recovered_torn_tail
        e = w.emit(EventType.RUN_END, {})
    assert e.seq == 2
    assert [e.seq for e in read_events(w.path).events] == [0, 1, 2]


def test_torn_tail_tolerated_on_read(tmp_path):
    path = _write(tmp_path, n=2)
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write('{"run_id":"r1","seq":2,"ty')  # crash mid-write
    result = read_events(path)
    assert result.truncated_tail
    assert [e.seq for e in result.events] == [0, 1]


def test_writer_recovers_from_torn_tail(tmp_path):
    path = _write(tmp_path, n=2)
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write('{"run_id":"r1","seq":2,"ty')
    with TraceWriter(tmp_path, "r1") as w:
        assert w.recovered_torn_tail
        e = w.emit(EventType.RUN_END, {})
    assert e.seq == 2  # torn fragment discarded, sequence stays contiguous
    result = read_events(path)
    assert not result.truncated_tail
    assert [e.seq for e in result.events] == [0, 1, 2]


def test_torn_first_line_recovers_to_empty(tmp_path):
    path = tmp_path / "r2.jsonl"
    path.write_text('{"run_id":"r2","se', encoding="utf-8")
    result = read_events(path)
    assert result.truncated_tail and result.events == []
    with TraceWriter(tmp_path, "r2") as w:
        e = w.emit(EventType.RUN_START, {})
    assert e.seq == 0


def test_mid_file_corruption_raises(tmp_path):
    path = _write(tmp_path, n=1)
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write("garbage\n")
        fh.write('{"run_id":"r1","seq":2,"type":"run_end","payload":{},"ts_us":1}\n')
    with pytest.raises(TraceIntegrityError, match="unparseable"):
        read_events(path)


def test_seq_gap_raises(tmp_path):
    path = _write(tmp_path, n=1)
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write('{"run_id":"r1","seq":5,"type":"run_end","payload":{},"ts_us":1}\n')
    with pytest.raises(TraceIntegrityError, match="gap or disorder"):
        read_events(path)


def test_unicode_payload_survives(tmp_path):
    with TraceWriter(tmp_path, "r3") as w:
        w.emit(EventType.TOOL_END, {"msg": "校验完成 — naïve ✓"})
    events = read_events(w.path).events
    assert events[0].payload["msg"] == "校验完成 — naïve ✓"


def test_emit_after_close_raises(tmp_path):
    w = TraceWriter(tmp_path, "r4")
    w.close()
    with pytest.raises(ValueError):
        w.emit(EventType.RUN_START, {})


def test_fsync_mode_works(tmp_path):
    path = _write(tmp_path, run_id="r5", n=2, fsync=True)
    assert [e.seq for e in read_events(path).events] == [0, 1]
