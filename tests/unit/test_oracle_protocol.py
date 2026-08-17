"""Tests for the oracle verdict envelope (docs/design/oracle-protocol.md)."""

import json

import pytest

from crashbench.oracle import (
    EXIT_ERROR,
    EXIT_MISMATCH,
    EXIT_PASS,
    OracleProtocolError,
    OracleReport,
    Verdict,
    parse_report,
    source_sha256,
    write_report,
)


def _report(verdict=Verdict.PASS, **details):
    return OracleReport.create(
        verdict=verdict,
        oracle_source_sha256="a" * 64,
        input_sha256="b" * 64,
        details=details,
    )


def test_verdict_exit_interlock():
    assert _report(Verdict.PASS).exit_code == EXIT_PASS == 0
    assert _report(Verdict.MISMATCH).exit_code == EXIT_MISMATCH == 2
    assert _report(Verdict.ERROR).exit_code == EXIT_ERROR == 3


def test_roundtrip_through_file(tmp_path):
    report = _report(Verdict.MISMATCH, duplicate_effects=1)
    path = tmp_path / "report.json"
    write_report(report, path)
    parsed = parse_report(path.read_text(encoding="utf-8"))
    assert parsed == report
    assert parsed.details == {"duplicate_effects": 1}


def test_broken_interlock_rejected():
    d = json.loads(_report(Verdict.MISMATCH).to_json())
    d["exit_code"] = 0  # claims pass exit while verdict says mismatch
    with pytest.raises(OracleProtocolError, match="interlock broken"):
        parse_report(json.dumps(d))


def test_unknown_verdict_rejected():
    d = json.loads(_report().to_json())
    d["verdict"] = "maybe"
    d["exit_code"] = 0
    with pytest.raises(OracleProtocolError, match="unknown verdict"):
        parse_report(json.dumps(d))


def test_missing_identity_keys_rejected():
    d = json.loads(_report().to_json())
    del d["identity"]["input_sha256"]
    with pytest.raises(OracleProtocolError, match="missing keys"):
        parse_report(json.dumps(d))


def test_unknown_top_level_keys_rejected():
    d = json.loads(_report().to_json())
    d["extra"] = 1
    with pytest.raises(OracleProtocolError, match="unknown top-level keys"):
        parse_report(json.dumps(d))


def test_non_object_rejected():
    with pytest.raises(OracleProtocolError):
        parse_report("[1,2]")
    with pytest.raises(OracleProtocolError):
        parse_report("not json")


def test_source_sha256_is_stable(tmp_path):
    f = tmp_path / "oracle.py"
    f.write_bytes(b"print('judge')\n")
    assert source_sha256(f) == source_sha256(f)
    f.write_bytes(b"print('judge!')\n")
    changed = source_sha256(f)
    f.write_bytes(b"print('judge')\n")
    assert source_sha256(f) != changed
