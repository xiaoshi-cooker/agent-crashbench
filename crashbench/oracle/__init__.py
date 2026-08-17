"""Out-of-process oracle verdict envelope (docs/design/oracle-protocol.md)."""

from crashbench.oracle.protocol import (
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
