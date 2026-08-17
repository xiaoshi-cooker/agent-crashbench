"""Verdict envelope for out-of-process oracles.

Design: docs/design/oracle-protocol.md. Three-state verdict with an
exit-code interlock (exit 1 deliberately unused: an accidental interpreter
crash must never look like a verdict), mandatory identity block, canonical
JSON, fail-closed parsing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from harness.core.canonical import canonical_json, sha256_hex

__all__ = [
    "Verdict",
    "OracleReport",
    "OracleProtocolError",
    "parse_report",
    "write_report",
    "source_sha256",
    "EXIT_PASS",
    "EXIT_MISMATCH",
    "EXIT_ERROR",
]

EXIT_PASS = 0
EXIT_MISMATCH = 2
EXIT_ERROR = 3


class Verdict(StrEnum):
    PASS = "pass"
    MISMATCH = "mismatch"
    ERROR = "error"


_VERDICT_EXIT = {
    Verdict.PASS: EXIT_PASS,
    Verdict.MISMATCH: EXIT_MISMATCH,
    Verdict.ERROR: EXIT_ERROR,
}

_REQUIRED_IDENTITY_KEYS = ("protocol_version", "oracle_source_sha256", "input_sha256")
_ALLOWED_TOP_KEYS = {"verdict", "exit_code", "identity", "details"}

PROTOCOL_VERSION = 1


class OracleProtocolError(Exception):
    """A report that cannot be fully understood is no verdict at all."""


@dataclass(frozen=True)
class OracleReport:
    verdict: Verdict
    identity: dict[str, Any]
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return _VERDICT_EXIT[self.verdict]

    @classmethod
    def create(
        cls,
        verdict: Verdict,
        oracle_source_sha256: str,
        input_sha256: str,
        details: dict[str, Any] | None = None,
    ) -> OracleReport:
        return cls(
            verdict=verdict,
            identity={
                "protocol_version": PROTOCOL_VERSION,
                "oracle_source_sha256": oracle_source_sha256,
                "input_sha256": input_sha256,
            },
            details=details or {},
        )

    def to_json(self) -> str:
        return canonical_json(
            {
                "verdict": str(self.verdict),
                "exit_code": self.exit_code,
                "identity": dict(self.identity),
                "details": dict(self.details),
            }
        )


def parse_report(text: str) -> OracleReport:
    import json

    try:
        d = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OracleProtocolError(f"unparseable report: {exc}") from exc
    if not isinstance(d, dict):
        raise OracleProtocolError("report must be a JSON object")

    unknown = set(d) - _ALLOWED_TOP_KEYS
    if unknown:
        raise OracleProtocolError(f"unknown top-level keys: {sorted(unknown)}")

    try:
        verdict = Verdict(d["verdict"])
    except (KeyError, ValueError) as exc:
        raise OracleProtocolError(f"missing or unknown verdict: {d.get('verdict')!r}") from exc

    exit_code = d.get("exit_code")
    if exit_code != _VERDICT_EXIT[verdict]:
        raise OracleProtocolError(
            f"interlock broken: verdict {verdict} requires exit {_VERDICT_EXIT[verdict]}, "
            f"report says {exit_code!r}"
        )

    identity = d.get("identity")
    if not isinstance(identity, dict):
        raise OracleProtocolError("missing identity block")
    missing = [k for k in _REQUIRED_IDENTITY_KEYS if k not in identity]
    if missing:
        raise OracleProtocolError(f"identity block missing keys: {missing}")

    return OracleReport(verdict=verdict, identity=identity, details=d.get("details", {}))


def write_report(report: OracleReport, path: str | os.PathLike[str]) -> None:
    Path(path).write_text(report.to_json() + "\n", encoding="utf-8")


def source_sha256(path: str | os.PathLike[str]) -> str:
    """Digest of an oracle's own source file, for the identity block."""
    return sha256_hex(Path(path).read_bytes())
